#!/usr/bin/env python3
import argparse
from pathlib import Path
from common import sha256, timestamp, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--reference")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    items = []
    for source_type, value, usage in (
        ("operation_excel", args.input, "fact_source"),
        ("mapping_adapter", args.adapter, "configuration"),
        ("analysis_profile", args.profile, "configuration"),
        ("reference_report", args.reference, "provisional_golden"),
    ):
        if not value:
            continue
        path = Path(value).resolve()
        if not path.is_file():
            raise SystemExit(f"Source does not exist: {path}")
        items.append({"source_id": f"S-{len(items)+1:03d}", "source_type": source_type,
                      "usage": usage, "file_name": path.name, "path": str(path),
                      "size": path.stat().st_size, "sha256": sha256(path)})
    write_json(args.output, {"schema_version": "0.1", "created_at": timestamp(), "sources": items})


if __name__ == "__main__":
    main()
