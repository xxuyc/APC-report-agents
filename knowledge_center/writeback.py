"""QA-gated writeback of deterministic run facts."""

from __future__ import annotations

import json
from pathlib import Path

from .core import repository_from_options, writeback_run


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_record(manifest):
    return {
        "run_id": manifest.get("run_id"), "project_id": manifest.get("project_id"),
        "agent_type": manifest.get("agent_type"), "status": manifest.get("status"),
        "reference_project_ids": manifest.get("reference_project_ids", []),
        "retrieval_intents": manifest.get("retrieval_intents", []),
        "knowledge_snapshot_sha256": manifest.get("knowledge_snapshot_sha256"),
        "outputs": manifest.get("outputs", []), "qa": manifest.get("qa", manifest.get("visual_qa")),
    }


def writeback_operation_artifacts(manifest, run_dir, store_path=None):
    repository = repository_from_options(store_path, allow_empty=False)
    run = writeback_run(repository, _run_record(manifest))
    run_dir = Path(run_dir); metrics_path = run_dir / "working" / "metrics.json"; normalized_path = run_dir / "working" / "normalized-data.json"
    if not metrics_path.exists() or not normalized_path.exists(): return {"run": run, "metrics": 0}
    metrics, normalized = _read(metrics_path), _read(normalized_path)
    meta = normalized.get("metrics", {}); period = str(metrics.get("analysis_year") or normalized.get("analysis_year") or "")
    count = 0
    for metric_id, stats in metrics.get("statistics", {}).items():
        definition = meta.get(metric_id, {})
        if stats.get("mean") is None: continue
        record = {
            "project_id": manifest.get("project_id"), "metric_id": metric_id,
            "metric_name": definition.get("label", metric_id), "value": stats["mean"], "unit": definition.get("unit"),
            "period": period, "time_granularity": "monthly", "formula_version": f"operation-metrics-{manifest.get('skill_version','unknown')}",
            "metric_definition": definition.get("aggregation"), "data_boundary": manifest.get("input_sha256"),
            "source_id": f"{manifest.get('run_id')}:{metric_id}", "qa_status": "passed",
            "reuse_status": "internal_reference", "allowed_usages": [], "disclosure_mode": "internal_only",
            "run_id": manifest.get("run_id"), "status": "active",
        }
        repository.upsert("metrics", record, ("project_id", "metric_id", "period", "formula_version", "run_id")); count += 1
    return {"run": run, "metrics": count}


def writeback_survey_artifacts(manifest, run_dir, store_path=None):
    repository = repository_from_options(store_path, allow_empty=False)
    run = writeback_run(repository, _run_record(manifest))
    facts_path = Path(run_dir) / "working" / "facts.json"
    if not facts_path.exists(): return {"run": run, "knowledge_candidates": 0}
    count = 0
    for fact in _read(facts_path).get("facts", []):
        if fact.get("confirmation") != "confirmed": continue
        record = {
            "knowledge_id": f"{manifest.get('run_id')}:{fact.get('fact_id')}", "project_id": manifest.get("project_id"),
            "knowledge_type": "project_fact", "title": fact.get("question") or fact.get("semantic_key") or fact.get("fact_id"),
            "content": fact.get("value"), "allowed_usages": ["current_fact"], "reuse_status": "internal_reference",
            "disclosure_mode": "internal_only", "source_id": (fact.get("source_refs") or [{}])[0].get("source_id"),
            "status": "pending_review", "version": manifest.get("skill_version"), "run_id": manifest.get("run_id"),
        }
        repository.upsert("knowledge", record, ("knowledge_id", "version")); count += 1
    return {"run": run, "knowledge_candidates": count}
