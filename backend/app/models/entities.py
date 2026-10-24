from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

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


class AccountBase(TimestampMixin, Base):
    """三类账号共享的抽象基类：只定义公共列，本身不建表。"""

    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 角色标识：普通 Python 类属性（不建列），由各子类赋值
    role: ClassVar[str]


class Admin(AccountBase):
    __tablename__ = "admins"

    role: ClassVar[str] = "admin"


class Supervisor(AccountBase):
    __tablename__ = "supervisors"

    role: ClassVar[str] = "supervisor"

    employee_no: Mapped[str] = mapped_column(String(40), unique=True)
    department: Mapped[str | None] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(10))
    phone: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))


class Teacher(AccountBase):
    __tablename__ = "teachers"

    role: ClassVar[str] = "teacher"

    employee_no: Mapped[str] = mapped_column(String(40), unique=True)
    department: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))


class Course(TimestampMixin, Base):
    """课程表：督导不在本表挂外键，多对多关系通过 recordings 关联表达。"""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    # 上课地址：地点筛选依据
    location: Mapped[str] = mapped_column(String(200))
    # 授课班级：纯文本
    class_name: Mapped[str] = mapped_column(String(200))
    # 多时间段 JSON 数组：[{"weekday": 1, "start_time": "08:00", "end_time": "09:40"}]
    schedules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    # 考察形式：当前仅百分制，枚举预留其他形式
    assessment_form: Mapped[str] = mapped_column(String(20), default="percent", nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    # 教师可未匹配：teacher_id 为空时仅保留录入姓名快照
    teacher_id: Mapped[int | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"), index=True
    )
    teacher_name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="not_started")

    recordings: Mapped[list[Recording]] = relationship(
        back_populates="course", cascade="all, delete-orphan", passive_deletes=True
    )


class Recording(TimestampMixin, Base):
    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    # 上传者可能是任意角色的账号（三张账号表无法单一外键），只保留普通整数列
    uploaded_by_id: Mapped[int] = mapped_column(Integer, index=True)
    # 上传者角色：区分教师上传（督导只读）与督导听课上传
    uploaded_by_role: Mapped[str] = mapped_column(
        String(20), default="teacher", server_default="teacher", nullable=False
    )
    storage_path: Mapped[str] = mapped_column(String(1000))
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    # 内容说明：供查看方了解音频内容（选填）
    description: Mapped[str | None] = mapped_column(String(500))
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
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
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
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

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
    supervisor_id: Mapped[int] = mapped_column(ForeignKey("supervisors.id", ondelete="RESTRICT"))
    comment: Mapped[str] = mapped_column(Text, nullable=False)

    evaluation: Mapped[Evaluation] = relationship(back_populates="reviews")


class ScoreCalibration(TimestampMixin, Base):
    __tablename__ = "score_calibrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    # 校准者可能是督导或教师（三张账号表独立自增，id 可能相同），故以角色+id 共同标识。
    calibrated_by_id: Mapped[int] = mapped_column(Integer, index=True)
    calibrated_by_role: Mapped[str] = mapped_column(String(20), nullable=False)
    overall_score: Mapped[float | None] = mapped_column(Float)
    dimension_scores: Mapped[dict[str, float] | None] = mapped_column(JSON)
    comment: Mapped[str | None] = mapped_column(Text)

    evaluation: Mapped[Evaluation] = relationship(back_populates="calibrations")


class CourseSupervisor(TimestampMixin, Base):
    """督导加入课程的成员关系：驱动「我查过的课」与课程内可见范围。

    同一督导对同一课程最多一条成员关系（加入一次即可）。
    """

    __tablename__ = "course_supervisors"
    __table_args__ = (UniqueConstraint("course_id", "supervisor_id", name="uq_course_supervisor"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    supervisor_id: Mapped[int] = mapped_column(
        ForeignKey("supervisors.id", ondelete="RESTRICT"), index=True
    )
