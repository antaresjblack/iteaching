"""Integration test using real backend/database and fake paid AI providers."""

import copy
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.main import create_application
from app.models import (
    Course,
    ProcessingTask,
    Recording,
    Supervisor,
    Teacher,
)
from app.schemas.business import EvaluationResultInput

for parent in Path(__file__).resolve().parents:
    if (parent / "iteaching_ai").is_dir():
        sys.path.insert(0, str(parent))
        break
pytest.importorskip("iteaching_ai", reason="AI worker package is required for cross-project tests")
from iteaching_ai.service import RUBRIC, AIService  # noqa: E402
from iteaching_ai.worker import BackendError, backend_result, run_once  # noqa: E402


class FakeModel:
    def generate(self, task, payload):
        if task == "suggest":
            return {
                "suggestions": [
                    {
                        "indicator_id": "objectives",
                        "problem": "目标可细化",
                        "action": "明确学习成果",
                        "priority": "medium",
                        "verification": "课末检查",
                    }
                ]
            }
        return {
            "summary": "测试评价",
            "indicators": [
                {
                    "id": key,
                    "score": 80 if key == "objectives" else None,
                    "status": "evaluated" if key == "objectives" else "insufficient_evidence",
                    "reason": "目标有依据" if key == "objectives" else "未观察到充分依据",
                    "evidence": (
                        [{"segment_id": "s1", "quote": "学习目标"}] if key == "objectives" else []
                    ),
                }
                for key in RUBRIC
            ],
        }


class FakeASR:
    def submit(self, data):
        assert "/audio-signed?" in data["audio_url"]
        return {"task_id": "test-asr", "status": "PENDING"}

    def fetch(self, data):
        return {"status": "SUCCEEDED", **self.transcribe_file(__file__)}

    def transcribe_file(self, path):
        assert Path(path).is_file()
        return {
            "segments": [
                {"id": "s1", "start_seconds": 0, "end_seconds": 1, "text": "今天的学习目标"}
            ]
        }


def result_payload():
    transcript = FakeASR().transcribe_file(__file__)
    ai = AIService(provider=FakeModel())
    e = ai.evaluate(
        {
            "course_id": "1",
            "lesson_id": "r1",
            "taught_at": "2026-10-17",
            "segments": transcript["segments"],
        }
    )
    return backend_result(transcript, e, ai.suggest({"evaluation": e}))


def test_partial_scores_and_fabricated_overall():
    payload = result_payload()
    assert EvaluationResultInput.model_validate(payload).overall_score is None
    payload["overall_score"] = 80
    with pytest.raises(ValidationError):
        EvaluationResultInput.model_validate(payload)


def test_invalid_evidence_and_mismatched_scores():
    for change in ("quote", "score"):
        payload = result_payload()
        if change == "quote":
            payload["indicators"][1]["evidence"][0]["quote"] = "不存在"
        else:
            payload["dimension_scores"]["objectives"] = 99
        with pytest.raises(ValidationError):
            EvaluationResultInput.model_validate(payload)


@pytest.fixture
def backend(
    tmp_path,
    monkeypatch,
    testing_sessionmaker: sessionmaker[Session],
    db_override,
):
    monkeypatch.setenv("AI_AUDIO_STORAGE", "signed_backend")
    monkeypatch.setenv("AI_WORKER_STATE_DIR", str(tmp_path / "worker-state"))
    monkeypatch.setattr(settings, "ai_service_token", "worker-test-token")
    monkeypatch.setattr(settings, "audio_public_base_url", "https://audio.example.com")
    monkeypatch.setattr(settings, "audio_signing_key", "test-key-" * 8)
    sessions = testing_sessionmaker
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"fake-audio")
    with sessions() as db:
        supervisor = Supervisor(
            username="supervisor",
            password_hash="unused",
            is_active=True,
            employee_no="20001",
            name="测试督导",
            level="校级",
        )
        teacher = Teacher(
            username="teacher",
            password_hash="unused",
            is_active=True,
            employee_no="20002",
            name="测试教师",
        )
        db.add_all([supervisor, teacher])
        db.flush()
        course = Course(
            code="C-001",
            name="测试课堂",
            location="教学楼 A101",
            class_name="2026 级 1 班",
            schedules=[{"weekday": 1, "start_time": "08:00", "end_time": "09:40"}],
            teacher_id=teacher.id,
            teacher_name="测试教师",
        )
        db.add(course)
        db.flush()
        course_id = course.id
        for n in (1, 2):
            db.add(
                Recording(
                    id=f"r{n}",
                    course_id=course.id,
                    uploaded_by_id=supervisor.id,
                    uploaded_by_role="supervisor",
                    storage_path=str(audio),
                    original_filename="a.wav",
                    media_type="audio/wav",
                    recorded_at=datetime(2026, 10, n, tzinfo=UTC),
                    consent_at=datetime.now(UTC),
                    consent_version="test",
                    duration_seconds=2,
                )
            )
            db.add(ProcessingTask(id=f"t{n}", recording_id=f"r{n}", status="QUEUED", attempts=0))
        db.commit()
    app = create_application()
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: supervisor
    client = TestClient(app)

    class Adapter:
        def __init__(self):
            self.sent = []

        def request(self, path, body=None, claim=None, destination=None):
            headers = {"X-Service-Token": "worker-test-token"}
            if claim:
                headers["X-Task-Claim-Token"] = claim
            response = (
                client.get(path, headers=headers)
                if body is None
                else client.post(path, headers=headers, json=body)
            )
            if response.status_code >= 400:
                raise BackendError(response.status_code)
            if path.endswith("/result"):
                self.sent.append((path, copy.deepcopy(body), claim))
            if destination:
                Path(destination).write_bytes(response.content)
                return None
            return response.json()["data"]

    yield client, Adapter(), course_id
    client.close()


def test_worker_roundtrip_null_scores_calibration_and_history(backend):
    client, adapter, course_id = backend

    def convert(source, target):
        Path(target).write_bytes(Path(source).read_bytes())

    for _ in range(2):
        assert (
            run_once(adapter, FakeASR(), AIService(provider=FakeModel()), "test-worker", convert)
            == "succeeded"
        )
    path, payload, claim = adapter.sent[-1]
    assert adapter.request(path, payload, claim)["idempotent"] is True
    detail = client.get("/api/v1/recordings/r2/evaluation").json()["data"]
    assert detail["overall_score"] is None
    assert detail["dimension_scores"]["bridge_in"] is None
    assert detail["indicators"][1]["evidence"][0]["quote"] == "学习目标"
    assert detail["segments"][0]["role"] == "unknown"
    history = client.get(f"/api/v1/courses/{course_id}/comparison").json()["data"]
    assert history["delta"]["overall_score"] is None
    assert history["delta"]["dimension_scores"]["objectives"] == 0
    assert history["delta"]["dimension_scores"]["bridge_in"] is None
    response = client.post(
        f"/api/v1/evaluations/{detail['id']}/calibrations",
        json={"dimension_scores": {"objectives": 90}},
    )
    assert response.status_code == 201
    history = client.get(f"/api/v1/courses/{course_id}/comparison").json()["data"]
    assert history["delta"]["dimension_scores"]["objectives"] == 10
    assert (
        run_once(adapter, FakeASR(), AIService(provider=FakeModel()), "worker", convert) == "idle"
    )


def test_worker_failure_requeues(backend, monkeypatch):
    _, adapter, _ = backend

    def broken(*args):
        raise ValueError("bad media")

    monkeypatch.setattr(FakeASR, "submit", broken)
    assert (
        run_once(adapter, FakeASR(), AIService(provider=FakeModel()), "worker", broken) == "failed"
    )


def test_lease_and_foreign_claim_are_enforced(backend):
    _, adapter, _ = backend
    task = adapter.request("/api/v1/internal/tasks/claim", {"worker_id": "test"})
    prefix = f"/api/v1/internal/tasks/{task['task_id']}"
    assert adapter.request(prefix + "/lease", {}, task["claim_token"])["lease_expires_at"]
    with pytest.raises(BackendError) as error:
        adapter.request(prefix + "/result", result_payload(), "incorrect-claim")
    assert error.value.status == 409


def test_lost_ack_retries_identical_result_without_rescoring(backend, monkeypatch):
    _, adapter, _ = backend
    original = adapter.request
    dropped = False

    def unreliable(path, body=None, claim=None, destination=None):
        nonlocal dropped
        result = original(path, body, claim, destination)
        if path.endswith("/result") and not dropped:
            dropped = True
            raise BackendError()
        return result

    monkeypatch.setattr(adapter, "request", unreliable)
    monkeypatch.setattr("iteaching_ai.worker.time.sleep", lambda _: None)

    def convert(source, target):
        Path(target).write_bytes(b"fake")

    assert (
        run_once(adapter, FakeASR(), AIService(provider=FakeModel()), "worker", convert)
        == "succeeded"
    )
    assert len(adapter.sent) == 2
    assert adapter.sent[0][1] == adapter.sent[1][1]


def test_history_refuses_different_rubrics(backend):
    client, adapter, course_id = backend
    for n in (1, 2):
        task = adapter.request("/api/v1/internal/tasks/claim", {"worker_id": "test"})
        payload = result_payload()
        payload["rubric_version"] = f"test-rubric-{n}"
        adapter.request(
            f"/api/v1/internal/tasks/{task['task_id']}/result", payload, task["claim_token"]
        )
    result = client.get(f"/api/v1/courses/{course_id}/comparison").json()["data"]
    assert result["comparable"] is False
    assert all(v is None for v in result["delta"]["dimension_scores"].values())


def test_signed_audio_bound_to_claim_and_expiry(backend, monkeypatch):
    from urllib.parse import urlsplit

    client, adapter, _ = backend
    task = adapter.request("/api/v1/internal/tasks/claim", {"worker_id": "test"})
    prefix = f"/api/v1/internal/tasks/{task['task_id']}"
    with pytest.raises(BackendError):
        adapter.request(prefix + "/audio-url", {}, "wrong")
    signed = adapter.request(prefix + "/audio-url", {}, task["claim_token"])
    url = urlsplit(signed["audio_url"])
    path = url.path + "?" + url.query
    response = client.get(path)
    assert response.status_code == 200
    assert response.content == b"fake-audio"
    assert response.headers["cache-control"] == "no-store"
    assert client.get(path.replace("signature=", "signature=x")).status_code == 403
    assert client.get(path.replace(str(signed["expires"]), "1")).status_code == 403
    other = "t2" if task["task_id"] == "t1" else "t1"
    assert client.get(path.replace(task["task_id"], other)).status_code == 403
    adapter.request(prefix + "/failure", {"reason": "test"}, task["claim_token"])
    assert client.get(path).status_code == 403


def test_preflight_prevents_claim_when_unconfigured(backend, monkeypatch):
    _, adapter, _ = backend
    monkeypatch.setattr(settings, "audio_public_base_url", "")
    with pytest.raises(BackendError) as error:
        run_once(adapter, FakeASR(), AIService(provider=FakeModel()), "worker")
    assert error.value.status == 503
    task = adapter.request("/api/v1/internal/tasks/claim", {"worker_id": "test"})
    assert task["attempt"] == 1


def test_async_poll_does_not_resubmit(backend, monkeypatch):
    _, adapter, _ = backend

    class PendingASR(FakeASR):
        submits = 0
        polls = 0

        def submit(self, data):
            self.submits += 1
            return super().submit(data)

        def fetch(self, data):
            self.polls += 1
            if self.polls < 3:
                return {"status": "RUNNING"}
            return super().fetch(data)

    asr = PendingASR()
    monkeypatch.setattr("iteaching_ai.worker.time.sleep", lambda _: None)
    assert run_once(adapter, asr, AIService(provider=FakeModel()), "worker") == "succeeded"
    assert (asr.submits, asr.polls) == (1, 3)


def test_failure_is_terminal_and_records_stage(backend, monkeypatch):
    import os

    from iteaching_ai.provider import ProviderError

    client, adapter, _ = backend

    def fail(self, data):
        raise ProviderError("阿里云语音请求失败，HTTP 403；code=AccessDenied")

    monkeypatch.setattr(FakeASR, "submit", fail)
    assert run_once(adapter, FakeASR(), AIService(provider=FakeModel()), "worker") == "failed"
    status = client.get("/api/v1/recordings/r1/status").json()["data"]
    assert status["status"] == "FAILED"
    logs = list(Path(os.environ["AI_WORKER_STATE_DIR"]).glob("*.jsonl"))
    assert len(logs) == 1
    text = logs[0].read_text(encoding="utf-8")
    assert "提交转写" in text and "AccessDenied" in text
    assert "audio-signed" not in text


def test_submit_marker_survives_process_restart(tmp_path, monkeypatch):
    from iteaching_ai.diagnostics import Journal

    monkeypatch.setenv("AI_AUDIO_STORAGE", "signed_backend")
    monkeypatch.setenv("AI_WORKER_STATE_DIR", str(tmp_path))
    Journal("same-task").before_submit()
    with pytest.raises(ValueError, match="重复"):
        Journal("same-task").before_submit()


def test_diagnostic_redaction(monkeypatch):
    from iteaching_ai.diagnostics import safe_detail

    monkeypatch.setenv("DASHSCOPE_API_KEY", "secret-test-value")
    text = safe_detail("secret-test-value https://host/audio?signature=secret Bearer abc123")
    assert "secret-test-value" not in text and "signature" not in text and "abc123" not in text


def test_cloud_id_is_saved_before_query_failure(backend, monkeypatch):
    import os

    from iteaching_ai.provider import ProviderError

    _, adapter, _ = backend

    def fail(self, data):
        raise ProviderError("音频子任务失败；code=DownloadFailed")

    monkeypatch.setattr(FakeASR, "fetch", fail)
    monkeypatch.setattr("iteaching_ai.worker.time.sleep", lambda _: None)
    assert run_once(adapter, FakeASR(), AIService(provider=FakeModel()), "worker") == "failed"
    text = next(Path(os.environ["AI_WORKER_STATE_DIR"]).glob("*.jsonl")).read_text(encoding="utf-8")
    assert "test-asr" in text and "DownloadFailed" in text


def test_oss_roundtrip_without_public_backend(backend, monkeypatch):
    client, adapter, _ = backend
    monkeypatch.setenv("AI_AUDIO_STORAGE", "oss")
    monkeypatch.setattr(settings, "audio_public_base_url", "")
    actions = []

    class Storage:
        def new_key(self, name):
            return "iteaching-temp/fake.wav"

        def upload(self, key, source):
            import time

            assert Path(source).read_bytes() == b"fake-audio"
            actions.append("upload")
            return {
                "audio_url": "https://example.com/audio-signed?test",
                "expires": int(time.time()) + 7200,
            }

        def cleanup(self, key, journal):
            actions.append("cleanup")

    monkeypatch.setattr("iteaching_ai.worker.OSSAudio", Storage)
    assert run_once(adapter, FakeASR(), AIService(provider=FakeModel()), "worker") == "succeeded"
    assert actions == ["upload", "cleanup"]


def test_oss_upload_failure_never_submits_and_cleans(backend, monkeypatch):
    from iteaching_ai.provider import ProviderError

    _, adapter, _ = backend
    monkeypatch.setenv("AI_AUDIO_STORAGE", "oss")
    actions = []

    class Storage:
        def new_key(self, name):
            return "iteaching-temp/fake.wav"

        def upload(self, key, source):
            raise ProviderError("OSS上传失败：AccessDenied")

        def cleanup(self, key, journal):
            actions.append("cleanup")

    class NoASR:
        def submit(self, data):
            raise AssertionError("must not submit")

    monkeypatch.setattr("iteaching_ai.worker.OSSAudio", Storage)
    assert run_once(adapter, NoASR(), AIService(provider=FakeModel()), "worker") == "failed"
    assert actions == ["cleanup"]


def test_oss_requires_credentials_before_claim(backend, monkeypatch):
    _, adapter, _ = backend
    monkeypatch.setenv("AI_AUDIO_STORAGE", "oss")
    monkeypatch.setenv("OSS_REGION", "cn-beijing")
    monkeypatch.setenv("OSS_BUCKET_NAME", "test-bucket")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "")
    with pytest.raises(ValueError, match="OSS_ACCESS_KEY"):
        run_once(adapter, FakeASR(), AIService(provider=FakeModel()), "worker")
    assert adapter.request("/api/v1/internal/tasks/claim", {"worker_id": "test"})["attempt"] == 1


def test_suggestion_failure_preserves_evaluation_and_checkpoints(backend, monkeypatch):
    import os

    from iteaching_ai.provider import ProviderError

    client, adapter, _ = backend

    class BrokenSuggestions(FakeModel):
        def generate(self, task, payload):
            if task == "suggest":
                raise ProviderError("模型服务连接失败或超时")
            return super().generate(task, payload)

    assert (
        run_once(adapter, FakeASR(), AIService(provider=BrokenSuggestions()), "worker")
        == "succeeded"
    )
    detail = client.get("/api/v1/recordings/r1/evaluation").json()["data"]
    assert detail["dimension_scores"]["objectives"] == 80
    assert "建议暂不可用" in detail["overall_evidence"]
    artifacts = Path(os.environ["AI_WORKER_STATE_DIR"]) / "artifacts"
    assert len(list(artifacts.glob("*/evaluation.json"))) == 1
    assert len(list(artifacts.glob("*/transcript.json"))) == 1


def test_suggestions_only_receive_supported_indicators(backend):
    class MixedSuggestions(FakeModel):
        def generate(self, task, payload):
            result = super().generate(task, payload)
            if task == "suggest":
                assert payload["allowed_indicator_ids"] == ["objectives"]
                assert len(payload["evaluation"]["indicators"]) == 1
                result["suggestions"].append(
                    {**result["suggestions"][0], "indicator_id": "summary"}
                )
            return result

    ai = AIService(provider=MixedSuggestions())
    transcript = FakeASR().transcribe_file(__file__)
    evaluation = ai.evaluate(
        {"course_id": "1", "lesson_id": "l", "taught_at": "2026-10-21", **transcript}
    )
    result = ai.suggest({"evaluation": evaluation})
    assert len(result["suggestions"]) == 1
    assert result["status"] == "partial"
    assert result["warnings"]
    assert all(i["indicator_id"] != "summary" for i in result["suggestions"])


def test_observed_average_and_problems_survive_no_suggestions(backend):
    from iteaching_ai.provider import ProviderError

    client, adapter, _ = backend

    class ObservedModel(FakeModel):
        def generate(self, task, payload):
            if task == "suggest":
                raise ProviderError("模型服务连接失败或超时")
            result = super().generate(task, payload)
            item = next(i for i in result["indicators"] if i["id"] == "objectives")
            item["score"] = 0
            item["problems"] = [
                {
                    "description": "目标没有明确成果标准",
                    "evidence": [{"segment_id": "s1", "quote": "学习目标"}],
                }
            ]
            return result

    assert (
        run_once(adapter, FakeASR(), AIService(provider=ObservedModel()), "worker") == "succeeded"
    )
    detail = client.get("/api/v1/recordings/r1/evaluation").json()["data"]
    assert detail["observed_score"] == 0
    assert detail["observed_count"] == 1
    assert detail["overall_score"] is None
    assert any("目标没有明确成果标准" in p for p in detail["problems"])
    assert detail["rubric_version"] == "boppps-text-v3"


def test_fabricated_problem_evidence_rejected(backend):
    from iteaching_ai.provider import ProviderError

    class BadProblem(FakeModel):
        def generate(self, task, payload):
            result = super().generate(task, payload)
            result["indicators"][1]["problems"] = [
                {"description": "问题", "evidence": [{"segment_id": "s1", "quote": "伪造的引文"}]}
            ]
            return result

    transcript = FakeASR().transcribe_file(__file__)
    with pytest.raises(ProviderError, match="问题引用"):
        AIService(provider=BadProblem()).evaluate(
            {"course_id": "1", "lesson_id": "l", "taught_at": "2026-10-21", **transcript}
        )


def test_observed_average_all_unknown_is_null(backend):
    client, adapter, _ = backend

    class Unknown(FakeModel):
        def generate(self, task, payload):
            result = super().generate(task, payload)
            for item in result["indicators"]:
                item.update(score=None, status="insufficient_evidence", evidence=[])
            return result

    assert run_once(adapter, FakeASR(), AIService(provider=Unknown()), "worker") == "succeeded"
    detail = client.get("/api/v1/recordings/r1/evaluation").json()["data"]
    assert detail["observed_score"] is None and detail["observed_count"] == 0
