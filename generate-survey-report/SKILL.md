---
name: generate-survey-report
description: Generate a traceable Chinese Word current-state assessment from a completed wastewater-plant field-survey Excel workbook and optional supporting DOCX/PDF/photos. Use when asked to turn a 工艺智能控制现场调研清单 Excel into 调研报告、现状评估章节、现场调研情况 Word 文件, or to validate and iteratively improve that reporting workflow. Produce only evidence-backed findings and clearly list gaps; do not invent project facts or detailed solutions.
---

# 调研报告生成

将“现场填写的 Excel”转为“可核验的 Word 现状评估”，采用固定的中间结构，避免直接从表格自由写作。

## 输入与输出

- 输入：一份已填写调研 Excel；可选补充材料（运行数据、图纸、照片、已审核 Word 样例）。
- 输出：`调研报告.docx`、`待确认事项.xlsx`、`内容追溯表.xlsx` 和本次运行的 `manifest.json`。如没有公司 Word 模板，使用通用模板生成可审核初稿。
- 中间文件：`survey.json`、`chapter-model.json`、`drafted-content.json`。它们属于项目过程文件，不是数据库。

## Agent 驱动 Harness V0.2

1. 调研 Excel 放入 `survey-report-workspace/projects/<project-id>/input/`，其中只能有一个当前 `.xlsx` 文件。
2. Agent 使用仓库根目录 `.venv` 中的 Python 执行 `scripts/run_pipeline.py prepare`。脚本创建独立 `run_id`，建立 `source-index.json`，分别提取 Excel 与补充资料，再形成统一 `facts.json`、完整性校验和动态章节模型。
3. 若状态为 `validation_failed`，停止写作并报告阻断项；不得绕过闸门。
4. 若状态为 `ready_to_draft`，读取本次运行的 `working/agent-request.json`，再按其中路径读取结构化事实、写作规则和金标准配置。存在 `golden_output` 时，先读取批准样例，复现其章节取舍、内容颗粒度和行文方式；不得复制其中项目参数。
5. Agent 将正文写入本次运行的 `working/drafted-content.json`：每个段落关联 `claim_ids`，每个 claim 记录来源；不得搬用历史项目参数。
6. Agent 执行 `scripts/run_pipeline.py finalize --run-dir <run-dir>`。Harness 校验正文合同、拒绝无来源结论，并生成 Word、待确认事项表、追溯表及自动 QA 结果。
7. 若当前 Agent 提供 Word 渲染能力，则逐页检查；没有渲染器时仍生成全部文件，并把视觉 QA 保持为 `pending`。实际检查通过后执行 `scripts/run_pipeline.py record-qa --run-dir <run-dir> --status passed`；发现问题则记录 `failed`。

每次运行都保留在 `projects/<project-id>/runs/<run-id>/`，不得覆盖既有运行结果。用户的一次“运行项目”指令由 Agent 自动完成 prepare、写作、finalize 和视觉 QA，无需用户逐步执行命令。

## 知识中心模式

- 默认 `--knowledge-mode disabled`，只处理本地输入，不读取飞书配置，也不执行远端写回。
- 用户要求使用历史知识但允许降级时使用 `optional`；连接失败后继续本地流程并记录警告。
- 用户明确要求知识中心必须可用时使用 `required`；连接或写回失败即停止。
- `--disable-knowledge` 仅作为旧命令兼容别名。

## 写作边界

- “背景事实”可来自已登记的正式补充资料；“现场事实”写设备、仪表、控制方式、现场问题和数据。
- “判断”只采用 `writing-rules.md` 中允许的受控表述，并关联证据。
- `target_requirement` 不得伪装成现有配置。若人工金标准允许且需求已有依据，可以作为“后续建设要求/建议配置”进入对应章节，但不展开详细方案。
- 用户人工定稿和项目级 `golden-profile.json` 控制章节取舍。Excel 自动汇总状态与人工定稿冲突时不得静默删章，应采用项目级覆盖并保留可审计记录。
- 资料冲突不得自动覆盖，必须进入待确认事项并保留双方来源。

## 迭代

人工审核后，阅读 `references/feedback-policy.md`。用户明确确认的人工修订稿应原样存入 `survey-report-workspace/golden-cases/<project-id>/approved-report.docx`，同时记录哈希和项目级 profile；禁止再次改写该原件。每次规则变化都用“原 Excel → 新输出”与金标准比较，重点检查章节保留、事实覆盖、建议边界和人工修改量。

## 资源

- `assets/survey-report-template.docx`：可由用户调整的通用 Word 调研报告模板，也是未提供公司模板时的默认版式基线。
- `scripts/extract_docx.py`：读取历史 Word 样例的标题、段落和表格结构。
- `scripts/build_source_index.py`、`scripts/extract_supporting.py`：登记并提取补充资料；未经确认的修订稿是反馈源，用户明确批准的修订稿归档为输出金标准，但不作为其他项目事实源。
- `scripts/extract_survey.py`：识别重复表头，保留 Excel 单元格来源、信息角色和确认状态。
- `scripts/build_fact_model.py`：合并多源事实、识别冲突并确定是否可进入现状评估。
- `scripts/validate_survey.py`：检查重要调研项缺失和公式错误。
- `scripts/build_chapter_model.py`：组织章节事实，不生成结论。
- `scripts/build_traceability.py`：拒绝无来源结论。
- `scripts/run_pipeline.py`：V0.2 统一入口和状态机。
- `scripts/validate_draft.py`：检查 Agent 正文合同和段落—结论关联。
- `scripts/build_docx.py`：使用选定模板生成可审阅的 Word 初稿。
- `scripts/export_pending_items.py`、`scripts/export_traceability.py`：导出人工可读的审核表。
- `scripts/check_docx.py`：检查占位符、空章节和标题结构；视觉版式仍需渲染确认。
- `references/chengnan-approved-pattern.md`：从用户人工定稿提炼的高优先级写作和章节模式。
