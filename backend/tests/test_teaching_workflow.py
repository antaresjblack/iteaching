from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import create_application
from app.models import Evaluation, ProcessingTask, TranscriptSegment, User


@pytest.mark.asyncio
async def test_full_supervision_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.api.v1.endpoints import recordings as recording_endpoints
    from app.core.config import settings

    monkeypatch.setattr(settings, "upload_dir", tmp_path / "private-audio")
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    monkeypatch.setattr(settings, "ai_service_token", "test-worker-secret")

    def fake_probe(path: Path, extension: str) -> float:
        if path.read_bytes() == b"not actually audio":
            raise HTTPException(status_code=415, detail="invalid test audio")
        return 37.5

    monkeypatch.setattr(recording_endpoints, "probe_audio", fake_probe)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSession() as session:
        session.add(
            User(
                username="admin",
                password_hash=hash_password("admin-password"),
                role="admin",
                is_active=True,
            )
        )
        session.commit()

    def override_db() -> Iterator[Session]:
        with TestingSession() as session:
            yield session

    application = create_application()
    application.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        admin_login = await client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin-password"}
        )
        assert admin_login.status_code == 200
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['data']['access_token']}"}

        supervisor_create = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "username": "supervisor",
                "password": "supervisor-password",
                "role": "supervisor",
            },
        )
        teacher_create = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={"username": "teacher", "password": "teacher-password", "role": "teacher"},
        )
        other_teacher_create = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "username": "other_teacher",
                "password": "other-teacher-password",
                "role": "teacher",
            },
        )
        assert supervisor_create.status_code == teacher_create.status_code == 201
        assert other_teacher_create.status_code == 201

        supervisor_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "supervisor", "password": "supervisor-password"},
        )
        supervisor_headers = {
            "Authorization": f"Bearer {supervisor_login.json()['data']['access_token']}"
        }
        teacher_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "teacher", "password": "teacher-password"},
        )
        teacher_headers = {
            "Authorization": f"Bearer {teacher_login.json()['data']['access_token']}"
        }
        assert (await client.get("/api/v1/auth/me", headers=teacher_headers)).json()["data"][
            "username"
        ] == "teacher"
        assert (await client.get("/api/v1/users", headers=teacher_headers)).status_code == 403

        course_response = await client.post(
            "/api/v1/courses",
            headers=supervisor_headers,
            json={"name": "公开课", "teacher_id": teacher_create.json()["data"]["id"]},
        )
        assert course_response.status_code == 201
        course_id = course_response.json()["data"]["id"]
        assert (await client.get("/api/v1/courses", headers=teacher_headers)).status_code == 200
        other_course = await client.post(
            "/api/v1/courses",
            headers=supervisor_headers,
            json={"name": "其他教师课程", "teacher_id": other_teacher_create.json()["data"]["id"]},
        )
        assert other_course.status_code == 201
        assert (
            await client.get(
                f"/api/v1/courses/{other_course.json()['data']['id']}", headers=teacher_headers
            )
        ).status_code == 403
        empty_history = await client.get(
            f"/api/v1/courses/{course_id}/evaluations", headers=teacher_headers
        )
        assert empty_history.json()["data"]["items"] == []
        empty_comparison = await client.get(
            f"/api/v1/courses/{course_id}/comparison", headers=teacher_headers
        )
        assert empty_comparison.json()["data"] is None

        no_consent = await client.post(
            f"/api/v1/courses/{course_id}/recordings",
            headers=teacher_headers,
            data={"recorded_at": "2026-10-01T09:00:00Z", "consent_confirmed": "false"},
            files={"file": ("lesson.wav", b"fake audio", "audio/wav")},
        )
        assert no_consent.status_code == 422

        oversized = await client.post(
            f"/api/v1/courses/{course_id}/recordings",
            headers=teacher_headers,
            data={"recorded_at": "2026-10-01T09:00:00Z", "consent_confirmed": "true"},
            files={"file": ("large.wav", b"x" * (1024 * 1024 + 1), "audio/wav")},
        )
        assert oversized.status_code == 413

        oversized_request = await client.post(
            f"/api/v1/courses/{course_id}/recordings",
            headers={**teacher_headers, "Origin": "http://localhost:3000"},
            data={"recorded_at": "2026-10-01T09:00:00Z", "consent_confirmed": "true"},
            files={"file": ("huge.wav", b"x" * (1024 * 1024 + 70 * 1024), "audio/wav")},
        )
        assert oversized_request.status_code == 413
        assert oversized_request.headers["access-control-allow-origin"] == "http://localhost:3000"

        fake_audio = await client.post(
            f"/api/v1/courses/{course_id}/recordings",
            headers=teacher_headers,
            data={"recorded_at": "2026-10-01T09:00:00Z", "consent_confirmed": "true"},
            files={"file": ("fake.wav", b"not actually audio", "audio/wav")},
        )
        assert fake_audio.status_code == 415

        upload = await client.post(
            f"/api/v1/courses/{course_id}/recordings",
            headers=teacher_headers,
            data={
                "recorded_at": "2026-10-01T09:00:00Z",
                "consent_confirmed": "true",
                "consent_version": "2026-01",
            },
            files={"file": ("lesson.wav", b"fake audio", "audio/wav")},
        )
        assert upload.status_code == 201, upload.text
        recording_id = upload.json()["data"]["recording_id"]
        task_id = upload.json()["data"]["task_id"]
        assert (
            await client.get(f"/api/v1/recordings/{recording_id}/status", headers=teacher_headers)
        ).json()["data"]["status"] == "QUEUED"

        worker_headers = {"X-Service-Token": "test-worker-secret"}
        assert (
            await client.post("/api/v1/internal/tasks/claim", headers={"X-Service-Token": "bad"})
        ).status_code == 401
        claim = await client.post("/api/v1/internal/tasks/claim", headers=worker_headers)
        assert claim.status_code == 200
        assert claim.json()["data"]["task_id"] == task_id
        claim_headers = {
            **worker_headers,
            "X-Task-Claim-Token": claim.json()["data"]["claim_token"],
        }
        assert (
            await client.get(
                f"/api/v1/internal/tasks/{task_id}/audio",
                headers=worker_headers,
            )
        ).status_code == 409
        internal_audio = await client.get(
            f"/api/v1/internal/tasks/{task_id}/audio", headers=claim_headers
        )
        assert internal_audio.status_code == 200
        assert internal_audio.content == b"fake audio"
        assert (
            await client.post(f"/api/v1/internal/tasks/{task_id}/lease", headers=claim_headers)
        ).status_code == 200
        assert (await client.get(f"/api/v1/recordings/{recording_id}/audio")).status_code == 401
        assert (await client.post("/api/v1/internal/tasks/claim", headers=worker_headers)).json()[
            "data"
        ] is None

        result = {
            "version": 1,
            "mode": "boppps",
            "transcript": "请联系13800138000或teacher@example.com，身份证11010519491231002X",
            "segments": [
                {
                    "start_seconds": 0,
                    "end_seconds": 2,
                    "text": "请联系13800138000",
                    "speaker_id": "spk1",
                    "role": "teacher",
                }
            ],
            "overall_score": 75,
            "overall_evidence": "手机号13800138000，课堂目标清楚",
            "problems": ["互动不足"],
            "dimension_scores": {
                "bridge_in": 70,
                "objectives": 80,
                "pre_assessment": 75,
                "participatory_learning": 50,
                "post_assessment": 70,
                "summary": 80,
            },
            "suggestions": [],
        }
        invalid_dimensions = {
            **result,
            "dimension_scores": {
                key: value for key, value in result["dimension_scores"].items() if key != "summary"
            },
        }
        assert (
            await client.post(
                f"/api/v1/internal/tasks/{task_id}/result",
                headers=claim_headers,
                json=invalid_dimensions,
            )
        ).status_code == 422
        submit = await client.post(
            f"/api/v1/internal/tasks/{task_id}/result", headers=claim_headers, json=result
        )
        assert submit.status_code == 200, submit.text
        assert (
            await client.post(
                f"/api/v1/internal/tasks/{task_id}/result", headers=claim_headers, json=result
            )
        ).status_code == 200
        changed_result = {**result, "overall_score": 76}
        assert (
            await client.post(
                f"/api/v1/internal/tasks/{task_id}/result",
                headers=claim_headers,
                json=changed_result,
            )
        ).status_code == 409

        evaluation = await client.get(
            f"/api/v1/recordings/{recording_id}/evaluation", headers=teacher_headers
        )
        assert evaluation.status_code == 200
        assert "13800138000" not in evaluation.text
        assert "teacher@example.com" not in evaluation.text
        assert "11010519491231002X" not in evaluation.text
        assert evaluation.json()["data"]["suggestions"][0]["text"]

        evaluation_id = evaluation.json()["data"]["id"]
        teacher_calibration = await client.post(
            f"/api/v1/evaluations/{evaluation_id}/calibrations",
            headers=teacher_headers,
            json={"overall_score": 95, "comment": "teacher cannot calibrate"},
        )
        assert teacher_calibration.status_code == 403
        calibration = await client.post(
            f"/api/v1/evaluations/{evaluation_id}/calibrations",
            headers=supervisor_headers,
            json={
                "overall_score": 82,
                "dimension_scores": {"participatory_learning": 65},
                "comment": "复核后调整",
            },
        )
        assert calibration.status_code == 201

        review = await client.post(
            f"/api/v1/evaluations/{evaluation_id}/reviews",
            headers=supervisor_headers,
            json={"comment": "下一次课堂增加学生表达机会"},
        )
        assert review.status_code == 201

        history = await client.get(
            f"/api/v1/courses/{course_id}/evaluations", headers=teacher_headers
        )
        assert history.status_code == 200
        assert history.json()["data"]["items"][0]["overall_score"] == 82
        second_upload = await client.post(
            f"/api/v1/courses/{course_id}/recordings",
            headers=teacher_headers,
            data={"recorded_at": "2026-10-08T09:00:00Z", "consent_confirmed": "true"},
            files={"file": ("lesson-2.wav", b"fake audio", "audio/wav")},
        )
        second_task_id = second_upload.json()["data"]["task_id"]
        second_claim = await client.post("/api/v1/internal/tasks/claim", headers=worker_headers)
        second_claim_headers = {
            **worker_headers,
            "X-Task-Claim-Token": second_claim.json()["data"]["claim_token"],
        }
        second_result = {**result, "transcript": "第二次课堂", "overall_score": 78}
        assert second_claim.json()["data"]["task_id"] == second_task_id
        assert (
            await client.post(
                f"/api/v1/internal/tasks/{second_task_id}/result",
                headers=second_claim_headers,
                json=second_result,
            )
        ).status_code == 200
        comparison = await client.get(
            f"/api/v1/courses/{course_id}/comparison", headers=teacher_headers
        )
        assert comparison.status_code == 200
        assert comparison.json()["data"]["delta"]["overall_score"] == -4

        retry_upload = await client.post(
            f"/api/v1/courses/{course_id}/recordings",
            headers=teacher_headers,
            data={"recorded_at": "2026-10-09T09:00:00Z", "consent_confirmed": "true"},
            files={"file": ("retry.wav", b"fake audio", "audio/wav")},
        )
        retry_recording_id = retry_upload.json()["data"]["recording_id"]
        retry_task_id = retry_upload.json()["data"]["task_id"]
        for attempt in range(1, 4):
            retry_claim = await client.post("/api/v1/internal/tasks/claim", headers=worker_headers)
            assert retry_claim.json()["data"]["task_id"] == retry_task_id
            retry_headers = {
                **worker_headers,
                "X-Task-Claim-Token": retry_claim.json()["data"]["claim_token"],
            }
            failed = await client.post(
                f"/api/v1/internal/tasks/{retry_task_id}/failure",
                headers=retry_headers,
                json={"reason": "simulated worker failure"},
            )
            assert failed.json()["data"]["attempts"] == attempt
            assert failed.json()["data"]["status"] == ("FAILED" if attempt == 3 else "QUEUED")
        assert (
            await client.get(
                f"/api/v1/recordings/{retry_recording_id}/status", headers=teacher_headers
            )
        ).json()["data"]["status"] == "FAILED"

        stored_file = tmp_path / "private-audio" / recording_id[:2] / f"{recording_id}.wav"
        assert stored_file.is_file()
        original_commit = Session.commit
        commit_failed = False

        def fail_first_commit(session: Session) -> None:
            nonlocal commit_failed
            if not commit_failed:
                commit_failed = True
                raise RuntimeError("simulated database commit failure")
            original_commit(session)

        monkeypatch.setattr(Session, "commit", fail_first_commit)
        with pytest.raises(RuntimeError, match="simulated database commit failure"):
            await client.delete(f"/api/v1/recordings/{recording_id}", headers=teacher_headers)
        monkeypatch.setattr(Session, "commit", original_commit)
        assert not stored_file.exists()
        assert (
            await client.get(f"/api/v1/recordings/{recording_id}/status", headers=teacher_headers)
        ).status_code == 200
        delete = await client.delete(f"/api/v1/recordings/{recording_id}", headers=teacher_headers)
        assert delete.status_code == 204
        assert not stored_file.exists()
        assert (
            await client.get(f"/api/v1/recordings/{recording_id}/status", headers=teacher_headers)
        ).status_code == 404
        assert (
            await client.get(f"/api/v1/evaluations/{evaluation_id}", headers=teacher_headers)
        ).status_code == 404

    with TestingSession() as session:
        assert session.get(Evaluation, evaluation_id) is None
        assert session.get(ProcessingTask, task_id) is None
        assert session.query(TranscriptSegment).filter_by(evaluation_id=evaluation_id).count() == 0

    application.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
