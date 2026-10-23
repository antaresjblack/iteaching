from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import settings
from app.models import (
    Course,
    DimensionScore,
    Evaluation,
    Supervisor,
    Teacher,
    TranscriptSegment,
)


def test_nullable_migration_preserves_records_and_rejects_lossy_downgrade(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "migration.db").as_posix()
    monkeypatch.setattr(settings, "database_url", url)
    config = Config("alembic.ini")
    command.upgrade(config, "10441b2742d3")
    engine = create_engine(url)
    now = datetime.now(UTC)
    # 旧版 users 表已随分表迁移删除，这里用原生 SQL 预置督导/教师两个历史账号
    legacy_ts = now.strftime("%Y-%m-%d %H:%M:%S.%f")
    with Session(engine) as db:
        for username, role in (
            ("legacy-supervisor", "supervisor"),
            ("legacy-teacher", "teacher"),
        ):
            db.execute(
                sa.text(
                    "INSERT INTO users (username, password_hash, role, is_active,"
                    " created_at, updated_at)"
                    " VALUES (:username, 'unused', :role, 1, :ts, :ts)"
                ),
                {"username": username, "role": role, "ts": legacy_ts},
            )
        db.flush()
        ids = dict(db.execute(sa.text("SELECT role, id FROM users")).all())
        # 旧版本 schema 与当前 ORM 模型不一致，历史课程行用原生 SQL 写入
        db.execute(
            sa.text(
                "INSERT INTO courses (name, supervisor_id, teacher_id,"
                " created_at, updated_at) VALUES ('test', :supervisor, :teacher, :ts, :ts)"
            ),
            {
                "supervisor": ids["supervisor"],
                "teacher": ids["teacher"],
                "ts": legacy_ts,
            },
        )
        db.flush()
        course_id = db.execute(sa.text("SELECT id FROM courses")).scalar()
        # 旧版本 recordings 表没有 uploaded_by_role / description 列，因此同样用原生 SQL 写入
        db.execute(
            sa.text(
                "INSERT INTO recordings (id, course_id, uploaded_by_id, storage_path,"
                " original_filename, media_type, recorded_at, consent_at, consent_version,"
                " duration_seconds, created_at, updated_at)"
                " VALUES ('r', :course_id, :uploader, 'test.wav', 'test.wav', 'audio/wav',"
                " :ts, :ts, 'test', 10, :ts, :ts)"
            ),
            {
                "course_id": course_id,
                "uploader": ids["teacher"],
                "ts": legacy_ts,
            },
        )
        db.flush()
        evaluation = Evaluation(
            recording_id="r",
            version=1,
            mode="basic",
            raw_result={},
            transcript="original",
            overall_score=80,
            overall_evidence="original",
            problems=[],
        )
        db.add(evaluation)
        db.flush()
        db.add(DimensionScore(evaluation_id=evaluation.id, dimension="objectives", score=80))
        db.add(
            TranscriptSegment(
                evaluation_id=evaluation.id,
                start_seconds=0,
                end_seconds=1,
                text="original",
                role="unknown",
            )
        )
        db.commit()
    command.upgrade(config, "2a10_ai_nullable_scores")
    assert next(
        c for c in inspect(engine).get_columns("evaluations") if c["name"] == "overall_score"
    )["nullable"]
    with Session(engine) as db:
        evaluation = db.scalar(select(Evaluation))
        assert evaluation.overall_score == 80
        assert db.scalar(select(TranscriptSegment)).text == "original"
        assert db.scalar(select(DimensionScore)).score == 80
        evaluation.overall_score = None
        db.commit()
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        command.downgrade(config, "10441b2742d3")
    # 继续升级到 head：users 按 role 拆入三张账号表，id 与原外键保持一致
    command.upgrade(config, "head")
    with Session(engine) as db:
        supervisor = db.scalar(select(Supervisor))
        teacher = db.scalar(select(Teacher))
        assert (supervisor.id, supervisor.username) == (ids["supervisor"], "legacy-supervisor")
        assert supervisor.employee_no == f"LEGACY-{ids['supervisor']}"
        assert supervisor.level == "校级" and supervisor.name == "legacy-supervisor"
        assert (teacher.id, teacher.name) == (ids["teacher"], "legacy-teacher")
        course = db.scalar(select(Course))
        assert course.id == course_id
        assert course.teacher_id == teacher.id
        # 课程表改造后的历史数据回填：编号、姓名快照、状态与空时间段
        assert course.code == f"LEGACY-{course.id}"
        assert course.teacher_name == "legacy-teacher"
        assert course.location == "未填写"
        assert course.schedules == []
        assert (course.assessment_form, course.status) == ("percent", "not_started")
        assert not hasattr(course, "supervisor_id")
    command.check(config)
    engine.dispose()
