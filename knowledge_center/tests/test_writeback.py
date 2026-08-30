import json
import tempfile
import unittest
from pathlib import Path

from knowledge_center.writeback import writeback_operation_artifacts, writeback_survey_artifacts


class WritebackTests(unittest.TestCase):
    def test_operation_metrics_are_internal_until_reuse_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); run_dir = root / "run"; working = run_dir / "working"; working.mkdir(parents=True)
            store = root / "store.json"
            (working / "metrics.json").write_text(json.dumps({"analysis_year": 2025, "statistics": {"m": {"mean": 1.2}}}), encoding="utf-8")
            (working / "normalized-data.json").write_text(json.dumps({"metrics": {"m": {"label": "metric", "unit": "kg/m3", "aggregation": "mean"}}}), encoding="utf-8")
            manifest = {"run_id": "r1", "project_id": "p1", "agent_type": "generate-operation-analysis-report", "status": "completed", "skill_version": "0.1.0", "input_sha256": "source"}
            result = writeback_operation_artifacts(manifest, run_dir, store)
            data = json.loads(store.read_text(encoding="utf-8"))
            self.assertEqual(result["metrics"], 1)
            self.assertEqual(data["metrics"][0]["qa_status"], "passed")
            self.assertEqual(data["metrics"][0]["reuse_status"], "internal_reference")
            self.assertEqual(data["metrics"][0]["allowed_usages"], [])

    def test_survey_facts_are_pending_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); run_dir = root / "run"; working = run_dir / "working"; working.mkdir(parents=True)
            store = root / "store.json"
            facts = {"facts": [{"fact_id": "F1", "confirmation": "confirmed", "question": "q", "value": "v", "source_refs": [{"source_id": "s1"}]}]}
            (working / "facts.json").write_text(json.dumps(facts), encoding="utf-8")
            manifest = {"run_id": "r1", "project_id": "p1", "agent_type": "generate-survey-report", "status": "completed", "skill_version": "0.2.1"}
            result = writeback_survey_artifacts(manifest, run_dir, store)
            data = json.loads(store.read_text(encoding="utf-8"))
            self.assertEqual(result["knowledge_candidates"], 1)
            self.assertEqual(data["knowledge"][0]["status"], "pending_review")


if __name__ == "__main__":
    unittest.main()
