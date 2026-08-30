"""Permission-aware metadata/keyword document retrieval."""

from __future__ import annotations

import re


def _items(value):
    if isinstance(value, list): return value
    if isinstance(value, str): return [x.strip() for x in re.split(r"[,，;；\n]", value) if x.strip()]
    return [] if value is None else [value]


def search_documents(repository, plan):
    query = plan.get("query", "").lower()
    keywords = [x for x in re.split(r"\s+|[,，;；]", query) if x]
    allowed_projects = set(plan.get("reference_project_ids", []))
    intents = set(plan.get("intents", []))
    usage_map = {"writing_pattern": "writing", "analysis_method": "method", "case_reference": "case", "benchmark_data": "numeric_comparison"}
    requested = {usage for intent, usage in usage_map.items() if intent in intents}
    documents, excluded = [], []
    for row in repository.list("sources"):
        if row.get("project_id") not in allowed_projects: continue
        haystack = f"{row.get('file_name','')} {row.get('source_usage','')} {row.get('locator','')}".lower()
        if keywords and not any(word in haystack for word in keywords): continue
        reason = None
        usages = set(_items(row.get("allowed_usages")))
        if row.get("reuse_status") != "named_reference": reason = "reuse_not_named_reference"
        elif row.get("disclosure_mode") != "named": reason = "disclosure_not_named"
        elif requested and not requested.intersection(usages): reason = "usage_not_allowed"
        if reason: excluded.append({"source_id": row.get("source_id"), "project_id": row.get("project_id"), "reason": reason})
        else: documents.append(row)
    return {"documents": documents, "excluded_references": excluded, "search_mode": "structured_metadata_and_keywords"}
