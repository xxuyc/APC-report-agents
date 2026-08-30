#!/usr/bin/env python3
"""Validate extracted survey records before report drafting."""

import json
import re
import sys
from pathlib import Path


REQUIRED_MARKERS = ("必填", "一级", "关键", "必须")
PROJECT_NAME_MARKERS = ("项目名称", "水厂名称", "污水厂名称", "厂站名称")
CRITICAL_FORMULA_FIELDS = ("question", "answer", "required")


def column_number(coordinate):
    match = re.match(r"([A-Z]+)", coordinate or "")
    if not match:
        return None
    number = 0
    for character in match.group(1):
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def not_applicable(record, module_status):
    module = record.get("module", "")
    sheet = record.get("source", {}).get("sheet", "")
    for item in module_status:
        if (module and module in item["module"]) or item["module"] in sheet:
            applicable = item.get("applicable", "").strip()
            status = item.get("status", "").strip()
            return applicable == "否" or "不适用" in applicable or (not applicable and status == "不适用")
    return False


def applicable_state(record, module_status):
    module = record.get("module", "")
    sheet = record.get("source", {}).get("sheet", "")
    for item in module_status:
        if (module and module in item["module"]) or item["module"] in sheet:
            value = item.get("applicable", "").strip()
            if value == "是":
                return True
            if value == "否" or "不适用" in value:
                return False
    return None


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: validate_survey.py survey.json validation.json")
    survey = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    issues = []
    recognized_sheets = [sheet for sheet in survey.get("sheets", []) if sheet.get("tables") or sheet.get("header_row")]
    if not recognized_sheets:
        issues.append({"severity": "error", "type": "unsupported_workbook",
                       "message": "未识别到包含调研内容和调研结果字段的工作表。"})
    sheet_columns = {sheet.get("name"): sheet.get("columns", {}) for sheet in survey.get("sheets", [])}
    for error in survey.get("formula_errors", []):
        error_column = column_number(error.get("cell"))
        critical_columns = {
            columns.get(field) for field in CRITICAL_FORMULA_FIELDS
            for columns in [sheet_columns.get(error.get("sheet"), {})]
            if columns.get(field)
        }
        critical = error_column in critical_columns
        issues.append({"severity": "error" if critical else "warning",
                       "type": "formula_error" if critical else "formula_error_noncritical",
                       "message": "关键调研字段存在公式错误，需核实原始调研表。" if critical
                       else "辅助列存在公式错误，不阻断报告生成，但需修复调研模板。",
                       **error})
    module_status = survey.get("module_status", [])
    if module_status:
        for item in module_status:
            if item.get("module") in ("精确曝气", "智能碳源投加", "智能化学除磷", "内回流", "外回流与排泥") \
                    and item.get("applicable", "").strip() not in ("是", "否"):
                issues.append({"severity": "error", "type": "missing_module_applicability",
                               "message": f"模块“{item.get('module')}”必须明确选择是否适用。",
                               "source": item.get("source", {})})
    project_name_records = [
        record for record in survey.get("records", [])
        if any(marker in record.get("question", "") for marker in PROJECT_NAME_MARKERS)
    ]
    if not project_name_records or not any(record.get("answer") for record in project_name_records):
        issues.append({"severity": "error", "type": "missing_project_name",
                       "message": "项目名称缺失，无法形成正式报告。"})
    for record in survey.get("records", []):
        required = record.get("required", "")
        answer = record.get("answer", "")
        conditionally_skipped = record.get("condition", "").strip() == "无需填写"
        if any(marker in required for marker in REQUIRED_MARKERS) and not answer \
                and not conditionally_skipped and not not_applicable(record, module_status):
            issues.append({"severity": "warning", "type": "missing_required_answer",
                           "message": "重要调研项未填写；报告中不得推断。",
                           "question": record.get("question"), "source": record["source"]})
        state = applicable_state(record, module_status)
        if state is False and answer:
            issues.append({"severity": "warning", "type": "data_in_nonapplicable_module",
                           "message": "不适用模块中存在已填写数据；内容保留追溯，但不得进入报告。",
                           "question": record.get("question"), "source": record["source"]})
        if record.get("confirmation") == "to_confirm" and answer:
            issues.append({"severity": "warning", "type": "unconfirmed_answer",
                           "message": "该内容尚未确认，只能列入待确认事项。",
                           "question": record.get("question"), "source": record["source"]})
    counts = {
        "error": sum(issue["severity"] == "error" for issue in issues),
        "warning": sum(issue["severity"] == "warning" for issue in issues),
    }
    payload = {"source_file": survey.get("source_file"), "issue_count": len(issues),
               "counts": counts, "can_continue": counts["error"] == 0, "issues": issues}
    Path(sys.argv[2]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
