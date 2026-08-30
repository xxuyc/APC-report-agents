#!/usr/bin/env python3
"""Validate the private release boundary without printing secret values."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "knowledge_center",
    "generate-operation-analysis-report/SKILL.md",
    "generate-survey-report/SKILL.md",
    "README.md",
    "RELEASE.md",
    "requirements.txt",
    "install.ps1",
    "install.sh",
)
FORBIDDEN_NAMES = {"feishu-connection.local.json", ".env"}
FORBIDDEN_PARTS = {
    ".venv", "node_modules", "survey-report-workspace", "operation-analysis-workspace",
    "runs", "outputs", "__pycache__",
}
SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
}
TEXT_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".ps1", ".sh", ".env"}


def candidate_files():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def main():
    issues = []
    for relative in REQUIRED:
        if not (ROOT / relative).exists():
            issues.append({"type": "missing_required", "path": relative})
    for path in candidate_files():
        relative = path.relative_to(ROOT)
        if path.name in FORBIDDEN_NAMES or any(part in FORBIDDEN_PARTS for part in relative.parts):
            issues.append({"type": "forbidden_path", "path": str(relative)})
            continue
        if path.suffix.lower() in {".xlsx", ".xls", ".pdf", ".pptx", ".ppt"}:
            if "assets" not in relative.parts:
                issues.append({"type": "raw_business_artifact", "path": str(relative)})
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {".gitignore", ".gitattributes"}:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for name, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    issues.append({"type": name, "path": str(relative)})
    result = {"status": "passed" if not issues else "failed", "issues": issues}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
