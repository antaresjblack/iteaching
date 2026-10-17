from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Role(StrEnum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    TEACHER = "teacher"


class Dimension(StrEnum):
    BRIDGE_IN = "bridge_in"
    OBJECTIVES = "objectives"
    PRE_ASSESSMENT = "pre_assessment"
    PARTICIPATORY_LEARNING = "participatory_learning"
    POST_ASSESSMENT = "post_assessment"
    SUMMARY = "summary"


DIMENSION_KEYS = tuple(item.value for item in Dimension)
Score = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class UserCreate(BaseModel):
    username: Annotated[str, Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")]
    password: Annotated[str, Field(min_length=10, max_length=128)]
    role: Role


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: Role
    is_active: bool


class LoginRequest(BaseModel):
    username: str
    password: str


class CourseCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    teacher_id: int
    supervisor_id: int | None = None


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    supervisor_id: int
    teacher_id: int
    created_at: datetime


class TaskClaimRequest(BaseModel):
    worker_id: Annotated[str, Field(min_length=1, max_length=120)] = "worker"


class TaskFailureRequest(BaseModel):
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class TranscriptSegmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    end_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    text: Annotated[str, Field(max_length=10000)]
    speaker_id: Annotated[str | None, Field(max_length=80)] = None
    role: Literal["teacher", "student", "unknown"] = "unknown"

    @model_validator(mode="after")
    def validate_time_range(self) -> TranscriptSegmentInput:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class SuggestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, Field(min_length=1, max_length=2000)]

    @field_validator("text", mode="before")
    @classmethod
    def accept_plain_text(cls, value: object) -> object:
        return {"text": value} if isinstance(value, str) else value


class EvaluationResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    mode: Literal["basic", "boppps"]
    transcript: Annotated[str, Field(max_length=500000)]
    segments: list[TranscriptSegmentInput] = Field(default_factory=list, max_length=20000)
    overall_score: Score
    overall_evidence: Annotated[str, Field(min_length=1, max_length=20000)]
    problems: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        default_factory=list, max_length=200
    )
    dimension_scores: dict[str, Score] = Field(default_factory=dict)
    suggestions: list[SuggestionInput] = Field(default_factory=list, max_length=50)

    @field_validator("dimension_scores")
    @classmethod
    def validate_dimension_names(cls, value: dict[str, float]) -> dict[str, float]:
        unknown = set(value) - set(DIMENSION_KEYS)
        if unknown:
            raise ValueError(f"unknown dimension(s): {', '.join(sorted(unknown))}")
        return value

    @model_validator(mode="after")
    def validate_mode_dimensions(self) -> EvaluationResultInput:
        if self.mode == "boppps" and set(self.dimension_scores) != set(DIMENSION_KEYS):
            raise ValueError("boppps results require scores for all six dimensions")
        return self


class ReviewCreate(BaseModel):
    comment: Annotated[str, Field(min_length=1, max_length=10000)]


class CalibrationCreate(BaseModel):
    overall_score: Score | None = None
    dimension_scores: dict[str, Score] | None = None
    comment: Annotated[str | None, Field(max_length=10000)] = None

    @field_validator("dimension_scores")
    @classmethod
    def validate_calibration_dimensions(
        cls, value: dict[str, float] | None
    ) -> dict[str, float] | None:
        if value is not None and set(value) - set(DIMENSION_KEYS):
            raise ValueError("calibration contains unknown dimensions")
        return value

    @model_validator(mode="after")
    def require_calibration_value(self) -> CalibrationCreate:
        if self.overall_score is None and not self.dimension_scores and not self.comment:
            raise ValueError("at least one score or comment is required")
        return self
