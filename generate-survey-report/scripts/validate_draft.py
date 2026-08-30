#!/usr/bin/env python3
"""Validate the Agent-to-Harness drafted-content contract."""

import json
import sys
from pathlib import Path


ALLOWED_KINDS = {"fact", "assessment", "requirement", "to_confirm"}
ALLOWED_STATUSES = {"completed", "insufficient_facts", "omitted_not_applicable"}
BANNED_PREFACES = ("调研表显示", "现场填写信息表明", "调研资料显示", "调研表记录")


def main():
    if len(sys.argv) != 4:
        raise SystemExit("Usage: validate_draft.py chapter-model.json drafted-content.json OUTPUT.json")
    model = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    draft = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    errors, warnings = [], []
    expected = {chapter["chapter_id"]: chapter for chapter in model.get("chapters", [])}
    allowed_fact_ids = {
        fact.get("fact_id")
        for chapter in model.get("chapters", [])
        for group in ("facts", "requirements")
        for fact in chapter.get(group, [])
    }
    allowed_source_ids = {
        ref.get("source_id")
        for chapter in model.get("chapters", [])
        for group in ("facts", "requirements")
        for fact in chapter.get(group, [])
        for ref in fact.get("source_refs", [])
        if ref.get("source_id")
    }
    allowed_source_ids.update(ref.get("source_id") for ref in model.get("reference_sources", []) if ref.get("source_id"))
    chapters = draft.get("chapters", [])
    actual = {chapter.get("chapter_id"): chapter for chapter in chapters}
    if not draft.get("title"):
        errors.append({"type": "missing_title", "message": "报告标题缺失。"})
    if len(actual) != len(chapters):
        errors.append({"type": "duplicate_or_missing_chapter_id", "message": "章节 ID 缺失或重复。"})
    for chapter_id, model_chapter in expected.items():
        chapter = actual.get(chapter_id)
        if not chapter:
            errors.append({"type": "missing_chapter", "chapter_id": chapter_id,
                           "message": f"缺少章节：{model_chapter['title']}"})
            continue
        status = chapter.get("status", "completed")
        if status not in ALLOWED_STATUSES:
            errors.append({"type": "invalid_chapter_status", "chapter_id": chapter_id, "status": status})
        paragraphs = chapter.get("paragraphs", [])
        if status == "completed" and model_chapter.get("facts") and not paragraphs:
            errors.append({"type": "empty_chapter", "chapter_id": chapter_id,
                           "message": "有事实依据的章节不得为空。"})
        claim_ids = set()
        for claim in chapter.get("claims", []):
            claim_id = claim.get("claim_id")
            if not claim_id or claim_id in claim_ids:
                errors.append({"type": "invalid_claim_id", "chapter_id": chapter_id})
            claim_ids.add(claim_id)
            if claim.get("kind") not in ALLOWED_KINDS:
                errors.append({"type": "invalid_claim_kind", "claim_id": claim_id})
            if claim.get("kind") == "requirement" and not any(
                    token in claim.get("text", "") for token in ("拟", "建议", "后续", "计划", "需")):
                errors.append({"type": "requirement_not_distinguished", "claim_id": claim_id,
                               "message": "建设要求必须使用拟、建议、后续、计划或需等措辞与现状事实区分。"})
            if not claim.get("sources"):
                errors.append({"type": "claim_without_source", "claim_id": claim_id,
                               "message": "无来源结论不得进入正式报告。"})
            for source in claim.get("sources", []):
                fact_id = source.get("fact_id")
                if not fact_id and not source.get("source_id"):
                    errors.append({"type": "unregistered_source", "claim_id": claim_id,
                                   "message": "V0.2 结论来源必须引用 fact_id 或 source_id。"})
                if fact_id and fact_id not in allowed_fact_ids:
                    errors.append({"type": "unknown_fact_source", "claim_id": claim_id, "fact_id": fact_id})
                source_id = source.get("source_id")
                if source_id and source_id not in allowed_source_ids:
                    errors.append({"type": "unknown_registered_source", "claim_id": claim_id, "source_id": source_id})
        for paragraph in paragraphs:
            if isinstance(paragraph, str):
                warnings.append({"type": "legacy_paragraph", "chapter_id": chapter_id,
                                 "message": "正文段落未显式关联 claim_ids。"})
                continue
            referenced = paragraph.get("claim_ids", [])
            if not referenced:
                errors.append({"type": "paragraph_without_claim", "chapter_id": chapter_id,
                               "paragraph_id": paragraph.get("paragraph_id")})
            unknown = [claim_id for claim_id in referenced if claim_id not in claim_ids]
            if unknown:
                errors.append({"type": "unknown_claim_reference", "chapter_id": chapter_id,
                               "claim_ids": unknown})
            text = paragraph.get("text", "") if isinstance(paragraph, dict) else str(paragraph)
            if any(prefix in text for prefix in BANNED_PREFACES):
                errors.append({"type": "mechanical_source_preface", "chapter_id": chapter_id,
                               "paragraph_id": paragraph.get("paragraph_id") if isinstance(paragraph, dict) else "",
                               "message": "正文应直接陈述专业事实，不使用机械化资料来源话术。"})
            if "12期" in text or "3期" in text:
                errors.append({"type": "nonstandard_phase_name", "chapter_id": chapter_id,
                               "message": "报告阶段名称应统一为“一、二期”和“三期”。"})
    result = {"schema_version": "0.2", "valid": not errors,
              "counts": {"error": len(errors), "warning": len(warnings)},
              "errors": errors, "warnings": warnings}
    Path(sys.argv[3]).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
