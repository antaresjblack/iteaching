import json
import unittest
from unittest.mock import patch, MagicMock
from project_agents.llm import BudgetLLM


class BudgetTests(unittest.TestCase):
    def test_no_extra_http_after_budget(self):
        model = BudgetLLM(
            "test",
            "https://example.invalid/v1/chat/completions",
            "not-a-real-key",
            lambda *args: None,
            max_calls=1,
        )
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            }
        ).encode()
        with patch("project_agents.llm.urlopen", return_value=response) as call:
            self.assertEqual(model.call("test"), "ok")
            with self.assertRaises(RuntimeError):
                model.call("test")
            self.assertEqual(call.call_count, 1)
            body = json.loads(call.call_args.args[0].data)
            self.assertIn("Observation:", body["stop"])
        self.assertEqual(model.usage["total_tokens"], 5)

    def test_reject_long_input_without_call(self):
        model = BudgetLLM("test", "https://example.invalid", "fake", lambda *args: None)
        with self.assertRaises(RuntimeError):
            model.call("x" * 85001)
        self.assertEqual(model.calls, 0)


if __name__ == "__main__":
    unittest.main()
