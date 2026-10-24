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

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.db.session import get_db
from app.main import create_application
from app.models import Admin, Evaluation, ProcessingTask, TranscriptSegment


@pytest.mark.asyncio
async def test_full_supervision_flow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    testing_sessionmaker: sessionmaker[Session],
    db_override: Callable[[], Iterator[Session]],
) -> None:
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

    # 共享夹具：内存 SQLite + StaticPool，会话供给函数来自 conftest.py
    TestingSession = testing_sessionmaker
    # 预置 admin 账号（绕过 INITIAL_ADMIN_PASSWORD 初始化流程）
    with TestingSession() as session:
        session.add(
            Admin(
                username="admin",
                password_hash=hash_password("admin-password"),
                is_active=True,
            )
        )
        session.commit()

    # 用测试会话覆盖 FastAPI 的数据库依赖
    application = create_application()
    application.dependency_overrides[get_db] = db_override
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
                "name": "王督导",
                "level": "校级",
                "department": "计算机学院",
                "phone": "13800000001",
            },
        )
        teacher_create = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "username": "teacher",
                "password": "teacher-password",
                "role": "teacher",
                "name": "李老师",
                "department": "计算机学院",
                "phone": "13800000002",
            },
        )
        other_teacher_create = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "username": "other_teacher",
                "password": "other-teacher-password",
                "role": "teacher",
                "name": "赵老师",
                "department": "数学学院",
            },
        )
        assert supervisor_create.status_code == teacher_create.status_code == 201
        assert other_teacher_create.status_code == 201
        # 工号由系统生成：督导 1xxxx、教师 2xxxx，同角色内递增
        assert supervisor_create.json()["data"]["employee_no"] == "10001"
        assert teacher_create.json()["data"]["employee_no"] == "20001"
        assert other_teacher_create.json()["data"]["employee_no"] == "20002"
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
            json={
                "code": "MATH-001",
                "name": "公开课",
                # 新版上课地址：教学楼 + 3 位教室编号
                "location": "信息101",
                "class_name": "2026 级数学 1 班",
                "schedules": [
                    {"weekday": 1, "start_time": "08:00", "end_time": "09:40"},
                    # 按周批量录入：第 1-16 周 每周三 14:00-15:40
                    {
                        "weekday": 3,
                        "start_time": "14:00",
                        "end_time": "15:40",
                        "start_week": 1,
                        "end_week": 16,
                    },
                ],
                "assessment_form": "percent",
                "description": "公开课简介",
                "teacher_id": teacher_create.json()["data"]["id"],
                "teacher_name": "李老师",
            },
        )
        assert course_response.status_code == 201
        course_id = course_response.json()["data"]["id"]
        assert course_response.json()["data"]["code"] == "MATH-001"
        # 后端以教师账号姓名为准覆盖快照（_resolve_teacher 回填 Teacher.name）
        assert course_response.json()["data"]["teacher_name"] == "李老师"
        assert course_response.json()["data"]["status"] == "not_started"
        # 周次范围随时间段一并存储并回读
        assert course_response.json()["data"]["schedules"][1]["end_week"] == 16
        assert (await client.get("/api/v1/courses", headers=teacher_headers)).status_code == 200
        other_course = await client.post(
            "/api/v1/courses",
            headers=supervisor_headers,
            json={
                "code": "MATH-002",
                "name": "其他教师课程",
                "location": "建筑",
                "class_name": "2026 级数学 2 班",
                "schedules": [{"weekday": 2, "start_time": "10:00", "end_time": "11:40"}],
                "teacher_id": other_teacher_create.json()["data"]["id"],
                "teacher_name": "赵老师",
            },
        )
        assert other_course.status_code == 201

        # 编号唯一冲突 → 409；时间段非法 → 422；教师未匹配（缺少 teacher_id）→ 422
        duplicate = await client.post(
            "/api/v1/courses",
            headers=supervisor_headers,
            json={
                "code": "MATH-001",
                "name": "重复编号",
                "location": "信息",
                "class_name": "2026 级数学 1 班",
                "schedules": [{"weekday": 1, "start_time": "08:00", "end_time": "09:40"}],
                "teacher_id": teacher_create.json()["data"]["id"],
                "teacher_name": "李老师",
            },
        )
        assert duplicate.status_code == 409
        invalid_schedule = await client.post(
            "/api/v1/courses",
            headers=supervisor_headers,
            json={
                "code": "MATH-003",
                "name": "时间段非法",
                "location": "信息",
                "class_name": "2026 级数学 1 班",
                "schedules": [{"weekday": 1, "start_time": "10:00", "end_time": "09:40"}],
                "teacher_id": teacher_create.json()["data"]["id"],
                "teacher_name": "李老师",
            },
        )
        assert invalid_schedule.status_code == 422
        # 周次必须成对出现：只填 start_week 也应被拒绝
        partial_week = await client.post(
            "/api/v1/courses",
            headers=supervisor_headers,
            json={
                "code": "MATH-005",
                "name": "周次不成对",
                "location": "信息",
                "class_name": "2026 级数学 1 班",
                "schedules": [
                    {"weekday": 1, "start_time": "08:00", "end_time": "09:40", "start_week": 3}
                ],
                "teacher_id": teacher_create.json()["data"]["id"],
                "teacher_name": "李老师",
            },
        )
        assert partial_week.status_code == 422
        # teacher_id 为空：Schema 校验器拦截，返回 422
        no_teacher = await client.post(
            "/api/v1/courses",
            headers=supervisor_headers,
            json={
                "code": "MATH-004",
                "name": "未匹配教师课程",
                "location": "生医",
                "class_name": "2026 级数学 3 班",
                "schedules": [{"weekday": 5, "start_time": "08:00", "end_time": "09:40"}],
                "teacher_name": "未入库教师",
            },
        )
        assert no_teacher.status_code == 422
        # 教师模糊搜索接口：命中字段含姓名、院系、工号
        teacher_search = await client.get(
            "/api/v1/teachers?keyword=%E6%9D%8E%E8%80%81%E5%B8%88&limit=5",
            headers=supervisor_headers,
        )
        assert teacher_search.status_code == 200
        teacher_search_data = teacher_search.json()["data"]
        assert len(teacher_search_data) >= 1
        assert teacher_search_data[0]["name"] == "李老师"

        # 列表筛选：地点 + 任一时间段匹配（周三 14:30 命中），状态与星期过滤生效
        filtered = await client.get(
            "/api/v1/courses?location=%E4%BF%A1%E6%81%AF&weekday=3&time=14:30",
            headers=teacher_headers,
        )
        assert [item["id"] for item in filtered.json()["data"]] == [course_id]
        assert (await client.get("/api/v1/courses?weekday=2", headers=supervisor_headers)).json()[
            "data"
        ][0]["code"] == "MATH-002"
        assert (
            await client.get("/api/v1/courses?status=in_progress", headers=teacher_headers)
        ).json()["data"] == []
        # 督导不可编辑课程详细信息，管理员可以
        supervisor_edit = await client.patch(
            f"/api/v1/courses/{course_id}",
            headers=supervisor_headers,
            json={"status": "in_progress"},
        )
        assert supervisor_edit.status_code == 403
        updated = await client.patch(
            f"/api/v1/courses/{course_id}",
            headers=admin_headers,
            json={"status": "in_progress"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["status"] == "in_progress"
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
        # 8. 校准与评语（上传者本人可校准/评语）：
        #   a) 教师可校准自己上传的录音 → 201；
        #   b) 督导不能校准/评语教师上传的录音 → 403；
        #   c) 督导主动加入课程 → 201，重复加入幂等 → 200；
        #   d) 督导上传自己的听课录音并校准/评语 → 201。
        # --------------------------------------------------------------
        teacher_calibration = await client.post(
            f"/api/v1/evaluations/{evaluation_id}/calibrations",
            headers=teacher_headers,
            json={"overall_score": 82, "comment": "教师本人校准"},
        )
        assert teacher_calibration.status_code == 201

        supervisor_calibration = await client.post(
            f"/api/v1/evaluations/{evaluation_id}/calibrations",
            headers=supervisor_headers,
            json={"overall_score": 90, "comment": "督导不能校准教师录音"},
        )
        assert supervisor_calibration.status_code == 403
        supervisor_review = await client.post(
            f"/api/v1/evaluations/{evaluation_id}/reviews",
            headers=supervisor_headers,
            json={"comment": "督导不能评语教师录音"},
        )
        assert supervisor_review.status_code == 403

        join = await client.post(f"/api/v1/courses/{course_id}/join", headers=supervisor_headers)
        assert join.status_code == 201
        duplicate_join = await client.post(
            f"/api/v1/courses/{course_id}/join", headers=supervisor_headers
        )
        assert duplicate_join.status_code == 200
        assert duplicate_join.json()["data"]["id"] == join.json()["data"]["id"]

        # 督导上传自己的听课录音，并完成校准与评语（教师可见）
        supervisor_upload = await client.post(
            f"/api/v1/courses/{course_id}/recordings",
            headers=supervisor_headers,
            data={"recorded_at": "2026-09-30T09:00:00Z", "consent_confirmed": "true"},
            files={"file": ("supervision.wav", b"fake audio", "audio/wav")},
        )
        assert supervisor_upload.status_code == 201, supervisor_upload.text
        supervisor_recording_id = supervisor_upload.json()["data"]["recording_id"]
        supervisor_task_id = supervisor_upload.json()["data"]["task_id"]
        supervisor_claim = await client.post("/api/v1/internal/tasks/claim", headers=worker_headers)
        supervisor_claim_headers = {
            **worker_headers,
            "X-Task-Claim-Token": supervisor_claim.json()["data"]["claim_token"],
        }
        assert supervisor_claim.json()["data"]["task_id"] == supervisor_task_id
        supervisor_result = {**result, "transcript": "督导听课", "overall_score": 80}
        assert (
            await client.post(
                f"/api/v1/internal/tasks/{supervisor_task_id}/result",
                headers=supervisor_claim_headers,
                json=supervisor_result,
            )
        ).status_code == 200
        supervisor_evaluation = await client.get(
            f"/api/v1/recordings/{supervisor_recording_id}/evaluation",
            headers=supervisor_headers,
        )
        assert supervisor_evaluation.status_code == 200
        supervisor_evaluation_id = supervisor_evaluation.json()["data"]["id"]
        calibration = await client.post(
            f"/api/v1/evaluations/{supervisor_evaluation_id}/calibrations",
            headers=supervisor_headers,
            json={
                "overall_score": 82,
                "dimension_scores": {"participatory_learning": 65},
                "comment": "复核后调整",
            },
        )
        assert calibration.status_code == 201

        review = await client.post(
            f"/api/v1/evaluations/{supervisor_evaluation_id}/reviews",
            headers=supervisor_headers,
            json={"comment": "下一次课堂增加学生表达机会"},
        )
        assert review.status_code == 201

        # --------------------------------------------------------------
        # 8.1 督导端可见性与「我查过的课」：
        #   a) 督导只能看到自己上传的录音（教师上传的不可见）；
        #   b) 教师能看到督导上传的录音；
        #   c) 我查过的课=主动加入的课程（带 joined_at，支持四条件筛选）；
        #   d) 督导不可删除教师上传的音频；
        #   e) 本人修改密码后旧密码失效，管理员可强制重置密码。
        # --------------------------------------------------------------
        supervisor_recordings = await client.get(
            f"/api/v1/courses/{course_id}/recordings", headers=supervisor_headers
        )
        assert supervisor_recordings.status_code == 200
        listed = supervisor_recordings.json()["data"]
        assert [item["uploaded_by_role"] for item in listed] == ["supervisor"]
        assert listed[0]["description"] is None

        teacher_recordings = await client.get(
            f"/api/v1/courses/{course_id}/recordings", headers=teacher_headers
        )
        assert teacher_recordings.status_code == 200
        assert {item["uploaded_by_role"] for item in teacher_recordings.json()["data"]} == {
            "teacher",
            "supervisor",
        }

        my_courses = await client.get("/api/v1/supervisions/my-courses", headers=supervisor_headers)
        assert my_courses.status_code == 200
        assert [item["id"] for item in my_courses.json()["data"]] == [course_id]
        assert my_courses.json()["data"][0]["joined_at"]
        no_match = await client.get(
            "/api/v1/supervisions/my-courses",
            headers=supervisor_headers,
            params={"teacher_name": "不存在的教师"},
        )
        assert no_match.json()["data"] == []
        assert (
            await client.get("/api/v1/supervisions/my-courses", headers=teacher_headers)
        ).status_code == 403

        assert (
            await client.delete(f"/api/v1/recordings/{recording_id}", headers=supervisor_headers)
        ).status_code == 403

        wrong_old = await client.post(
            "/api/v1/auth/password",
            headers=supervisor_headers,
            json={"old_password": "wrong-password", "new_password": "supervisor-new-password"},
        )
        assert wrong_old.status_code == 400
        assert (
            await client.post(
                "/api/v1/auth/password",
                headers=supervisor_headers,
                json={
                    "old_password": "supervisor-password",
                    "new_password": "supervisor-new-password",
                },
            )
        ).status_code == 200
        assert (
            await client.post(
                "/api/v1/auth/login",
                json={"username": "supervisor", "password": "supervisor-password"},
            )
        ).status_code == 401
        relogin = await client.post(
            "/api/v1/auth/login",
            json={"username": "supervisor", "password": "supervisor-new-password"},
        )
        assert relogin.status_code == 200
        supervisor_headers = {"Authorization": f"Bearer {relogin.json()['data']['access_token']}"}

        supervisor_id = supervisor_create.json()["data"]["id"]
        assert (
            await client.post(
                f"/api/v1/users/{supervisor_id}/reset-password",
                headers=admin_headers,
                params={"role": "supervisor"},
                json={"new_password": "supervisor-reset-password"},
            )
        ).status_code == 200
        assert (
            await client.post(
                "/api/v1/auth/login",
                json={"username": "supervisor", "password": "supervisor-reset-password"},
            )
        ).status_code == 200

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

    # 清理：解除依赖覆盖（内存 SQLite 随夹具结束自动释放，无需手动删表）
    application.dependency_overrides.clear()
