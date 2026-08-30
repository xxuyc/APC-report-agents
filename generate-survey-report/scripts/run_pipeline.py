#!/usr/bin/env python3
"""Agent-driven local-file Harness for survey Excel to reviewable Word reports."""

# =============================================================================
# 脚本用途（中文说明）
# -----------------------------------------------------------------------------
# 这是「调研报告生成流水线」的主控脚本（Harness / 编排器）。
# 它把一份「调研 Excel 表」+ 一份「Word 模板」，自动加工成一份可评审的
# 《调研报告.docx》，并附带《待确认事项.xlsx》《内容追溯表.xlsx》等产物。
#
# 整体流程分三个阶段：
#   1) prepare（准备）：接收 Excel / Word 模板 / 补充资料 → 创建项目目录并
#      归档输入文件 → 依次运行「提取 → 校验 → 构建章节模型」三个子脚本 →
#      生成 agent-request.json，把“起草正文”这件事打包交给 AI Agent 完成。
#   2) Agent 起草：外部 AI 依据 agent-request.json 写出 drafted-content.json。
#      （本脚本不直接写正文，只负责准备好上下文和写作约束交给 Agent。）
#   3) finalize（收尾）：读取 Agent 写好的草稿 → 校验草稿 → 构建内容追溯 →
#      生成 Word 报告 → 检查 Word 质量 → 导出两个 Excel → 等待人工视觉质检。
#
# 另外还有两个辅助子命令：
#   - record-qa：记录人工视觉质检（通过/不通过）的结果。
#   - status   ：查看某次运行的 manifest.json 状态。
#
# 所有子命令都会以 JSON 形式向 stdout 输出状态，方便上层工具或 Agent 解析。
# =============================================================================

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SKILL_VERSION = "0.2.1"
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from knowledge_center.pipeline import normalize_knowledge_mode, prepare_snapshot
from knowledge_center.evidence import register_survey_references
from knowledge_center.writeback import writeback_survey_artifacts
from knowledge_center.core import KnowledgeUnavailable, ProjectConfirmationRequired, repository_from_options, resolve_project


def write_json(path, data):
    # 写入 JSON 文件：自动创建父目录，中文不转义（ensure_ascii=False），缩进 2 空格。
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path):
    # 读取 JSON 文件并按字典返回。
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_hash(path):
    # 计算文件的 SHA-256 哈希，用于判断文件内容是否一致（去重/校验）。
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def next_run_id(runs_dir):
    # 生成本次运行的编号：日期 + 当天序号，例如 20260824-001、20260824-002……
    prefix = datetime.now().strftime("%Y%m%d")
    numbers = []
    for path in runs_dir.glob(f"{prefix}-*"):
        try:
            numbers.append(int(path.name.rsplit("-", 1)[1]))
        except ValueError:
            pass
    return f"{prefix}-{max(numbers, default=0) + 1:03d}"


def update_manifest(path, **changes):
    # 更新 manifest.json：合并传入的字段，并刷新 updated_at 时间戳。
    manifest = read_json(path)
    manifest.update(changes)
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(path, manifest)
    return manifest


def run_script(name, arguments, log_dir):
    # 用当前 Python 解释器运行本目录下的子脚本（如 extract_survey.py），
    # 捕获 stdout/stderr 并写入对应的 .log 文件，返回子进程结果。
    command = [sys.executable, str(SCRIPT_DIR / name), *[str(item) for item in arguments]]
    result = subprocess.run(command, text=True, capture_output=True, encoding="utf-8", errors="replace")
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{Path(name).stem}.log").write_text(
        f"COMMAND: {' '.join(command)}\nEXIT_CODE: {result.returncode}\n\nSTDOUT\n{result.stdout}\n\nSTDERR\n{result.stderr}",
        encoding="utf-8",
    )
    return result


def yaml_quote(value):
    # 把字符串转成 YAML 单引号字面量（内部单引号翻倍），用于写 project.yaml。
    return "'" + str(value).replace("'", "''") + "'"


def project_paths(workspace, project_id):
    # 根据工作区根目录和项目 ID 推导项目的四个关键目录：
    # project（根）、input（输入）、runs（历次运行）、review（评审）。
    project = workspace / "projects" / project_id
    return project, project / "input", project / "runs", project / "review"


def ensure_project(workspace, project_id, project_name):
    # 初始化项目：校验 project-id 格式 → 创建目录结构 → 首次运行时生成 project.yaml 配置。
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", project_id):
        raise ValueError("project-id 只能使用小写字母、数字和连字符。")
    project, input_dir, runs_dir, review_dir = project_paths(workspace, project_id)
    for directory in (input_dir, input_dir / "photos", input_dir / "drawings",
                      input_dir / "supporting-docs", runs_dir, review_dir):
        directory.mkdir(parents=True, exist_ok=True)
    config = project / "project.yaml"
    if not config.exists():
        config.write_text(
            f"project_id: {yaml_quote(project_id)}\nproject_name: {yaml_quote(project_name)}\n"
            "survey_type: 'wastewater-intelligent-control'\ninput_version: 'v0.2'\ntemplate_version: '0.2'\n",
            encoding="utf-8",
        )
    return project, input_dir, runs_dir, review_dir


def fail_before_run(message):
    # 在正式运行前失败时的统一出口：向 stdout 输出 input_error JSON，返回退出码 2。
    print(json.dumps({"status": "input_error", "message": message}, ensure_ascii=False))
    return 2


def prepare(args):
    # =========================================================================
    # prepare 子命令：准备阶段。
    # 职责：接收并归档输入 → 提取/校验/建模 → 生成 agent-request.json 交给 AI 起草。
    # =========================================================================
    workspace = Path(args.workspace).resolve()
    knowledge_mode = normalize_knowledge_mode(args.knowledge_mode, args.disable_knowledge)
    if not args.project_id:
        if knowledge_mode == "disabled":
            return fail_before_run("本地模式请提供 --project-id；启用知识中心后可由项目路由器识别。")
        try:
            repository = repository_from_options(args.knowledge_store, allow_empty=False)
            resolved = resolve_project(repository, explicit_project_name=args.project_name, input_paths=[args.input] if args.input else [])
            args.project_id = resolved["project_id"]
            args.project_name = args.project_name or resolved.get("project_name") or args.project_id
        except (KnowledgeUnavailable, ProjectConfirmationRequired) as exc:
            print(json.dumps(exc.as_dict(), ensure_ascii=False))
            return 6
    args.project_name = args.project_name or args.project_id
    try:
        project, input_dir, runs_dir, _ = ensure_project(workspace, args.project_id, args.project_name)
    except ValueError as exc:
        return fail_before_run(str(exc))

    # 显式 --input 直接作为本次运行输入，不覆盖项目 input 中的旧版调研表。
    if args.input:
        supplied = Path(args.input).resolve()
        if not supplied.is_file() or supplied.suffix.lower() != ".xlsx":
            return fail_before_run("输入文件不存在或不是 .xlsx 文件。")
        source = supplied
    else:
        excel_files = [path for path in input_dir.glob("*.xlsx") if not path.name.startswith("~$")]
        if len(excel_files) != 1:
            return fail_before_run(f"项目 input 中应有且仅有一个 Excel，当前数量为 {len(excel_files)}。")
        source = excel_files[0]
    # 未显式指定模板时，使用内置默认模板。
    template = Path(args.template).resolve() if args.template else SKILL_DIR / "assets" / "survey-report-template.docx"
    if not template.is_file() or template.suffix.lower() != ".docx":
        return fail_before_run("Word 模板不存在或不是 .docx 文件。")

    # 复制用户提供的补充资料到 input/supporting-docs。
    for supporting in args.supporting or []:
        item = Path(supporting).resolve()
        if not item.is_file():
            return fail_before_run(f"补充资料不存在：{item}")
        target = input_dir / "supporting-docs" / item.name
        if not target.exists():
            shutil.copy2(item, target)

    feedback_files = []
    for feedback in args.feedback or []:
        item = Path(feedback).resolve()
        if not item.is_file():
            return fail_before_run(f"审核反馈文件不存在：{item}")
        feedback_files.append(item)

    # 生成新的 run_id 并创建本次运行的目录结构：
    # input（快照）/ working（中间产物）/ output（最终产物）/ qa / logs。
    run_id = next_run_id(runs_dir)
    run_dir = runs_dir / run_id
    snapshot = run_dir / "input"
    working = run_dir / "working"
    output = run_dir / "output"
    qa = run_dir / "qa"
    logs = run_dir / "logs"
    for directory in (snapshot, working, output, qa, logs):
        directory.mkdir(parents=True, exist_ok=True)
    # 把 Excel、模板、补充资料都复制一份到 snapshot，保证本次运行输入可追溯、不被后续改动影响。
    survey_snapshot = snapshot / source.name
    template_snapshot = snapshot / template.name
    shutil.copy2(source, survey_snapshot)
    shutil.copy2(template, template_snapshot)
    support_snapshot = snapshot / "supporting-docs"
    support_snapshot.mkdir(exist_ok=True)
    for item in (input_dir / "supporting-docs").iterdir():
        if item.is_file():
            shutil.copy2(item, support_snapshot / item.name)
    for folder in ("photos", "drawings"):
        destination = snapshot / folder
        destination.mkdir(exist_ok=True)
        for item in (input_dir / folder).iterdir():
            if item.is_file():
                shutil.copy2(item, destination / item.name)
    feedback_snapshot = snapshot / "review-feedback"
    feedback_snapshot.mkdir(exist_ok=True)
    for item in feedback_files:
        shutil.copy2(item, feedback_snapshot / item.name)

    # 建立 manifest.json：记录本次运行的基本信息、输入文件及其哈希，作为流程状态机。
    manifest_path = run_dir / "manifest.json"
    manifest = {
        "schema_version": "0.2", "project_id": args.project_id, "project": args.project_name,
        "run_id": run_id, "skill_version": SKILL_VERSION, "template_version": "0.2",
        "status": "ready_to_prepare", "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_file": str(survey_snapshot), "input_sha256": file_hash(survey_snapshot),
        "template_file": str(template_snapshot), "template_sha256": file_hash(template_snapshot),
        "warnings": 0, "outputs": [], "run_dir": str(run_dir),
    }
    write_json(manifest_path, manifest)

    # 依次运行三个子脚本，把 Excel 一步步转成结构化的章节模型：
    source_index = working / "source-index.json"
    supporting_json = working / "supporting-evidence.json"
    survey_json = working / "survey.json"
    validation_json = working / "validation.json"
    facts_json = working / "facts.json"
    chapter_model = working / "chapter-model.json"
    result = run_script("build_source_index.py", [snapshot, source_index], logs)
    if result.returncode:
        update_manifest(manifest_path, status="input_error", failure_step="build_source_index")
        return fail_before_run("资料索引生成失败，详见本次运行 logs。")
    result = run_script("extract_supporting.py", [source_index, supporting_json], logs)
    if result.returncode:
        update_manifest(manifest_path, status="input_error", failure_step="extract_supporting")
        return fail_before_run("补充资料提取失败，详见本次运行 logs。")
    result = run_script("extract_survey.py", [survey_snapshot, survey_json], logs)
    if result.returncode:
        update_manifest(manifest_path, status="input_error", failure_step="extract_survey")
        return fail_before_run("Excel 提取失败，详见本次运行 logs。")
    result = run_script("validate_survey.py", [survey_json, validation_json], logs)
    if result.returncode:
        update_manifest(manifest_path, status="input_error", failure_step="validate_survey")
        return fail_before_run("完整性校验脚本执行失败，详见本次运行 logs。")
    validation = read_json(validation_json)
    # 校验不通过（can_continue 为 False）则终止，返回退出码 3。
    if not validation.get("can_continue"):
        update_manifest(manifest_path, status="validation_failed",
                        warnings=validation.get("counts", {}).get("warning", 0),
                        validation=validation.get("counts", {}))
        print(json.dumps({"status": "validation_failed", "run_dir": str(run_dir),
                          "validation": str(validation_json)}, ensure_ascii=False))
        return 3
    result = run_script("build_fact_model.py", [survey_json, supporting_json, source_index, facts_json], logs)
    if result.returncode:
        update_manifest(manifest_path, status="input_error", failure_step="build_fact_model")
        return 2
    facts = read_json(facts_json)
    if facts.get("conflicts"):
        for conflict in facts["conflicts"]:
            validation["issues"].append({"severity": "warning", "type": "source_conflict",
                                          "message": conflict["message"], "sources": conflict.get("sources", [])})
        validation["counts"]["warning"] += len(facts["conflicts"])
        validation["issue_count"] = len(validation["issues"])
        write_json(validation_json, validation)
    golden_dir = workspace / "golden-cases" / args.project_id
    golden_profile = golden_dir / "golden-profile.json"
    chapter_arguments = [facts_json, validation_json, chapter_model]
    if golden_profile.is_file():
        chapter_arguments.append(golden_profile)
    result = run_script("build_chapter_model.py", chapter_arguments, logs)
    if result.returncode:
        update_manifest(manifest_path, status="input_error", failure_step="build_chapter_model")
        return 2

    # 打包一份 agent-request.json：告诉 AI 要干什么（起草现状评估）、输入有哪些、
    # 输出写到哪、以及必须遵守的写作约束，然后由外部 Agent 据此写出草稿。
    knowledge_snapshot_path = working / "knowledge-snapshot.json"
    knowledge_snapshot = prepare_snapshot(
        output=knowledge_snapshot_path,
        project_id=args.project_id,
        project_name=args.project_name,
        agent_type="generate-survey-report",
        input_paths=[survey_snapshot, *support_snapshot.iterdir()],
        store_path=args.knowledge_store,
        query=args.retrieval_query,
        intents=args.knowledge_intent or [],
        reference_ids=args.reference_project_id or [],
        mode=knowledge_mode,
    )
    register_survey_references(chapter_model, knowledge_snapshot)

    agent_request = {
        "schema_version": "0.2.1", "action": "draft_current_state_assessment_and_constraints",
        "project": args.project_name, "run_id": run_id,
        "inputs": {"source_index": str(source_index), "facts": str(facts_json),
                   "chapter_model": str(chapter_model),
                   "knowledge_snapshot": str(knowledge_snapshot_path),
                   "writing_rules": str(SKILL_DIR / "references" / "writing-rules.md"),
                   "terminology": str(SKILL_DIR / "references" / "terminology.md"),
                   "draft_contract": str(SKILL_DIR / "references" / "drafted-content-schema.md"),
                   "approved_writing_pattern": str(SKILL_DIR / "references" / "chengnan-approved-pattern.md"),
                   "golden_profile": str(golden_profile) if golden_profile.is_file() else "",
                   "golden_output": str(golden_dir / "approved-report.docx")
                   if (golden_dir / "approved-report.docx").is_file() else ""},
        "output": str(working / "drafted-content.json"),
        "constraints": ["不得使用 chapter-model.json 之外的项目事实。", "正式结论必须关联 fact_id 或 source_id。",
                        "项目存在 golden_profile 时，其人工批准章节取舍优先于自动适用性判断。",
                        "requirements 中的建设需求可以写成后续要求，但不得伪装成现有配置。",
                        "待确认事项不得写成确定事实。", "不得展开设备选型、工程量、报价或详细控制算法。",
                        "金标准控制行文和取舍，但其中的项目参数不得迁移到其他项目。"],
        "knowledge_constraints": [
            "Writing and method references may influence organization only; they are not project facts.",
            "A cross-project case or number must cite a source_id registered in chapter-model.json reference_sources.",
            "Historical evidence must never be stated as the current target project's condition.",
        ],
        "resume_command": f'python "{SCRIPT_DIR / "run_pipeline.py"}" finalize --run-dir "{run_dir}"',
    }
    write_json(working / "agent-request.json", agent_request)
    knowledge_plan = knowledge_snapshot["retrieval_plan"]
    update_manifest(manifest_path, status="ready_to_draft", agent_type="generate-survey-report",
                    knowledge_mode=knowledge_mode,
                    knowledge_status=knowledge_plan["knowledge_status"],
                    knowledge_warning=knowledge_plan.get("warning"),
                    knowledge_store=str(Path(args.knowledge_store).resolve()) if args.knowledge_store else "",
                    knowledge_snapshot=str(knowledge_snapshot_path),
                    knowledge_snapshot_sha256=knowledge_snapshot["sha256"],
                    retrieval_intents=knowledge_snapshot["retrieval_plan"]["intents"],
                    reference_project_ids=knowledge_snapshot["retrieval_plan"]["reference_project_ids"],
                    warnings=validation.get("counts", {}).get("warning", 0),
                    validation=validation.get("counts", {}))
    # 输出就绪状态和 agent-request 路径，供上层（或 Agent）读取后继续。
    print(json.dumps({"status": "ready_to_draft", "run_dir": str(run_dir),
                      "agent_request": str(working / "agent-request.json")}, ensure_ascii=False))
    return 0


def finalize(args):
    # =========================================================================
    # finalize 子命令：收尾阶段（在 Agent 写起草稿之后执行）。
    # 职责：读取草稿 → 校验草稿 → 生成追溯表 → 生成 Word → 检查 Word → 导出 Excel。
    # =========================================================================
    run_dir = Path(args.run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return fail_before_run("run-dir 中不存在 manifest.json。")
    manifest = read_json(manifest_path)
    working, output, qa, logs = run_dir / "working", run_dir / "output", run_dir / "qa", run_dir / "logs"
    # 草稿文件是 Agent 在上一步写好的；若不存在则无法继续。
    draft = working / "drafted-content.json"
    if not draft.is_file():
        update_manifest(manifest_path, status="draft_failed", failure_step="missing_drafted_content")
        print(json.dumps({"status": "draft_failed", "message": "Agent 尚未生成 drafted-content.json。"}, ensure_ascii=False))
        return 4
    # 先校验草稿是否符合约定的结构（配合章节模型一起校验）。
    draft_validation = working / "draft-validation.json"
    result = run_script("validate_draft.py", [working / "chapter-model.json", draft, draft_validation], logs)
    if result.returncode:
        update_manifest(manifest_path, status="draft_failed", failure_step="validate_draft")
        print(json.dumps({"status": "draft_failed", "validation": str(draft_validation)}, ensure_ascii=False))
        return 4

    # 依次执行三个子脚本：
    #   1) build_traceability.py  生成内容追溯（正文 ↔ 来源的对应关系）
    #   2) build_docx.py          用草稿 + 模板生成《调研报告.docx》
    #   3) check_docx.py          对生成的 Word 做质量检查（输出 word-check.json）
    trace_json = working / "traceability.json"
    commands = [
        ("build_traceability.py", [draft, trace_json]),
        ("build_docx.py", [draft, output / "调研报告_V0.2.docx", "--template", manifest["template_file"],
                           "--project-name", manifest["project"]]),
        ("check_docx.py", [output / "调研报告_V0.2.docx", qa / "word-check.json"]),
    ]
    for script, arguments in commands:
        result = run_script(script, arguments, logs)
        if result.returncode:
            status = "qa_failed" if script == "check_docx.py" else "draft_failed"
            update_manifest(manifest_path, status=status, failure_step=Path(script).stem)
            print(json.dumps({"status": status, "failure_step": script}, ensure_ascii=False))
            return 5

    # 使用公开的 openpyxl 生成审核工作簿，不依赖 Node.js、Office 或 Codex 内置包。
    spreadsheet_commands = [
        ("export_pending_items.py", [working / "validation.json", draft, output / "待确认事项.xlsx"]),
        ("export_traceability.py", [trace_json, output / "内容追溯表.xlsx"]),
    ]
    for script, arguments in spreadsheet_commands:
        result = run_script(script, arguments, logs)
        if result.returncode:
            update_manifest(manifest_path, status="qa_failed", failure_step=Path(script).stem)
            print(json.dumps({"status": "qa_failed", "failure_step": script}, ensure_ascii=False))
            return 5

    # 汇总最终产物，状态置为 completed_with_warnings，等待人工视觉质检（visual_qa=pending）。
    outputs = [str(output / "调研报告_V0.2.docx"), str(output / "待确认事项.xlsx"), str(output / "内容追溯表.xlsx")]
    update_manifest(manifest_path, status="completed_with_warnings", outputs=outputs,
                    visual_qa="pending", qa=str(qa / "word-check.json"), failure_step=None)
    print(json.dumps({"status": "completed_with_warnings", "visual_qa": "pending",
                      "run_dir": str(run_dir), "outputs": outputs}, ensure_ascii=False))
    return 0


def record_qa(args):
    # record-qa 子命令：记录人工视觉质检结果（passed/failed），并据此推进最终状态。
    run_dir = Path(args.run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return fail_before_run("run-dir 中不存在 manifest.json。")
    qa_result = {"status": args.status, "notes": args.notes or "",
                 "checked_at": datetime.now().isoformat(timespec="seconds")}
    write_json(run_dir / "qa" / "visual-qa.json", qa_result)
    manifest = read_json(manifest_path)
    # 质检不通过 → qa_failed；有警告 → completed_with_warnings；否则 → completed。
    if args.status == "failed":
        status = "qa_failed"
    elif manifest.get("warnings", 0):
        status = "completed_with_warnings"
    else:
        status = "completed"
    manifest = update_manifest(manifest_path, status=status, visual_qa=args.status,
                    failure_step=None if args.status == "passed" else manifest.get("failure_step"))
    if args.status == "passed" and manifest.get("knowledge_status") == "enabled":
        try:
            writeback_survey_artifacts(manifest, run_dir, manifest.get("knowledge_store") or None)
            update_manifest(manifest_path, knowledge_writeback="completed")
        except KnowledgeUnavailable as exc:
            update_manifest(manifest_path, knowledge_writeback="failed", knowledge_warning=str(exc))
            if manifest.get("knowledge_mode") == "required":
                print(json.dumps({"status": "knowledge_unavailable", "message": str(exc)}, ensure_ascii=False))
                return 7
    print(json.dumps({"status": status, "visual_qa": args.status}, ensure_ascii=False))
    return 0


def show_status(args):
    # status 子命令：打印某次运行的 manifest.json，查看当前进度/状态。
    manifest = read_json(Path(args.run_dir) / "manifest.json")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def build_parser():
    # 构建命令行解析器，暴露四个子命令：prepare / finalize / record-qa / status。
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--workspace", required=True)
    prepare_parser.add_argument("--project-id")
    prepare_parser.add_argument("--project-name")
    prepare_parser.add_argument("--input")
    prepare_parser.add_argument("--template")
    prepare_parser.add_argument("--supporting", action="append")
    prepare_parser.add_argument("--feedback", action="append")
    prepare_parser.add_argument("--knowledge-store")
    prepare_parser.add_argument("--retrieval-query")
    prepare_parser.add_argument("--knowledge-intent", action="append")
    prepare_parser.add_argument("--reference-project-id", action="append")
    prepare_parser.add_argument("--knowledge-mode", choices=("disabled", "optional", "required"),
                                default="disabled")
    prepare_parser.add_argument("--disable-knowledge", action="store_true")
    prepare_parser.set_defaults(func=prepare)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--run-dir", required=True)
    finalize_parser.set_defaults(func=finalize)
    qa_parser = subparsers.add_parser("record-qa")
    qa_parser.add_argument("--run-dir", required=True)
    qa_parser.add_argument("--status", required=True, choices=("passed", "failed"))
    qa_parser.add_argument("--notes")
    qa_parser.set_defaults(func=record_qa)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--run-dir", required=True)
    status_parser.set_defaults(func=show_status)
    return parser


if __name__ == "__main__":
    # 程序入口：解析命令行参数，并调用对应子命令的函数，用其返回值作为退出码。
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.func(arguments))
