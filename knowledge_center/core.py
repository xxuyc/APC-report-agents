"""Deterministic project routing and cross-project retrieval.

The module deliberately keeps structured facts separate from prose retrieval.
It can read a local JSON store for tests/offline work or the seven Feishu Base
tables through the Open Platform REST API.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from .input_detection import collect_input_tokens


TABLES = ("projects", "sources", "knowledge", "metrics", "requirements", "runs", "changes")
NUMERIC_SCORE_MIN = 70
REVIEW_SCORE_MIN = 50


class KnowledgeError(RuntimeError):
    code = "knowledge_error"

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.code, "message": str(self)}


class ProjectConfirmationRequired(KnowledgeError):
    code = "project_confirmation_required"

    def __init__(self, message: str, candidates: Iterable[dict[str, Any]] = ()):
        super().__init__(message)
        self.candidates = list(candidates)

    def as_dict(self) -> dict[str, Any]:
        result = super().as_dict()
        result["candidates"] = self.candidates
        return result


class KnowledgeUnavailable(KnowledgeError):
    code = "knowledge_unavailable"


class KnowledgeConflict(KnowledgeError):
    code = "knowledge_conflict"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def empty_store() -> dict[str, list[dict[str, Any]]]:
    return {name: [] for name in TABLES}


class LocalJsonRepository:
    """Small file-backed implementation of the Feishu Base contract."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path).resolve() if path else None
        if self.path and self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.data = {name: list(raw.get(name, [])) for name in TABLES}
        else:
            self.data = empty_store()

    def list(self, table: str) -> list[dict[str, Any]]:
        if table not in TABLES:
            raise KeyError(table)
        return [dict(item) for item in self.data[table]]

    def upsert(self, table: str, record: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
        keys = tuple(keys)
        rows = self.data[table]
        found = next((row for row in rows if all(row.get(k) == record.get(k) for k in keys)), None)
        if found is None:
            found = dict(record)
            rows.append(found)
        else:
            found.update(record)
        self.flush()
        return dict(found)

    def flush(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")


FIELD_MAP = {
    "projects": {
        "项目ID": "project_id", "项目名称": "project_name", "项目别名": "aliases",
        "项目类型": "project_type", "报告类型": "report_types", "处理工艺": "process",
        "设计规模": "design_scale", "规模档位": "scale_band", "排放标准": "discharge_standard",
        "地域": "region", "气候": "climate", "设备与成本边界": "equipment_boundary",
        "允许复用范围": "allowed_usages", "复用状态": "reuse_status", "披露方式": "disclosure_mode",
        "状态": "status",
    },
    "sources": {
        "资料ID": "source_id", "项目ID": "project_id", "文件名": "file_name", "文件链接": "file_url",
        "SHA-256": "sha256", "来源用途": "source_usage", "版本": "version", "复用状态": "reuse_status",
        "允许用途": "allowed_usages", "披露方式": "disclosure_mode", "证据定位": "locator", "状态": "status",
    },
    "knowledge": {
        "知识ID": "knowledge_id", "项目ID": "project_id", "类型": "knowledge_type", "标题": "title",
        "内容": "content", "关键词": "keywords", "允许用途": "allowed_usages", "复用状态": "reuse_status",
        "披露方式": "disclosure_mode", "来源ID": "source_id", "状态": "status", "版本": "version",
    },
    "metrics": {
        "项目ID": "project_id", "指标ID": "metric_id", "指标名称": "metric_name", "值": "value",
        "单位": "unit", "统计周期": "period", "时间粒度": "time_granularity", "公式版本": "formula_version",
        "指标定义": "metric_definition", "数据边界": "data_boundary", "证据来源": "source_id",
        "QA状态": "qa_status", "复用状态": "reuse_status", "允许用途": "allowed_usages",
        "披露方式": "disclosure_mode", "运行ID": "run_id", "状态": "status",
    },
    "requirements": {"记录ID": "item_id", "项目ID": "project_id", "类型": "item_type", "内容": "content", "状态": "status"},
    "runs": {"运行ID": "run_id", "项目ID": "project_id", "Agent类型": "agent_type", "状态": "status", "知识快照SHA-256": "knowledge_snapshot_sha256", "内容哈希": "content_hash"},
    "changes": {"变更ID": "change_id", "项目ID": "project_id", "变更前": "before", "变更后": "after", "来源": "source", "审批方式": "approval", "影响范围": "scope", "回归结果": "regression", "替代关系": "supersedes"},
}


class FeishuBaseRepository:
    """Seven-table Feishu Base adapter using only the Python standard library."""

    def __init__(self, app_id: str, app_secret: str, app_token: str, table_ids: dict[str, str], cache_path: str | Path | None = None):
        self.app_id, self.app_secret, self.app_token = app_id, app_secret, app_token
        self.table_ids = table_ids
        self.cache_path = Path(cache_path).resolve() if cache_path else None
        self._token: str | None = None

    def _request(self, method: str, url: str, payload: Any = None, token: bool = True) -> dict[str, Any]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token:
            headers["Authorization"] = f"Bearer {self._tenant_token()}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers, method=method), timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise KnowledgeUnavailable(f"飞书知识中心访问失败：{exc}") from exc
        if result.get("code", 0) != 0:
            raise KnowledgeUnavailable(f"飞书接口返回错误：{result.get('msg') or result.get('code')}")
        return result

    def _tenant_token(self) -> str:
        if self._token:
            return self._token
        result = self._request("POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal", {"app_id": self.app_id, "app_secret": self.app_secret}, token=False)
        self._token = result["tenant_access_token"]
        return self._token

    def _decode(self, table: str, fields: dict[str, Any]) -> dict[str, Any]:
        mapping = FIELD_MAP[table]
        return {mapping.get(key, key): value for key, value in fields.items()}

    def _encode(self, table: str, record: dict[str, Any]) -> dict[str, Any]:
        reverse = {value: key for key, value in FIELD_MAP[table].items()}
        return {reverse.get(key, key): value for key, value in record.items() if key not in {"record_id"}}

    def list(self, table: str) -> list[dict[str, Any]]:
        table_id = self.table_ids.get(table)
        if not table_id:
            return []
        try:
            rows, page_token = [], None
            while True:
                query = {"page_size": 500}
                if page_token:
                    query["page_token"] = page_token
                url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records?{urllib.parse.urlencode(query)}"
                result = self._request("GET", url)
                data = result.get("data", {})
                for item in data.get("items", []):
                    row = self._decode(table, item.get("fields", {})); row["record_id"] = item.get("record_id"); rows.append(row)
                if not data.get("has_more"): break
                page_token = data.get("page_token")
            self._write_cache(table, rows)
            return rows
        except KnowledgeUnavailable:
            if self.cache_path and self.cache_path.exists():
                try:
                    cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
                    if time.time() - float(cache.get("cached_at", 0)) <= 86400 and table in cache.get("tables", {}):
                        return cache["tables"][table]
                except (OSError, ValueError, json.JSONDecodeError):
                    pass
            raise

    def _write_cache(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not self.cache_path:
            return
        cache = {"cached_at": time.time(), "tables": {}}
        if self.cache_path.exists():
            try: cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError): pass
        cache.setdefault("tables", {})[table] = rows
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert(self, table: str, record: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
        existing = next((row for row in self.list(table) if all(row.get(k) == record.get(k) for k in keys)), None)
        table_id = self.table_ids[table]
        fields = self._encode(table, record)
        base = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"
        if existing and existing.get("record_id"):
            self._request("PUT", f"{base}/{existing['record_id']}", {"fields": fields})
        else:
            self._request("POST", base, {"fields": fields})
        return record


def repository_from_options(store_path: str | Path | None = None, allow_empty: bool = True):
    if store_path:
        return LocalJsonRepository(store_path)
    connection_path = Path(os.getenv("FEISHU_CONNECTION_FILE", Path(__file__).with_name("feishu-connection.local.json")))
    if connection_path.exists():
        connection = json.loads(connection_path.read_text(encoding="utf-8-sig"))
        if connection.get("provider") == "lark_cli":
            from .lark_cli_repository import LarkCliBaseRepository
            return LarkCliBaseRepository(
                connection["base_token"],
                connection.get("table_ids"),
                connection.get("identity", "bot"),
            )
    cli_base_token = os.getenv("FEISHU_CLI_BASE_TOKEN")
    if cli_base_token:
        from .lark_cli_repository import LarkCliBaseRepository
        return LarkCliBaseRepository(cli_base_token, identity=os.getenv("FEISHU_CLI_IDENTITY", "bot"))
    app_id, secret, token = (os.getenv("FEISHU_APP_ID"), os.getenv("FEISHU_APP_SECRET"), os.getenv("FEISHU_BASE_APP_TOKEN"))
    if app_id and secret and token:
        table_ids = {name: os.getenv(f"FEISHU_TABLE_{name.upper()}_ID", "") for name in TABLES}
        return FeishuBaseRepository(app_id, secret, token, table_ids, os.getenv("FEISHU_KNOWLEDGE_CACHE"))
    if allow_empty:
        return LocalJsonRepository()
    raise KnowledgeUnavailable("未提供本地知识库，也未配置飞书知识中心凭据。")


def _list(value: Any) -> list[Any]:
    if value is None: return []
    if isinstance(value, list): return value
    if isinstance(value, str): return [x.strip() for x in re.split(r"[,，;；\n]", value) if x.strip()]
    return [value]


def _active(row: dict[str, Any]) -> bool:
    return str(row.get("status", "active")).lower() not in {"deleted", "inactive", "superseded", "rejected"}


def resolve_project(repository, explicit_project_id: str | None = None, explicit_project_name: str | None = None, input_paths: Iterable[str | Path] = (), create_pending: bool = False) -> dict[str, Any]:
    projects = [p for p in repository.list("projects") if _active(p)]
    if explicit_project_id:
        exact = [p for p in projects if p.get("project_id") == explicit_project_id]
        if exact: return exact[0]
        pending = {"project_id": explicit_project_id, "project_name": explicit_project_name or explicit_project_id, "status": "pending_confirmation", "aliases": []}
        if create_pending: repository.upsert("projects", pending, ("project_id",))
        return pending
    tokens = collect_input_tokens(input_paths)
    if explicit_project_name: tokens.add(explicit_project_name.strip().lower())
    matches = []
    for project in projects:
        names = [project.get("project_name", ""), project.get("project_id", ""), *_list(project.get("aliases"))]
        if any(str(name).lower() in token or token in str(name).lower() for token in tokens for name in names if name):
            matches.append(project)
    unique = {item.get("project_id"): item for item in matches}
    if len(unique) == 1: return next(iter(unique.values()))
    candidates = [{"project_id": x.get("project_id"), "project_name": x.get("project_name")} for x in unique.values()]
    if not candidates and create_pending:
        label = explicit_project_name or next(iter(tokens), "new-project")
        pending_id = "pending-" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:10]
        pending = {"project_id": pending_id, "project_name": label, "aliases": [], "status": "pending_confirmation"}
        repository.upsert("projects", pending, ("project_id",))
        return pending
    raise ProjectConfirmationRequired("无法唯一确定目标项目，请显式提供 project_id。", candidates)


INTENT_KEYWORDS = {
    "writing_pattern": ("写法", "表达", "结构", "措辞", "已审核"),
    "analysis_method": ("方法", "图表", "分析维度", "论证"),
    "case_reference": ("案例", "以前项目", "历史项目"),
    "benchmark_data": ("对标", "比较", "范围", "药耗", "能耗", "历史数据", "同类"),
}


def infer_intents(query: str | None, supplied: Iterable[str] = ()) -> list[str]:
    intents = ["current_fact"]
    intents.extend(x for x in supplied if x not in intents)
    query = query or ""
    for intent, words in INTENT_KEYWORDS.items():
        if any(word in query for word in words) and intent not in intents: intents.append(intent)
    if len(intents) == 1: intents.extend(["writing_pattern", "analysis_method"])
    return intents


def _same(a: Any, b: Any) -> bool:
    return bool(a not in (None, "") and b not in (None, "") and str(a).strip().lower() == str(b).strip().lower())


def similarity_score(target: dict[str, Any], reference: dict[str, Any], context: dict[str, Any] | None = None) -> tuple[int, dict[str, int], list[str]]:
    context = context or {}; parts, missing = {}, []
    checks = (("process", 25), ("scale_band", 20), ("discharge_standard", 15), ("time_granularity", 15), ("formula_version", 15), ("equipment_boundary", 5), ("region", 5))
    for field, points in checks:
        left = context.get(field, target.get(field)); right = reference.get(field)
        if left in (None, "") or right in (None, ""): missing.append(field); parts[field] = 0
        else: parts[field] = points if _same(left, right) else 0
    return sum(parts.values()), parts, missing


def build_retrieval_plan(repository, target: dict[str, Any], agent_type: str, query: str | None = None, intents: Iterable[str] = (), explicit_reference_ids: Iterable[str] = (), context: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved_intents = infer_intents(query, intents); explicit = set(explicit_reference_ids)
    candidates = []
    for project in repository.list("projects"):
        if not _active(project) or project.get("project_id") == target.get("project_id"): continue
        report_types = _list(project.get("report_types"))
        hard = []
        if report_types and agent_type not in report_types: hard.append("report_type_mismatch")
        score, breakdown, missing = similarity_score(target, project, context)
        if explicit and project.get("project_id") not in explicit: continue
        candidates.append({"project_id": project.get("project_id"), "project_name": project.get("project_name"), "score": score, "score_breakdown": breakdown, "missing_metadata": missing, "hard_exclusions": hard, "explicit": project.get("project_id") in explicit})
    candidates.sort(key=lambda x: (-x["score"], str(x["project_id"])))
    selected = [x for x in candidates if x["explicit"] or x["score"] >= REVIEW_SCORE_MIN]
    return {
        "schema_version": "1.0", "target_project_id": target["project_id"], "agent_type": agent_type,
        "query": query or "", "intents": resolved_intents,
        "reference_project_ids": [x["project_id"] for x in selected],
        "reference_project_type": target.get("project_type"),
        "allowed_usages": ["adapt_writing", "reuse_method", "named_case_reference", "numeric_comparison"],
        "candidates": candidates,
    }


def _named_allowed(row: dict[str, Any], usage: str) -> tuple[bool, str | None]:
    if row.get("reuse_status") != "named_reference": return False, "reuse_not_named_reference"
    if row.get("disclosure_mode") != "named": return False, "disclosure_not_named"
    usages = set(_list(row.get("allowed_usages")))
    if usage not in usages: return False, "usage_not_allowed"
    return True, None


def _keyword_match(row: dict[str, Any], query: str) -> bool:
    if not query: return True
    terms = [x.lower() for x in re.split(r"\s+|[,，;；]", query) if x]
    terms.extend(word.lower() for words in INTENT_KEYWORDS.values() for word in words if word in query)
    haystack = " ".join(str(row.get(k, "")) for k in ("title", "content", "keywords", "metric_name", "metric_id")).lower()
    return not terms or any(term in haystack for term in terms)


def search_structured(repository, plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    target_id, reference_ids = plan["target_project_id"], set(plan["reference_project_ids"])
    result = {"current_project_evidence": [], "writing_references": [], "method_references": [], "case_references": [], "benchmark_data": [], "excluded_references": []}
    for row in repository.list("knowledge"):
        if not _active(row) or not _keyword_match(row, plan.get("query", "")): continue
        if row.get("project_id") == target_id:
            result["current_project_evidence"].append(row); continue
        if row.get("project_id") not in reference_ids: continue
        kind = row.get("knowledge_type")
        mapping = {"writing": ("writing_references", "writing"), "writing_pattern": ("writing_references", "writing"), "method": ("method_references", "method"), "analysis_method": ("method_references", "method"), "case": ("case_references", "case")}
        if kind not in mapping: continue
        bucket, usage = mapping[kind]; ok, reason = _named_allowed(row, usage)
        if ok: result[bucket].append(row)
        else: result["excluded_references"].append({"kind": kind, "id": row.get("knowledge_id"), "project_id": row.get("project_id"), "reason": reason})
    candidates = {x["project_id"]: x for x in plan.get("candidates", [])}
    metric_rows = repository.list("metrics")
    target_metrics = defaultdict(list)
    for current in metric_rows:
        if _active(current) and current.get("project_id") == target_id:
            target_metrics[current.get("metric_id")].append(current)
    for row in metric_rows:
        if not _active(row) or row.get("project_id") not in reference_ids: continue
        candidate = candidates.get(row.get("project_id"), {})
        reason = None
        if candidate.get("hard_exclusions"): reason = candidate["hard_exclusions"][0]
        elif candidate.get("score", 0) < NUMERIC_SCORE_MIN: reason = "similarity_score_below_70"
        elif candidate.get("missing_metadata"): reason = "missing_key_metadata"
        elif row.get("qa_status") != "passed": reason = "qa_not_passed"
        else:
            comparable = target_metrics.get(row.get("metric_id"), [])
            if comparable:
                current = comparable[0]
                if current.get("metric_definition") and row.get("metric_definition") and current.get("metric_definition") != row.get("metric_definition"):
                    reason = "metric_definition_mismatch"
                elif current.get("unit") and row.get("unit") and current.get("unit") != row.get("unit"):
                    reason = "unit_not_convertible"
                elif current.get("formula_version") and row.get("formula_version") and current.get("formula_version") != row.get("formula_version"):
                    reason = "formula_version_mismatch"
        if not reason:
            ok, reason = _named_allowed(row, "numeric_comparison")
        if reason:
            result["excluded_references"].append({"kind": "metric", "id": row.get("metric_id"), "project_id": row.get("project_id"), "reason": reason}); continue
        result["benchmark_data"].append(row)
    for key in result:
        result[key].sort(key=lambda x: (str(x.get("project_id", "")), str(x.get("knowledge_id", x.get("metric_id", "")))))
    return result


def summarize_benchmarks(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row.get("metric_id"), row.get("unit"), row.get("formula_version"), row.get("time_granularity"))].append(row)
    summaries = []
    for key, items in groups.items():
        values = [float(x["value"]) for x in items if isinstance(x.get("value"), (int, float)) or str(x.get("value", "")).replace(".", "", 1).isdigit()]
        if not values: continue
        n = len(values)
        label = "历史项目案例值" if n == 1 else "两个参考项目的取值范围" if n == 2 else f"{n}个参考项目样本统计"
        summary = {"metric_id": key[0], "unit": key[1], "formula_version": key[2], "time_granularity": key[3], "sample_count": n, "wording": label, "min": min(values), "max": max(values), "projects": [x.get("project_id") for x in items]}
        if n >= 3: summary["median"] = median(values)
        summaries.append(summary)
    return summaries


def build_knowledge_snapshot(repository, plan: dict[str, Any]) -> dict[str, Any]:
    results = search_structured(repository, plan)
    project_names = {item.get("project_id"): item.get("project_name") for item in plan.get("candidates", [])}
    for bucket in ("writing_references", "method_references", "case_references", "benchmark_data"):
        for item in results[bucket]:
            item.setdefault("project_name", project_names.get(item.get("project_id")))
    snapshot = {"schema_version": "1.0", "created_at": _now(), "retrieval_plan": plan, **results, "benchmark_summaries": summarize_benchmarks(results["benchmark_data"])}
    hash_basis = {key: value for key, value in snapshot.items() if key not in {"created_at", "sha256"}}
    snapshot["sha256"] = _sha(hash_basis)
    return snapshot


def writeback_run(repository, run: dict[str, Any]) -> dict[str, Any]:
    basis = {key: value for key, value in run.items() if key not in {"record_id", "content_hash", "updated_at"}}
    record = {**basis, "content_hash": _sha(basis), "updated_at": _now()}
    return repository.upsert("runs", record, ("run_id", "agent_type", "content_hash"))
