import json
import tempfile
import time
import unittest
from pathlib import Path

from knowledge_center.core import FeishuBaseRepository, KnowledgeUnavailable


class CacheFallbackTests(unittest.TestCase):
    def repository(self, cache):
        repo = FeishuBaseRepository("app", "secret", "base", {"projects": "table"}, cache)
        repo._request = lambda *args, **kwargs: (_ for _ in ()).throw(KnowledgeUnavailable("offline"))
        return repo

    def test_fresh_cache_is_used_when_feishu_is_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "cache.json"
            cache.write_text(json.dumps({"cached_at": time.time(), "tables": {"projects": [{"project_id": "p"}]}}), encoding="utf-8")
            self.assertEqual(self.repository(cache).list("projects")[0]["project_id"], "p")

    def test_cache_older_than_24_hours_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "cache.json"
            cache.write_text(json.dumps({"cached_at": time.time() - 90000, "tables": {"projects": []}}), encoding="utf-8")
            with self.assertRaises(KnowledgeUnavailable):
                self.repository(cache).list("projects")


if __name__ == "__main__":
    unittest.main()
