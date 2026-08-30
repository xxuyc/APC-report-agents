#!/usr/bin/env python3
"""Create a claim-to-source manifest from the agent's drafted content."""

import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: build_traceability.py drafted-content.json traceability.json")
    content = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    claims = []
    for chapter in content.get("chapters", []):
        for item in chapter.get("claims", []):
            if not item.get("sources"):
                raise SystemExit(f"Claim without source: {item.get('text', '')}")
            claims.append({"chapter_id": chapter.get("chapter_id", ""),
                           "chapter": chapter["title"], **item})
    Path(sys.argv[2]).write_text(json.dumps({"schema_version": "0.2", "claims": claims},
                                           ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
