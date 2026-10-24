"""On-demand comparison synthesis; cache keyed by current evaluation content."""

import hashlib
import json
import sys
import threading
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[3]
_lock = threading.Lock()
PROMPT_VERSION = "comparison-v2"


def analyze(payload: dict, generate: bool = False) -> dict | None:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    if len(encoded) > 120000:
        raise HTTPException(422, "评价资料过长，请精简评语后重试")
    key = hashlib.sha256((PROMPT_VERSION + encoded).encode()).hexdigest()
    directory = ROOT / "runtime" / "comparison"
    path = directory / (key + ".json")

    def cached():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    existing = cached()
    if existing is not None or not generate:
        return existing
    if not _lock.acquire(blocking=False):
        raise HTTPException(409, "综合分析正在生成，请稍后刷新")
    try:
        existing = cached()
        if existing is not None:
            return existing
        # AI package lives alongside backend/ in the complete repository.
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from iteaching_ai.provider import ModelProvider

        try:
            result = ModelProvider().generate("comparison_analysis", json.loads(encoded))
        except Exception:
            raise HTTPException(502, "综合分析生成失败，请稍后重试") from None
        text = result.get("analysis") if isinstance(result, dict) else None
        if not isinstance(text, str) or not text.strip() or len(text) > 6000:
            raise HTTPException(502, "综合分析返回格式不正确，请重试")
        from app.services.recordings import DIMENSION_LABELS, redact_text

        for name, label in DIMENSION_LABELS.items():
            text = text.replace(name, label)
        output = {"analysis": redact_text(text.strip()), "version": PROMPT_VERSION}
        directory.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)
        return output
    finally:
        _lock.release()
