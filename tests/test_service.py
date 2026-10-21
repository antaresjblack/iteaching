import copy
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from iteaching_ai.service import AIService, RUBRIC
from iteaching_ai.provider import ProviderError
from iteaching_ai.server import make_handler


def classroom():
    return {"course_id": "c1", "lesson_id": "l1", "taught_at": "2026-10-17",
            "segments": [{"id": "s1", "start_seconds": 0, "end_seconds": 20,
                          "text": "今天学习二分查找，请同学们讨论。"}]}


class FakeProvider:
    def generate(self, task, payload):
        if task == "suggest":
            return {"suggestions": [{"indicator_id": "objectives", "problem": "目标表述需细化",
                     "action": "将目标改写为学生能完成的操作", "priority": "medium", "verification": "检查课末任务完成情况"}]}
        return {"summary": "测试评价", "indicators": [
            {"id": key, "status": "evaluated", "score": 50,
             "reason": "测试依据", "evidence": [{"segment_id": "s1", "quote": "今天学习二分查找"}]}
            for key in RUBRIC]}


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.live = AIService(provider=FakeProvider())

    def test_demo_has_no_fabricated_scores(self):
        service = AIService(mode="demo")
        e = service.evaluate(classroom())
        self.assertTrue(e["demo"])
        self.assertTrue(all(i["score"] is None for i in e["indicators"]))
        self.assertEqual(service.suggest({"evaluation": e})["suggestions"], [])

    def test_live_evaluation_and_suggestions(self):
        e = self.live.evaluate(classroom())
        self.assertFalse(e["demo"])
        self.assertEqual(len(self.live.suggest({"evaluation": e})["suggestions"]), 1)

    def test_fabricated_quote_rejected(self):
        class Bad(FakeProvider):
            def generate(self, task, payload):
                result = super().generate(task, payload)
                result["indicators"][0]["evidence"][0]["quote"] = "不存在的引文"
                return result
        with self.assertRaises(ProviderError):
            AIService(provider=Bad()).evaluate(classroom())

    def test_invalid_input(self):
        for field, value in [("segments", []), ("taught_at", "bad"), ("course_id", "")]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                data = classroom()
                data[field] = value
                self.live.evaluate(data)

    def test_invalid_time_and_duplicate_segment(self):
        data = classroom()
        data["segments"][0]["end_seconds"] = -1
        with self.assertRaises(ValueError):
            self.live.evaluate(data)
        data = classroom()
        data["segments"] *= 2
        with self.assertRaises(ValueError):
            self.live.evaluate(data)

    def pair(self):
        a = self.live.evaluate(classroom())
        data = classroom()
        data.update(lesson_id="l2", taught_at="2026-10-18")
        b = self.live.evaluate(data)
        b["indicators"][0]["score"] = 70
        return a, b

    def test_compare_sorts_and_detects_persistent_weakness(self):
        a, b = self.pair()
        result = self.live.compare({"evaluations": [b, a]})
        self.assertEqual(result["series"][0]["delta"], 20)
        self.assertEqual(result["series"][0]["trend"], "improved")
        self.assertEqual(len(result["persistent_weak_indicators"]), 5)

    def test_missing_score_not_zero(self):
        a, b = self.pair()
        b["indicators"][0].update(status="insufficient_evidence", score=None, evidence=[])
        result = self.live.compare({"evaluations": [a, b]})
        self.assertIsNone(result["series"][0]["delta"])
        self.assertEqual(result["series"][0]["trend"], "not_comparable")

    def test_incompatible_histories(self):
        for field, value in [("course_id", "other"), ("rubric_version", "v2"), ("lesson_id", "l1")]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                a, b = self.pair()
                b[field] = value
                self.live.compare({"evaluations": [a, b]})

    def test_boolean_score_rejected(self):
        a, b = self.pair()
        a["indicators"][0]["score"] = True
        with self.assertRaises(ValueError):
            self.live.compare({"evaluations": [a, b]})

    def test_unsupported_suggestion_rejected(self):
        class Bad(FakeProvider):
            def generate(self, task, payload):
                result = super().generate(task, payload)
                result["suggestions"][0]["indicator_id"] = "unknown"
                return result
        e = self.live.evaluate(classroom())
        with self.assertRaises(ProviderError):
            AIService(provider=Bad()).suggest({"evaluation": e})

    def test_http_contract(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(AIService(mode="demo")))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:" + str(server.server_port)
        try:
            with urlopen(base + "/health") as r:
                self.assertEqual(json.load(r)["data"]["mode"], "demo")
            req = Request(base + "/api/ai/evaluations", data=json.dumps(classroom()).encode())
            with urlopen(req) as r:
                self.assertTrue(json.load(r)["data"]["demo"])
            with self.assertRaises(HTTPError) as err:
                urlopen(Request(base + "/api/ai/evaluations", data=b"null"))
            self.assertEqual(err.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
