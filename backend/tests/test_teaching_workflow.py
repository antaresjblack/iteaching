"""教学督导业务全流程端到端测试。

用一个完整场景串起系统的核心闭环（全部通过 HTTP 接口驱动，内存 SQLite 隔离）：

  1. 建号与权限：admin 创建督导/教师账号，教师无权访问用户管理接口；
  2. 课程与隔离：督导建课，教师只能看自己课程的历史与对比；
  3. 上传防线：未确认知情同意(422)、超限(413)、伪造音频(415)均被拦截；
  4. 任务队列：Worker 凭服务令牌认领任务，音频下载需要认领令牌；
  5. 结果回传：维度缺失(422)、重复提交幂等(200)、内容变更冲突(409)；
  6. 隐私脱敏：评价结果中的手机号/邮箱/身份证不得外泄；
  7. 督导校准：教师不可校准(403)，督导校准后历史记录采用校准分；
  8. 历史对比：两次课堂评价的差值计算；
  9. 失败重试：Worker 连续失败 3 次后任务进入 FAILED 终态；
 10. 删除一致性：删除录音时数据库失败会回滚并保留文件，成功后级联清除。
"""

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
    """端到端走通"上传 → AI 处理 → 校准 → 对比 → 重试 → 删除"完整业务闭环。"""
    from app.api.v1.endpoints import recordings as recording_endpoints
    from app.core.config import settings

    # ------------------------------------------------------------------
    # 0. 测试环境装配：上传目录指向临时路径、限制 1MB、固定 Worker 令牌
    # ------------------------------------------------------------------
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "private-audio")
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    monkeypatch.setattr(settings, "ai_service_token", "test-worker-secret")

    # 用假的 ffprobe 替代真实探测：内容为特定字节时模拟"非法音频"，否则返回 37.5 秒
    def fake_probe(path: Path, extension: str) -> float:
        if path.read_bytes() == b"not actually audio":
            raise HTTPException(status_code=415, detail="invalid test audio")
        return 37.5

    monkeypatch.setattr(recording_endpoints, "probe_audio", fake_probe)

    # 内存 SQLite + StaticPool：整个测试共享同一个连接，表结构不丢失
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    # 预置 admin 账号（绕过 INITIAL_ADMIN_PASSWORD 初始化流程）
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

    # 用测试会话覆盖 FastAPI 的数据库依赖
    def override_db() -> Iterator[Session]:
        with TestingSession() as session:
            yield session

    application = create_application()
    application.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # --------------------------------------------------------------
        # 1. 建号与权限：admin 登录后创建督导、教师、另一教师三个账号
        # --------------------------------------------------------------
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

        # 各角色分别登录；教师可读取自身信息，但无权访问用户管理列表
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

        # --------------------------------------------------------------
        # 2. 课程与隔离：督导建课；教师看自己的课正常、看他人的课 403；
        #    新课程的历史评价与对比数据为空
        # --------------------------------------------------------------
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

        # --------------------------------------------------------------
        # 3. 上传防线：未确认知情同意 → 422；超过体积限制 → 413
        #    （且 CORS 头在错误响应上依然生效）；伪造音频 → 415
        # --------------------------------------------------------------
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

        # --------------------------------------------------------------
        # 4. 合法上传：201 返回录音与任务 ID，初始状态为 QUEUED
        # --------------------------------------------------------------
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

        # --------------------------------------------------------------
        # 5. 任务队列：服务令牌错误 → 401；认领成功后音频下载必须携带
        #    认领令牌（否则 409）；续租成功；未认证访问音频 → 401；
        #    队列已空时再次认领返回 data=null
        # --------------------------------------------------------------
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

        # --------------------------------------------------------------
        # 6. 结果回传：转写文本故意混入手机号/邮箱/身份证，供后续验证脱敏；
        #    维度分数缺失 → 422；正常提交 → 200；同内容重复提交幂等 → 200；
        #    内容变更后重复提交 → 409 冲突
        # --------------------------------------------------------------
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

        # --------------------------------------------------------------
        # 7. 隐私脱敏：教师读取评价结果时，手机号/邮箱/身份证均已脱敏；
        #    建议（suggestions）已由证据自动改写生成
        # --------------------------------------------------------------
        evaluation = await client.get(
            f"/api/v1/recordings/{recording_id}/evaluation", headers=teacher_headers
        )
        assert evaluation.status_code == 200
        assert "13800138000" not in evaluation.text
        assert "teacher@example.com" not in evaluation.text
        assert "11010519491231002X" not in evaluation.text
        assert evaluation.json()["data"]["suggestions"][0]["text"]

        evaluation_id = evaluation.json()["data"]["id"]
        # --------------------------------------------------------------
        # 8. 督导校准与评语：教师尝试校准 → 403；督导校准总分与维度分 → 201；
        #    督导追加人工评语 → 201
        # --------------------------------------------------------------
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

        # --------------------------------------------------------------
        # 9. 历史与对比：历史记录采用校准后的 82 分；上传第二次课堂（78 分）
        #    后，对比接口给出 -4 的分差
        # --------------------------------------------------------------
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

        # --------------------------------------------------------------
        # 10. 失败重试：同一任务被 Worker 连续标记失败，前两次回到 QUEUED，
        #     第三次达到最大尝试次数后进入 FAILED 终态
        # --------------------------------------------------------------
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

        # --------------------------------------------------------------
        # 11. 删除一致性：首次删除时模拟数据库提交失败——文件必须回滚保留、
        #     记录仍在；恢复后再次删除成功（204），文件与级联数据全部清除
        # --------------------------------------------------------------
        stored_file = tmp_path / "private-audio" / recording_id[:2] / f"{recording_id}.wav"
        assert stored_file.is_file()
        original_commit = Session.commit
        commit_failed = False

        # 仅让第一次 commit 抛错，验证服务端"删文件 + 删记录"的原子性补偿逻辑
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

    # 数据库层面确认级联删除：评价、任务、转写分段均已清除
    with TestingSession() as session:
        assert session.get(Evaluation, evaluation_id) is None
        assert session.get(ProcessingTask, task_id) is None
        assert session.query(TranscriptSegment).filter_by(evaluation_id=evaluation_id).count() == 0

    # 清理：解除依赖覆盖、删表、释放连接
    application.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
