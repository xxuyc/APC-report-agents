import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_center.core import KnowledgeUnavailable
from knowledge_center.pipeline import prepare_snapshot


class KnowledgeModeTests(unittest.TestCase):
    def test_disabled_mode_never_opens_configured_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "snapshot.json"
            with patch("knowledge_center.pipeline.repository_from_options") as repository:
                snapshot = prepare_snapshot(
                    output=output,
                    project_id="p1",
                    project_name="Project 1",
                    agent_type="generate-survey-report",
                )
            repository.assert_not_called()
            self.assertEqual(snapshot["retrieval_plan"]["knowledge_status"], "disabled")
            self.assertTrue(output.is_file())

    def test_optional_mode_falls_back_when_connection_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "snapshot.json"
            with patch(
                "knowledge_center.pipeline.repository_from_options",
                side_effect=KnowledgeUnavailable("offline"),
            ):
                snapshot = prepare_snapshot(
                    output=output,
                    project_id="p1",
                    project_name="Project 1",
                    agent_type="generate-survey-report",
                    mode="optional",
                )
            plan = snapshot["retrieval_plan"]
            self.assertEqual(plan["knowledge_status"], "unavailable")
            self.assertEqual(plan["warning"], "offline")

    def test_required_mode_propagates_connection_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch(
                "knowledge_center.pipeline.repository_from_options",
                side_effect=KnowledgeUnavailable("offline"),
            ):
                with self.assertRaises(KnowledgeUnavailable):
                    prepare_snapshot(
                        output=Path(temp) / "snapshot.json",
                        project_id="p1",
                        project_name="Project 1",
                        agent_type="generate-survey-report",
                        mode="required",
                    )


if __name__ == "__main__":
    unittest.main()
