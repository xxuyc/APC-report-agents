import unittest

from knowledge_center.core import LocalJsonRepository, build_retrieval_plan, resolve_project, search_structured
from knowledge_center.documents import search_documents
from knowledge_center.semantic import validate_semantic_results
from knowledge_center.tests.test_core import project


class RoutingAndSemanticTests(unittest.TestCase):
    def test_report_type_mismatch_allows_writing_but_blocks_numeric(self):
        repo = LocalJsonRepository()
        target = project("target", "target")
        reference = project("ref", "reference", report_types=["generate-survey-report"])
        repo.data["projects"] = [target, reference]
        repo.data["knowledge"] = [{"knowledge_id": "w", "project_id": "ref", "knowledge_type": "writing", "title": "approved writing", "content": "writing pattern", "reuse_status": "named_reference", "disclosure_mode": "named", "allowed_usages": ["writing"], "status": "active"}]
        repo.data["metrics"] = [{"project_id": "ref", "metric_id": "m", "value": 1, "unit": "kg/m3", "formula_version": "metrics-v1", "time_granularity": "daily", "qa_status": "passed", "reuse_status": "named_reference", "disclosure_mode": "named", "allowed_usages": ["numeric_comparison"], "status": "active"}]
        plan = build_retrieval_plan(repo, target, "generate-operation-analysis-report", query="writing", explicit_reference_ids=["ref"])
        found = search_structured(repo, plan)
        self.assertEqual(len(found["writing_references"]), 1)
        self.assertFalse(found["benchmark_data"])
        self.assertEqual(found["excluded_references"][0]["reason"], "report_type_mismatch")

    def test_create_pending_project_without_guessing_existing_project(self):
        repo = LocalJsonRepository()
        pending = resolve_project(repo, explicit_project_name="brand-new", create_pending=True)
        self.assertTrue(pending["project_id"].startswith("pending-"))
        self.assertEqual(pending["status"], "pending_confirmation")

    def test_document_search_enforces_named_usage(self):
        repo = LocalJsonRepository()
        repo.data["sources"] = [
            {"source_id": "ok", "project_id": "ref", "file_name": "approved report", "allowed_usages": ["writing"], "reuse_status": "named_reference", "disclosure_mode": "named"},
            {"source_id": "no", "project_id": "ref", "file_name": "private report", "allowed_usages": ["writing"], "reuse_status": "internal_reference", "disclosure_mode": "internal_only"},
        ]
        plan = {"query": "report", "reference_project_ids": ["ref"], "intents": ["writing_pattern"]}
        found = search_documents(repo, plan)
        self.assertEqual([x["source_id"] for x in found["documents"]], ["ok"])
        self.assertEqual(found["excluded_references"][0]["reason"], "reuse_not_named_reference")

    def test_semantic_results_cannot_escape_router_allowlist(self):
        results = [
            {"project_id": "ref", "asset_id": "a1", "content_type": "document"},
            {"project_id": "other", "asset_id": "a2", "content_type": "document"},
            {"project_id": "ref", "asset_id": "a1", "content_type": "structured_metric"},
        ]
        checked = validate_semantic_results(results, ["ref"], ["a1"])
        self.assertEqual(len(checked["accepted"]), 1)
        self.assertEqual({x["reason"] for x in checked["excluded"]}, {"project_outside_router_allowlist", "structured_metric_not_allowed_in_semantic_search"})


if __name__ == "__main__":
    unittest.main()
