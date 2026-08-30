import json
import tempfile
import unittest
from pathlib import Path

from knowledge_center.evidence import register_operation_references, register_survey_references


class EvidenceRegistrationTests(unittest.TestCase):
    def snapshot(self):
        return {
            "sha256": "abc", "retrieval_plan": {"reference_project_ids": ["history"]},
            "writing_references": [{"project_id": "history", "content": "style"}],
            "method_references": [],
            "case_references": [{"project_id": "history", "project_name": "历史厂", "knowledge_id": "case-1", "source_id": "src-1", "title": "案例", "content": "结论"}],
            "benchmark_data": [{"project_id": "history", "project_name": "历史厂", "metric_id": "m", "value": 1.2, "unit": "kg/m3", "period": "2025", "formula_version": "v1", "time_granularity": "monthly"}],
            "benchmark_summaries": [{"metric_id": "m", "sample_count": 1, "wording": "历史项目案例值"}],
        }

    def test_survey_registers_only_case_and_benchmark_as_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "chapter.json"; path.write_text(json.dumps({"chapters": []}), encoding="utf-8")
            refs = register_survey_references(path, self.snapshot())
            self.assertEqual(len(refs), 2)
            self.assertTrue(all(item["source_id"].startswith("KREF-") for item in refs))
            self.assertNotIn("style", path.read_text(encoding="utf-8"))

    def test_operation_adds_registered_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "analysis.json"; path.write_text(json.dumps({"evidence": []}), encoding="utf-8")
            refs = register_operation_references(path, self.snapshot())
            model = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(refs), 2)
            self.assertEqual(len(model["evidence"]), 2)
            self.assertEqual(model["knowledge_context"]["benchmark_summaries"][0]["sample_count"], 1)


if __name__ == "__main__":
    unittest.main()
