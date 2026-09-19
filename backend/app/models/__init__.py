"""SQLAlchemy model package.

Import future model classes here so Alembic can discover them through Base.metadata.
"""

from app.models.base import TimestampMixin

__all__ = ["TimestampMixin"]
