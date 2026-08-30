import unittest

from knowledge_center.core import LocalJsonRepository, build_retrieval_plan, search_structured
from knowledge_center.tests.test_core import project


class MetricBoundaryTests(unittest.TestCase):
    def test_metric_definition_mismatch_is_excluded(self):
        repo = LocalJsonRepository()
        repo.data["projects"] = [project("target", "target"), project("ref", "reference")]
        common = {
            "metric_id": "energy_intensity", "value": 0.2, "unit": "kWh/m3",
            "formula_version": "metrics-v1", "time_granularity": "daily",
            "qa_status": "passed", "reuse_status": "named_reference",
            "disclosure_mode": "named", "allowed_usages": ["numeric_comparison"], "status": "active",
        }
        repo.data["metrics"] = [
            {**common, "project_id": "target", "metric_definition": "blower_energy / treated_water"},
            {**common, "project_id": "ref", "metric_definition": "plant_energy / treated_water"},
        ]
        plan = build_retrieval_plan(repo, repo.data["projects"][0], "generate-operation-analysis-report", intents=["benchmark_data"], explicit_reference_ids=["ref"])
        found = search_structured(repo, plan)
        self.assertFalse(found["benchmark_data"])
        self.assertEqual(found["excluded_references"][0]["reason"], "metric_definition_mismatch")

    def test_unit_mismatch_is_excluded(self):
        repo = LocalJsonRepository()
        repo.data["projects"] = [project("target", "target"), project("ref", "reference")]
        common = {"metric_id": "m", "value": 1, "formula_version": "metrics-v1", "time_granularity": "daily", "metric_definition": "same", "qa_status": "passed", "reuse_status": "named_reference", "disclosure_mode": "named", "allowed_usages": ["numeric_comparison"], "status": "active"}
        repo.data["metrics"] = [{**common, "project_id": "target", "unit": "kg/m3"}, {**common, "project_id": "ref", "unit": "mg/L"}]
        plan = build_retrieval_plan(repo, repo.data["projects"][0], "generate-operation-analysis-report", intents=["benchmark_data"], explicit_reference_ids=["ref"])
        found = search_structured(repo, plan)
        self.assertEqual(found["excluded_references"][0]["reason"], "unit_not_convertible")


if __name__ == "__main__":
    unittest.main()
