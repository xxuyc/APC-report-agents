"""Feishu Base repository backed by lark-cli user or self-built-app identity."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .core import FIELD_MAP, KnowledgeUnavailable, TABLES


TABLE_NAMES = {
    "projects": "项目台账",
    "sources": "资料与证据",
    "knowledge": "知识条目",
    "metrics": "项目指标事实",
    "requirements": "需求与反馈",
    "runs": "Agent运行",
    "changes": "知识变更",
}


class LarkCliBaseRepository:
    """Uses lark-cli's credential store; no app secret is stored in the repo."""

    def __init__(self, base_token: str, table_ids: dict[str, str] | None = None, identity: str = "bot"):
        self.base_token = base_token
        self.table_ids = table_ids or {}
        self.identity = identity
        self.cli = shutil.which("lark-cli")
        if not self.cli:
            raise KnowledgeUnavailable("未找到已安装的 lark-cli。")
        self.command = [self.cli]
        if os.name == "nt" and self.cli.lower().endswith((".cmd", ".bat")):
            npm_dir = Path(self.cli).parent
            run_script = npm_dir / "node_modules" / "@larksuite" / "cli" / "scripts" / "run.js"
            node = shutil.which("node") or str(npm_dir / "node.exe")
            if run_script.exists() and Path(node).exists():
                self.command = [node, str(run_script)]

    def _call(self, *args: str) -> dict[str, Any]:
        result = subprocess.run(
            [*self.command, *args, "--jq", "@base64"],
            capture_output=True,
            text=True,
            encoding="ascii",
            errors="replace",
        )
        try:
            encoded = result.stdout.strip().strip('"')
            payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeUnavailable(f"lark-cli 返回不可解析：{result.stderr or result.stdout}") from exc
        if result.returncode or not payload.get("ok"):
            message = payload.get("error", {}).get("message") or result.stderr or "未知错误"
            raise KnowledgeUnavailable(f"飞书 CLI 调用失败：{message}")
        return payload.get("data", {})

    def _table_id(self, table: str) -> str:
        return self.table_ids.get(table) or TABLE_NAMES[table]

    @staticmethod
    def _cell(value: Any, field_type: str) -> Any:
        if field_type == "select" and isinstance(value, list):
            return value[0] if value else None
        return value

    def list(self, table: str) -> list[dict[str, Any]]:
        if table not in TABLES:
            raise KeyError(table)
        offset, rows = 0, []
        while True:
            data = self._call("base", "+record-list", "--as", self.identity, "--base-token", self.base_token,
                              "--table-id", self._table_id(table), "--format", "json", "--limit", "200", "--offset", str(offset))
            fields, types = data.get("fields", []), data.get("field_type_list", [])
            mapping = FIELD_MAP[table]
            for index, cells in enumerate(data.get("data", [])):
                record = {mapping.get(field, field): self._cell(cells[position] if position < len(cells) else None, types[position] if position < len(types) else "")
                          for position, field in enumerate(fields)}
                ids = data.get("record_id_list", [])
                if index < len(ids): record["record_id"] = ids[index]
                rows.append(record)
            if not data.get("has_more"):
                return rows
            offset += len(data.get("data", []))

    def upsert(self, table: str, record: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
        keys = tuple(keys)
        existing = next((row for row in self.list(table) if all(row.get(key) == record.get(key) for key in keys)), None)
        reverse = {value: key for key, value in FIELD_MAP[table].items()}
        fields = {reverse.get(key, key): value for key, value in record.items() if key != "record_id" and value is not None}
        args = ["base", "+record-upsert", "--as", self.identity, "--base-token", self.base_token,
                "--table-id", self._table_id(table), "--json", json.dumps(fields, ensure_ascii=False)]
        if existing and existing.get("record_id"):
            args.extend(["--record-id", existing["record_id"]])
        self._call(*args)
        return dict(record)
