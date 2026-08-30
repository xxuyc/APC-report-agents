import base64
import json
import unittest
from unittest.mock import patch

from knowledge_center.lark_cli_repository import LarkCliBaseRepository


class LarkCliRepositoryTests(unittest.TestCase):
    def test_base64_transport_preserves_chinese(self):
        payload = {
            "ok": True,
            "data": {
                "data": [["selfbuilt-app-long-connection", "自建应用长期连接"]],
                "fields": ["记录ID", "内容"],
                "field_type_list": ["text", "text"],
                "record_id_list": ["rec_test"],
                "has_more": False,
            },
        }
        encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
        completed = type("Completed", (), {"stdout": encoded, "stderr": "", "returncode": 0})()
        repository = object.__new__(LarkCliBaseRepository)
        repository.command = ["lark-cli"]

        with patch("knowledge_center.lark_cli_repository.subprocess.run", return_value=completed) as run:
            result = repository._call("base", "+record-list")

        self.assertEqual(result["data"][0][1], "自建应用长期连接")
        self.assertEqual(run.call_args.args[0][-2:], ["--jq", "@base64"])


if __name__ == "__main__":
    unittest.main()
