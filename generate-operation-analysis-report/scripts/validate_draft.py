#!/usr/bin/env python3
import argparse
from common import read_json, write_json

BANNED = ["全年稳定达标", "稳定达标", "必然导致", "节能8%", "节能 8%", "降低5%", "降低 5%"]
UNCERTAIN = ["待确认", "尚未提供", "未提供", "缺少", "无法判断", "不能判断", "口径冲突", "需要复核", "需复核"]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--draft", required=True); p.add_argument("--model", required=True); p.add_argument("--output", required=True)
    a = p.parse_args(); draft, model = read_json(a.draft), read_json(a.model)
    evidence = {x["evidence_id"] for x in model.get("evidence", [])}
    allow_cross_plant = model.get("report_preferences", {}).get("allow_cross_plant_comparison", False)
    known_claims = {x["claim_id"] for x in model.get("suggested_claims", []) + model.get("suggested_requirements", [])}
    issues = []
    section_ids = {x["section_id"] for x in model["sections"]}
    for section in draft.get("sections", []):
        if section.get("section_id") not in section_ids:
            issues.append({"severity":"error","type":"unknown_section","value":section.get("section_id")})
        for para in section.get("paragraphs", []):
            text = para.get("text", "")
            for term in BANNED:
                if term in text: issues.append({"severity":"error","type":"unsupported_wording","term":term,"text":text})
            for term in UNCERTAIN:
                if term in text: issues.append({"severity":"error","type":"uncertain_content_in_body","term":term,"text":text})
            if not allow_cross_plant and "城南" in text and "城东" in text and any(term in text for term in ["高于", "低于", "差异", "更接近", "占比", "排名"]):
                issues.append({"severity":"error","type":"cross_plant_comparison_not_enabled","text":text})
            refs = para.get("evidence", [])
            if not refs and section.get("section_id") not in {"data_basis", "limitations"}:
                issues.append({"severity":"error","type":"claim_without_evidence","text":text})
            for ref in refs:
                if ref not in evidence and ref not in known_claims:
                    issues.append({"severity":"error","type":"unknown_evidence","value":ref,"text":text})
        for callout in section.get("callouts", []):
            if callout.get("kind") != "critical_input":
                issues.append({"severity":"error","type":"unsupported_callout_kind","value":callout.get("kind")})
    result = {"status":"failed" if any(i["severity"]=="error" for i in issues) else "passed", "issues":issues}
    write_json(a.output, result)
    if result["status"] == "failed": raise SystemExit(2)

if __name__ == "__main__": main()
