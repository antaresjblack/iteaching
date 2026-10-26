import hashlib
import re
import subprocess
from pathlib import Path

BLOCKED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "runtime",
    "outputs",
    "uploads",
    "data",
    "__pycache__",
}
EXTENSIONS = {".py", ".ts", ".vue", ".js", ".md", ".json", ".toml", ".yaml", ".yml"}


def redact(text):
    text = re.sub(
        r"\b(?:sk-[A-Za-z0-9_-]{12,}|LTAI[A-Za-z0-9]{12,})\b", "[REDACTED]", text
    )
    return re.sub(
        r"(?im)((?:api[_-]?key|secret|password|token)\s*[=:]\s*)[\"\'][^\"\'\r\n]{8,}[\"\']",
        r'\1"[REDACTED]"',
        text,
    )


class Sources:
    def __init__(self, root, names):
        self.root = Path(root).resolve()
        self.files = {}
        self.hashes = {}
        if not 1 <= len(names) <= 8:
            raise ValueError("请选择1至8个源码或测试文件")
        for name in names:
            relative = Path(name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or any(
                    part.lower() in BLOCKED or part.startswith(".env")
                    for part in relative.parts
                )
            ):
                raise ValueError("文件路径不在允许范围内")
            path = (self.root / relative).resolve()
            if (
                not path.is_relative_to(self.root)
                or path.suffix.lower() not in EXTENSIONS
                or not path.is_file()
            ):
                raise ValueError("只允许仓库内指定的文本源码文件")
            if any(
                part.lower() in BLOCKED or part.startswith(".env")
                for part in path.relative_to(self.root).parts
            ):
                raise ValueError("解析后的路径位于禁止目录")
            if path.stat().st_size > 60000:
                raise ValueError("单个文件过大，请缩小检查范围")
            raw = path.read_text(encoding="utf-8-sig")
            key = relative.as_posix()
            self.files[key] = redact(raw)
            self.hashes[key] = hashlib.sha256(raw.encode()).hexdigest()
        if sum(map(len, self.files.values())) > 70000:
            raise ValueError("输入文件总量过大，请分批检查")

    def read(self, path):
        if path not in self.files:
            return "拒绝读取：只能使用任务给出的精确文件路径。"
        return "\n".join(
            f"{i}: {line}" for i, line in enumerate(self.files[path].splitlines(), 1)
        )

    def diff(self):
        result = subprocess.run(
            [
                "git",
                "--no-pager",
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "HEAD",
                "--",
                *self.files,
            ],
            cwd=self.root,
            capture_output=True,
            timeout=10,
        )
        if result.returncode:
            return "无法读取Git差异，请以指定源码为准。"
        return (
            redact(result.stdout.decode("utf-8", errors="replace"))[:18000]
            or "所选文件没有相对HEAD的未提交差异。"
        )
