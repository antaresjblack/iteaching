"""SQLAlchemy model package.

Import future model classes here so Alembic can discover them through Base.metadata.
"""

from app.models.base import TimestampMixin
from app.models.entities import (
    Course,
    DimensionScore,
    Evaluation,
    EvaluationReview,
    ImprovementSuggestion,
    ProcessingTask,
    Recording,
    ScoreCalibration,
    TranscriptSegment,
    User,
)

__all__ = [
    "Course",
    "DimensionScore",
    "Evaluation",
    "EvaluationReview",
    "ImprovementSuggestion",
    "ProcessingTask",
    "Recording",
    "ScoreCalibration",
    "TimestampMixin",
    "TranscriptSegment",
    "User",
]
