#!/usr/bin/env python3
import hashlib
import json
from datetime import datetime
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def timestamp():
    return datetime.now().isoformat(timespec="seconds")


def month_label(year, value, index):
    try:
        month = int(value)
        if 1 <= month <= 12:
            return f"{int(year):04d}-{month:02d}"
    except (TypeError, ValueError):
        pass
    return f"{int(year):04d}-{index:02d}"
