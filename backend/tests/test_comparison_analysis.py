import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services import comparison_analysis as service

for parent in Path(__file__).resolve().parents:
    if (parent / "iteaching_ai").is_dir():
        sys.path.insert(0, str(parent))
        break


def test_cache_and_invalidation(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ROOT", tmp_path)
    with patch("iteaching_ai.provider.ModelProvider") as provider:
        provider.return_value.generate.return_value = {"analysis": "pre_assessment需要关注"}
        assert service.analyze({"reviews": []}) is None
        first = service.analyze({"reviews": []}, True)
        assert "前测" in first["analysis"]
        assert service.analyze({"reviews": []}, True) == first
        assert provider.return_value.generate.call_count == 1
        assert service.analyze({"reviews": ["新评语"]}) is None
        service.analyze({"reviews": ["新评语"]}, True)
        assert provider.return_value.generate.call_count == 2


def test_failure_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ROOT", tmp_path)
    with patch("iteaching_ai.provider.ModelProvider") as provider:
        provider.return_value.generate.return_value = {"analysis": ""}
        with pytest.raises(HTTPException) as error:
            service.analyze({}, True)
        assert error.value.status_code == 502
        assert service.analyze({}) is None
