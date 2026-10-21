from datetime import UTC, datetime

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import settings
from app.models import Course, DimensionScore, Evaluation, Recording, TranscriptSegment, User


def test_nullable_migration_preserves_records_and_rejects_lossy_downgrade(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "migration.db").as_posix()
    monkeypatch.setattr(settings, "database_url", url)
    config = Config("alembic.ini")
    command.upgrade(config, "10441b2742d3")
    engine = create_engine(url)
    now = datetime.now(UTC)
    with Session(engine) as db:
        user = User(username="migration-user", password_hash="unused", role="admin", is_active=True)
        db.add(user)
        db.flush()
        course = Course(name="test", teacher_id=user.id, supervisor_id=user.id)
        db.add(course)
        db.flush()
        recording = Recording(
            id="r",
            course_id=course.id,
            uploaded_by_id=user.id,
            storage_path="test.wav",
            original_filename="test.wav",
            media_type="audio/wav",
            recorded_at=now,
            consent_at=now,
            consent_version="test",
            duration_seconds=10,
        )
        db.add(recording)
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
    command.upgrade(config, "head")
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
    command.check(config)
    engine.dispose()
