#!/usr/bin/env python3
"""Merge survey records and supporting evidence into a unified V0.2 fact model."""

import json
import re
import sys
from pathlib import Path


SEMANTIC_MARKERS = {
    "project_name": ("项目名称", "污水厂名称", "水厂名称"),
    "design_capacity": ("设计规模", "设计处理规模"),
    "actual_flow": ("日均处理水量", "实际处理水量", "当前处理水量"),
    "discharge_standard": ("排放标准", "出水标准"),
}


def applicability(record, statuses):
    module = record.get("module", "")
    sheet = record.get("source", {}).get("sheet", "")
    for item in statuses:
        if (module and module in item.get("module", "")) or item.get("module", "") in sheet:
            value = item.get("applicable", "").strip()
            if value == "否" or "不适用" in value:
                return False
            if value == "是":
                return True
    return True


def semantic_key(text):
    for key, markers in SEMANTIC_MARKERS.items():
        if any(marker in text for marker in markers):
            return key
    return ""


def normalized_value(value):
    result = re.sub(r"[\s，,；;。]", "", str(value or "")).lower()
    for unit in ("m³/d", "m3/d", "立方米/日", "吨/日"):
        result = result.replace(unit, "")
    return result


def comparison_value(key, text):
    text = str(text or "")
    patterns = {
        "project_name": r"(?:项目名称|污水处理厂名称|水厂名称)[为：:]?\s*([^，。；\n]+)",
        "design_capacity": r"(?:设计规模|设计处理规模)[为：:]?\s*([0-9.]+\s*万?\s*(?:m³/d|m3/d|立方米/日|吨/日|万)?)",
        "actual_flow": r"(?:日均处理水量|实际处理水量|当前处理水量)[为：:]?\s*([0-9.]+\s*万?\s*(?:m³/d|m3/d|立方米/日|吨/日|万)?)",
        "discharge_standard": r"(?:排放标准|出水标准)[为：:]?\s*([^，。；\n]+)",
    }
    match = re.search(patterns.get(key, r"$^"), text, flags=re.I)
    return normalized_value(match.group(1) if match else text)


def main():
    if len(sys.argv) != 5:
        raise SystemExit("Usage: build_fact_model.py survey.json supporting.json source-index.json OUTPUT.json")
    survey = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    supporting = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    source_index = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    source_by_name = {item["file_name"]: item for item in source_index.get("sources", [])}
    facts = []
    for record in survey.get("records", []):
        if not record.get("answer"):
            continue
        source = record["source"]
        indexed = source_by_name.get(source.get("workbook"), {})
        fact = {
            "fact_id": f"F-{len(facts) + 1:04d}", "role": record.get("role", "current_fact"),
            "confirmation": record.get("confirmation", "confirmed"),
            "module_applicable": applicability(record, survey.get("module_status", [])),
            "module": record.get("module", ""), "submodule": record.get("submodule", ""),
            "question_id": record.get("question_id", ""), "question": record.get("question", ""),
            "value": record.get("normalized_answer") or record.get("answer"),
            "semantic_key": semantic_key(record.get("question", "")),
            "source_refs": [{"source_id": indexed.get("source_id", ""), "workbook": source.get("workbook", ""),
                             "sheet": source.get("sheet", ""), "cell": source.get("answer_cell", "")}],
        }
        fact["eligible_for_current_state"] = (fact["module_applicable"] and fact["confirmation"] == "confirmed"
                                               and fact["role"] in ("background_fact", "current_fact", "problem"))
        fact["comparison_value"] = comparison_value(fact["semantic_key"], fact["value"]) if fact["semantic_key"] else ""
        facts.append(fact)

    for evidence in supporting.get("evidence", []):
        if evidence.get("usage") != "fact_source" or evidence.get("confirmation") != "confirmed":
            continue
        item = {
            "fact_id": f"F-{len(facts) + 1:04d}", "role": "background_fact", "confirmation": "confirmed",
            "module_applicable": True, "module": "补充资料", "submodule": "项目背景",
            "question_id": "", "question": "补充资料原文", "value": evidence.get("text", ""),
            "semantic_key": semantic_key(evidence.get("text", "")), "eligible_for_current_state": True,
            "source_refs": [{"source_id": evidence.get("source_id", ""), "document": evidence.get("source_file", ""),
                             "locator": evidence.get("locator", ""), "evidence_id": evidence.get("evidence_id", "")}],
        }
        item["comparison_value"] = comparison_value(item["semantic_key"], item["value"]) if item["semantic_key"] else ""
        facts.append(item)

    conflicts = []
    grouped = {}
    for fact in facts:
        if fact.get("semantic_key") and fact.get("eligible_for_current_state"):
            grouped.setdefault(fact["semantic_key"], []).append(fact)
    for key, items in grouped.items():
        values = {item.get("comparison_value") or normalized_value(item["value"]) for item in items if item.get("value")}
        if len(values) > 1:
            conflicts.append({"conflict_id": f"CF-{len(conflicts) + 1:03d}", "semantic_key": key,
                              "message": "不同正式来源对同一事实的记录不一致，未自动覆盖。",
                              "fact_ids": [item["fact_id"] for item in items],
                              "sources": [ref for item in items for ref in item.get("source_refs", [])]})
            for item in items:
                item["eligible_for_current_state"] = False
                item["confirmation"] = "conflict"

    payload = {"schema_version": "0.2", "sources": source_index.get("sources", []),
               "module_status": survey.get("module_status", []), "facts": facts, "conflicts": conflicts}
    Path(sys.argv[4]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
