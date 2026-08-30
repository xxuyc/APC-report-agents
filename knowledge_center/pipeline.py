"""Small integration helpers shared by both report Harnesses."""

from __future__ import annotations

import json
from pathlib import Path

from .core import (
    KnowledgeUnavailable,
    LocalJsonRepository,
    build_knowledge_snapshot,
    build_retrieval_plan,
    repository_from_options,
    resolve_project,
    writeback_run,
)


KNOWLEDGE_MODES = ("disabled", "optional", "required")


def normalize_knowledge_mode(mode: str | None = None, disabled: bool = False) -> str:
    """Resolve the public mode while preserving the old disable switch."""
    if disabled:
        return "disabled"
    resolved = mode or "disabled"
    if resolved not in KNOWLEDGE_MODES:
        raise ValueError(f"knowledge mode must be one of: {', '.join(KNOWLEDGE_MODES)}")
    return resolved


def _inactive_plan(project_id, project_name, agent_type, query, status, warning=None):
    plan = {
        "schema_version": "1.0",
        "target_project_id": project_id,
        "target_project_name": project_name,
        "agent_type": agent_type,
        "query": query or "",
        "intents": ["current_fact"],
        "reference_project_ids": [],
        "reference_project_type": None,
        "allowed_usages": [],
        "candidates": [],
        "knowledge_mode": "disabled" if status == "disabled" else "optional",
        "knowledge_status": status,
    }
    if warning:
        plan["warning"] = warning
    return plan


def prepare_snapshot(*, output: str | Path, project_id: str, project_name: str, agent_type: str,
                     input_paths=(), store_path=None, query=None, intents=(), reference_ids=(),
                     mode: str = "disabled", disabled: bool = False):
    mode = normalize_knowledge_mode(mode, disabled)
    if mode == "disabled":
        repo = LocalJsonRepository()
        plan = _inactive_plan(project_id, project_name, agent_type, query, "disabled")
    else:
        try:
            repo = repository_from_options(store_path, allow_empty=False)
            target = resolve_project(repo, project_id, project_name, input_paths)
            plan = build_retrieval_plan(repo, target, agent_type, query, intents, reference_ids)
            plan.update({"knowledge_mode": mode, "knowledge_status": "enabled"})
        except KnowledgeUnavailable as exc:
            if mode == "required":
                raise
            repo = LocalJsonRepository()
            plan = _inactive_plan(project_id, project_name, agent_type, query, "unavailable", str(exc))
    snapshot = build_knowledge_snapshot(repo, plan)
    path = Path(output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def writeback_manifest(manifest: dict, store_path=None):
    repo = repository_from_options(store_path, allow_empty=False)
    return writeback_run(repo, {
        "run_id": manifest.get("run_id"),
        "project_id": manifest.get("project_id"),
        "agent_type": manifest.get("agent_type"),
        "status": manifest.get("status"),
        "reference_project_ids": manifest.get("reference_project_ids", []),
        "retrieval_intents": manifest.get("retrieval_intents", []),
        "knowledge_snapshot_sha256": manifest.get("knowledge_snapshot_sha256"),
        "outputs": manifest.get("outputs", []),
        "qa": manifest.get("qa", manifest.get("visual_qa")),
    })
