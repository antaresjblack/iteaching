from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Course(TimestampMixin, Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    supervisor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)

    recordings: Mapped[list[Recording]] = relationship(
        back_populates="course", cascade="all, delete-orphan", passive_deletes=True
    )


class Recording(TimestampMixin, Base):
    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    storage_path: Mapped[str] = mapped_column(String(1000))
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(40), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)

    course: Mapped[Course] = relationship(back_populates="recordings")
    task: Mapped[ProcessingTask | None] = relationship(
        back_populates="recording", cascade="all, delete-orphan", uselist=False
    )
    evaluation: Mapped[Evaluation | None] = relationship(
        back_populates="recording", cascade="all, delete-orphan", uselist=False
    )


class ProcessingTask(TimestampMixin, Base):
    __tablename__ = "processing_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recording_id: Mapped[str] = mapped_column(
        ForeignKey("recordings.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    claim_token: Mapped[str | None] = mapped_column(String(128))
    last_error: Mapped[str | None] = mapped_column(Text)

    recording: Mapped[Recording] = relationship(back_populates="task")


class Evaluation(TimestampMixin, Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    recording_id: Mapped[str] = mapped_column(
        ForeignKey("recordings.id", ondelete="CASCADE"), unique=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    overall_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    problems: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)

    recording: Mapped[Recording] = relationship(back_populates="evaluation")
    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    dimension_scores: Mapped[list[DimensionScore]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    suggestions: Mapped[list[ImprovementSuggestion]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[EvaluationReview]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    calibrations: Mapped[list[ScoreCalibration]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    speaker_id: Mapped[str | None] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    evaluation: Mapped[Evaluation] = relationship(back_populates="segments")


class DimensionScore(Base):
    __tablename__ = "dimension_scores"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "dimension", name="uq_dimension_eval_dimension"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    dimension: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)

    evaluation: Mapped[Evaluation] = relationship(back_populates="dimension_scores")


class ImprovementSuggestion(Base):
    __tablename__ = "improvement_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    evaluation: Mapped[Evaluation] = relationship(back_populates="suggestions")


class EvaluationReview(TimestampMixin, Base):
    __tablename__ = "evaluation_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    supervisor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    comment: Mapped[str] = mapped_column(Text, nullable=False)

    evaluation: Mapped[Evaluation] = relationship(back_populates="reviews")


class ScoreCalibration(TimestampMixin, Base):
    __tablename__ = "score_calibrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    supervisor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    overall_score: Mapped[float | None] = mapped_column(Float)
    dimension_scores: Mapped[dict[str, float] | None] = mapped_column(JSON)
    comment: Mapped[str | None] = mapped_column(Text)

    evaluation: Mapped[Evaluation] = relationship(back_populates="calibrations")
