#!/usr/bin/env python3
"""Build a dynamic current-state chapter model from eligible V0.2 facts."""

import json
import sys
from pathlib import Path


SECTION_RULES = [
    {"key": "basis", "title": "调研范围及资料依据", "tokens": ("source_inventory",), "always": True},
    {"key": "overview", "title": "项目概况及工艺现状", "tokens": ("01项目基本信息", "02全厂工艺", "补充资料"), "always": True},
    {"key": "control", "title": "自控与数据基础", "tokens": ("03自控与数据",), "always": True},
    {"key": "aeration", "title": "精确曝气系统现状", "tokens": ("04精确曝气调研",), "module": "精确曝气"},
    {"key": "carbon", "title": "智能碳源投加系统现状", "tokens": ("05智能碳源投加调研",), "module": "智能碳源投加"},
    {"key": "phosphorus", "title": "智能化学除磷系统现状", "tokens": ("06智能化学除磷调研",), "module": "智能化学除磷"},
    {"key": "internal_recycle", "title": "内回流系统现状", "tokens": ("07内回流调研",), "module": "内回流"},
    {"key": "return_sludge", "title": "回流与排泥系统现状", "tokens": ("07内回流调研", "08外回流与排泥调研"), "module": "外回流与排泥"},
]


def is_applicable(module, statuses):
    for item in statuses:
        if item.get("module") == module:
            return item.get("applicable", "").strip() == "是"
    return True


def source_text(fact):
    return " ".join(str(value) for ref in fact.get("source_refs", []) for value in ref.values())


def relevant_issue(issue, tokens):
    sheet = str(issue.get("source", {}).get("sheet", issue.get("sheet", "")))
    return any(token in sheet for token in tokens if token != "source_inventory")


def main():
    if len(sys.argv) not in (4, 5):
        raise SystemExit("Usage: build_chapter_model.py facts.json validation.json chapter-model.json [golden-profile.json]")
    fact_model = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    validation = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    profile = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8")) if len(sys.argv) == 5 else {}
    approved_keys = set(profile.get("approved_chapter_keys", []))
    overrides = profile.get("module_applicability_overrides", {})
    statuses = fact_model.get("module_status", [])
    eligible = [fact for fact in fact_model.get("facts", [])
                if fact.get("confirmation") == "confirmed"
                and fact.get("role") in ("background_fact", "current_fact", "problem")
                and (fact.get("module_applicable") or overrides.get(fact.get("module")) is True)]
    requirements = [fact for fact in fact_model.get("facts", [])
                    if fact.get("role") == "target_requirement"
                    and fact.get("confirmation") == "confirmed"
                    and (fact.get("module_applicable") or overrides.get(fact.get("module")) is True)]
    chapters, number = [], int(profile.get("chapter_start", 1))

    for rule in SECTION_RULES:
        if approved_keys and rule["key"] not in approved_keys:
            continue
        applicable = overrides.get(rule.get("module")) if rule.get("module") in overrides else is_applicable(rule.get("module"), statuses)
        if rule.get("module") and not applicable and rule["key"] not in approved_keys:
            continue
        if rule["key"] == "basis":
            facts = [{"fact_id": f"SRC-{source['source_id']}", "role": "background_fact",
                      "confirmation": "confirmed", "value": source["file_name"],
                      "source_refs": [{"source_id": source["source_id"], "file": source["file_name"]}]}
                     for source in fact_model.get("sources", []) if source.get("usage") in ("fact_source", "evidence_only")]
        else:
            facts = [fact for fact in eligible if any(token in source_text(fact) or token in fact.get("module", "")
                                                      for token in rule["tokens"])]
        chapter_requirements = [fact for fact in requirements if any(
            token in source_text(fact) or token in fact.get("module", "") for token in rule["tokens"])] \
            if profile.get("allow_confirmed_requirements") else []
        issues = [issue for issue in validation.get("issues", []) if relevant_issue(issue, rule["tokens"])
                  and issue.get("type") != "data_in_nonapplicable_module"]
        if not facts and not issues and not chapter_requirements and not rule.get("always") and rule["key"] not in approved_keys:
            continue
        chapter_id = f"3.{number}"
        chapters.append({"chapter_id": chapter_id, "chapter_key": rule["key"],
                         "title": f"{chapter_id} {rule['title']}", "facts": facts, "to_confirm": issues,
                         "requirements": chapter_requirements,
                         "drafting_status": "ready" if facts else "insufficient_facts"})
        number += 1

    summary_facts = [fact for fact in eligible if fact.get("role") in ("problem", "current_fact")]
    conflict_issues = [{"severity": "warning", "type": "source_conflict", "message": item["message"],
                        "conflict_id": item["conflict_id"], "sources": item.get("sources", [])}
                       for item in fact_model.get("conflicts", [])]
    summary_id = f"3.{number}"
    chapters.append({"chapter_id": summary_id, "chapter_key": "summary",
                     "title": f"{summary_id} 主要问题、建设约束及待确认事项", "facts": summary_facts,
                     "to_confirm": conflict_issues, "drafting_status": "requires_synthesis"})
    payload = {"schema_version": "0.2.1", "report_scope": "current_state_and_constraints",
               "purpose": "基于已确认事实形成现状评估；项目金标准允许时，可将已确认建设需求作为后续要求单独表述。",
               "excluded_roles": ["to_confirm"], "golden_profile": profile or None, "chapters": chapters}
    Path(sys.argv[3]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
