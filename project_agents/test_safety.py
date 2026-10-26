import tempfile
import unittest
from pathlib import Path
from project_agents.safety import Sources, redact


class SourceTests(unittest.TestCase):
    def test_allowlist_and_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ok.py").write_text("print(1)\n", encoding="utf-8")
            sources = Sources(root, ["ok.py"])
            self.assertEqual(sources.read("ok.py"), "1: print(1)")
            self.assertIn("拒绝", sources.read(".env"))
            for path in [
                "../outside.py",
                ".env",
                "runtime/key.py",
                str(root / "ok.py"),
            ]:
                with self.assertRaises(ValueError):
                    Sources(root, [path])

    def test_missing_or_oversize(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "large.py").write_text("a" * 60001)
            for name in ["missing.py", "large.py"]:
                with self.assertRaises(ValueError):
                    Sources(root, [name])

    def test_secrets_masked(self):
        self.assertNotIn("sk-abcdefghijklmno", redact('api_key="sk-abcdefghijklmno"'))
        self.assertNotIn("testpassword123", redact('password="testpassword123"'))


if __name__ == "__main__":
    unittest.main()
