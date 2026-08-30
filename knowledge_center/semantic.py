"""Aily semantic-search boundary. Structured metrics never enter this path."""

from __future__ import annotations


class SemanticScopeViolation(ValueError):
    pass


def validate_semantic_results(results, allowed_project_ids, allowed_asset_ids):
    project_allowlist, asset_allowlist = set(allowed_project_ids), set(allowed_asset_ids)
    accepted, excluded = [], []
    for item in results:
        reason = None
        if item.get("project_id") not in project_allowlist: reason = "project_outside_router_allowlist"
        elif item.get("asset_id") not in asset_allowlist: reason = "asset_outside_router_allowlist"
        elif item.get("content_type") == "structured_metric": reason = "structured_metric_not_allowed_in_semantic_search"
        if reason: excluded.append({**item, "reason": reason})
        else: accepted.append(item)
    return {"accepted": accepted, "excluded": excluded}


class AilySemanticProvider:
    """Protocol adapter placeholder; callers must supply an authenticated search callable."""

    def __init__(self, search_callable):
        self.search_callable = search_callable

    def search(self, query, *, allowed_project_ids, allowed_assets):
        asset_ids = [item["asset_id"] for item in allowed_assets if item.get("project_id") in set(allowed_project_ids)]
        raw = self.search_callable(query=query, asset_ids=asset_ids)
        return validate_semantic_results(raw, allowed_project_ids, asset_ids)
