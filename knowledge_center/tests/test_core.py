import json
import tempfile
import unittest
from pathlib import Path

from knowledge_center.core import (
    LocalJsonRepository,
    ProjectConfirmationRequired,
    build_knowledge_snapshot,
    build_retrieval_plan,
    resolve_project,
    search_structured,
    summarize_benchmarks,
    writeback_run,
)


def project(project_id, name, **overrides):
    row = {
        "project_id": project_id, "project_name": name,
        "project_type": "municipal_wastewater",
        "report_types": ["generate-operation-analysis-report"],
        "process": "AAO", "scale_band": "50k-100k-m3d",
        "discharge_standard": "一级A", "time_granularity": "daily",
        "formula_version": "metrics-v1", "equipment_boundary": "whole_plant",
        "region": "华东", "status": "active",
    }
    row.update(overrides)
    return row


class KnowledgeCenterTests(unittest.TestCase):
    def repo(self, *, projects=None, knowledge=None, metrics=None):
        repo = LocalJsonRepository()
        repo.data["projects"] = projects or []
        repo.data["knowledge"] = knowledge or []
        repo.data["metrics"] = metrics or []
        return repo

    def test_ambiguous_project_requires_confirmation(self):
        repo = self.repo(projects=[project("p1", "城南一厂", aliases=["城南"]), project("p2", "城南二厂", aliases=["城南"])])
        with self.assertRaises(ProjectConfirmationRequired):
            resolve_project(repo, explicit_project_name="城南")

    def test_explicit_unknown_project_is_pending_not_guessed(self):
        row = resolve_project(self.repo(), "new-project", "新项目")
        self.assertEqual(row["status"], "pending_confirmation")

    def test_current_facts_and_historical_writing_are_separated(self):
        rows = [
            {"knowledge_id": "current", "project_id": "target", "knowledge_type": "fact", "content": "当前事实", "status": "active"},
            {"knowledge_id": "history", "project_id": "ref", "knowledge_type": "writing", "content": "历史写法", "reuse_status": "named_reference", "disclosure_mode": "named", "allowed_usages": ["writing"], "status": "active"},
        ]
        repo = self.repo(projects=[project("target", "目标"), project("ref", "参考")], knowledge=rows)
        plan = build_retrieval_plan(repo, repo.data["projects"][0], "generate-operation-analysis-report", explicit_reference_ids=["ref"])
        found = search_structured(repo, plan)
        self.assertEqual([x["knowledge_id"] for x in found["current_project_evidence"]], ["current"])
        self.assertEqual([x["knowledge_id"] for x in found["writing_references"]], ["history"])

    def test_reference_without_named_permission_is_excluded(self):
        row = {"knowledge_id": "private", "project_id": "ref", "knowledge_type": "case", "content": "案例", "reuse_status": "internal_reference", "disclosure_mode": "internal_only", "allowed_usages": ["case"], "status": "active"}
        repo = self.repo(projects=[project("target", "目标"), project("ref", "参考")], knowledge=[row])
        plan = build_retrieval_plan(repo, repo.data["projects"][0], "generate-operation-analysis-report", intents=["case_reference"], explicit_reference_ids=["ref"])
        found = search_structured(repo, plan)
        self.assertFalse(found["case_references"])
        self.assertEqual(found["excluded_references"][0]["reason"], "reuse_not_named_reference")

    def test_numeric_reference_requires_score_70_and_qa(self):
        metric = {"project_id": "ref", "metric_id": "chemical_usage", "value": 1.2, "unit": "kg/m3", "formula_version": "metrics-v1", "time_granularity": "daily", "qa_status": "passed", "reuse_status": "named_reference", "disclosure_mode": "named", "allowed_usages": ["numeric_comparison"], "status": "active"}
        low = project("ref", "\u53c2\u8003", process="SBR", scale_band="under-10k-m3d")
        repo = self.repo(projects=[project("target", "目标"), low], metrics=[metric])
        plan = build_retrieval_plan(repo, repo.data["projects"][0], "generate-operation-analysis-report", intents=["benchmark_data"], explicit_reference_ids=["ref"])
        found = search_structured(repo, plan)
        self.assertFalse(found["benchmark_data"])
        self.assertEqual(found["excluded_references"][0]["reason"], "similarity_score_below_70")

    def test_sample_wording_reflects_count(self):
        base = {"metric_id": "m", "unit": "kWh/m3", "formula_version": "v1", "time_granularity": "daily"}
        self.assertEqual(summarize_benchmarks([{**base, "project_id": "a", "value": 1}])[0]["wording"], "历史项目案例值")
        self.assertEqual(summarize_benchmarks([{**base, "project_id": "a", "value": 1}, {**base, "project_id": "b", "value": 2}])[0]["wording"], "两个参考项目的取值范围")
        summary = summarize_benchmarks([{**base, "project_id": x, "value": i} for i, x in enumerate("abc", 1)])[0]
        self.assertEqual(summary["sample_count"], 3)
        self.assertEqual(summary["median"], 2)

    def test_snapshot_hash_is_stable_and_writeback_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = LocalJsonRepository(Path(temp) / "store.json")
            repo.data["projects"] = [project("target", "目标")]
            plan = build_retrieval_plan(repo, repo.data["projects"][0], "generate-operation-analysis-report")
            self.assertEqual(build_knowledge_snapshot(repo, plan)["sha256"], build_knowledge_snapshot(repo, plan)["sha256"])
            record = {"run_id": "r1", "agent_type": "agent", "project_id": "target", "status": "completed"}
            writeback_run(repo, record); writeback_run(repo, record)
            self.assertEqual(len(repo.list("runs")), 1)


if __name__ == "__main__":
    unittest.main()
