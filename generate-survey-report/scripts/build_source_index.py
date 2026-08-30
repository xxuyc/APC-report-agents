#!/usr/bin/env python3
"""Create a deterministic index for every source in a run snapshot."""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def classify(path):
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name in ("approved-report.docx", "人工定稿.docx"):
        return "approved_output", "style_reference"
    if "template" in name or "模板" in name:
        return "template", "excluded"
    if "修订" in name or "审核意见" in name or "样例" in name:
        return "review_feedback", "feedback_only"
    if suffix == ".xlsx":
        return "survey_excel", "fact_source"
    if suffix in (".docx", ".pdf", ".txt", ".md"):
        return "supporting_document", "fact_source"
    if suffix in (".jpg", ".jpeg", ".png", ".heic", ".webp"):
        return "photo_evidence", "evidence_only"
    if suffix in (".dwg", ".dxf"):
        return "drawing", "evidence_only"
    return "other", "evidence_only"


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: build_source_index.py SNAPSHOT_DIR OUTPUT.json")
    root = Path(sys.argv[1]).resolve()
    sources = []
    for index, path in enumerate(sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p).lower()), 1):
        source_type, usage = classify(path)
        stat = path.stat()
        sources.append({
            "source_id": f"S-{index:03d}", "file_name": path.name,
            "relative_path": str(path.relative_to(root)), "source_type": source_type, "usage": usage,
            "sha256": sha256(path), "size": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        })
    Path(sys.argv[2]).write_text(json.dumps({"schema_version": "0.2", "root": str(root), "sources": sources},
                                           ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
