"""Register approved cross-project references in each Harness evidence model."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


def _id(prefix: str, *parts) -> str:
    raw = "|".join(str(x or "") for x in parts)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", raw).strip("-")[:48]
    return f"{prefix}-{slug or hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def approved_reference_evidence(snapshot):
    evidence = []
    for row in snapshot.get("case_references", []):
        evidence.append({
            "evidence_id": _id("KREF-CASE", row.get("project_id"), row.get("knowledge_id")),
            "reference_kind": "case", "project_id": row.get("project_id"),
            "project_name": row.get("project_name"), "source_id": row.get("source_id"),
            "knowledge_id": row.get("knowledge_id"), "title": row.get("title"),
            "content": row.get("content"), "disclosure_mode": row.get("disclosure_mode"),
        })
    for row in snapshot.get("benchmark_data", []):
        evidence.append({
            "evidence_id": _id("KREF-METRIC", row.get("project_id"), row.get("metric_id"), row.get("period"), row.get("formula_version")),
            "reference_kind": "benchmark", "project_id": row.get("project_id"),
            "project_name": row.get("project_name"), "source_id": row.get("source_id"),
            "metric_id": row.get("metric_id"), "metric_name": row.get("metric_name"),
            "value": row.get("value"), "unit": row.get("unit"), "period": row.get("period"),
            "time_granularity": row.get("time_granularity"), "formula_version": row.get("formula_version"),
            "metric_definition": row.get("metric_definition"), "data_boundary": row.get("data_boundary"),
        })
    return evidence


def register_survey_references(chapter_model_path, snapshot):
    model = _read(chapter_model_path)
    references = approved_reference_evidence(snapshot)
    model["reference_sources"] = [
        {**item, "original_source_id": item.get("source_id"), "source_id": item["evidence_id"]}
        for item in references
    ]
    model["knowledge_context"] = {
        "snapshot_sha256": snapshot.get("sha256"),
        "writing_reference_count": len(snapshot.get("writing_references", [])),
        "method_reference_count": len(snapshot.get("method_references", [])),
        "reference_project_ids": snapshot.get("retrieval_plan", {}).get("reference_project_ids", []),
    }
    _write(chapter_model_path, model)
    return model["reference_sources"]


def register_operation_references(analysis_model_path, snapshot):
    model = _read(analysis_model_path)
    references = approved_reference_evidence(snapshot)
    known = {item.get("evidence_id") for item in model.get("evidence", [])}
    model.setdefault("evidence", []).extend(item for item in references if item["evidence_id"] not in known)
    model["knowledge_context"] = {
        "snapshot_sha256": snapshot.get("sha256"),
        "reference_project_ids": snapshot.get("retrieval_plan", {}).get("reference_project_ids", []),
        "writing_references": snapshot.get("writing_references", []),
        "method_references": snapshot.get("method_references", []),
        "case_references": snapshot.get("case_references", []),
        "benchmark_summaries": snapshot.get("benchmark_summaries", []),
        "registered_evidence": references,
    }
    _write(analysis_model_path, model)
    return references
