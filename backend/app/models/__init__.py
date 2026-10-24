"""SQLAlchemy model package.

Import future model classes here so Alembic can discover them through Base.metadata.
"""

from app.models.base import TimestampMixin
from app.models.entities import (
    AccountBase,
    Admin,
    Course,
    CourseSupervisor,
    DimensionScore,
    Evaluation,
    EvaluationReview,
    ImprovementSuggestion,
    ProcessingTask,
    Recording,
    ScoreCalibration,
    Supervisor,
    Teacher,
    TranscriptSegment,
)

__all__ = [
    "AccountBase",
    "Admin",
    "Course",
    "CourseSupervisor",
    "DimensionScore",
    "Evaluation",
    "EvaluationReview",
    "ImprovementSuggestion",
    "ProcessingTask",
    "Recording",
    "ScoreCalibration",
    "Supervisor",
    "Teacher",
    "TimestampMixin",
    "TranscriptSegment",
]
