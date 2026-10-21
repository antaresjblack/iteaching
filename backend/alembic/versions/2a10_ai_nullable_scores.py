"""Allow unobserved AI scores without fabricating zeros."""

import sqlalchemy as sa

from alembic import op

revision = "2a10_ai_nullable_scores"
down_revision = "10441b2742d3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("evaluations") as batch:
        batch.alter_column("overall_score", existing_type=sa.Float(), nullable=True)
    with op.batch_alter_table("dimension_scores") as batch:
        batch.alter_column("score", existing_type=sa.Float(), nullable=True)


def downgrade():
    connection = op.get_bind()
    for table, column in (("evaluations", "overall_score"), ("dimension_scores", "score")):
        missing = connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL")
        ).scalar()
        if missing:
            raise RuntimeError(
                "Cannot downgrade while unobserved scores exist; no zero substitution is allowed"
            )
    with op.batch_alter_table("dimension_scores") as batch:
        batch.alter_column("score", existing_type=sa.Float(), nullable=False)
    with op.batch_alter_table("evaluations") as batch:
        batch.alter_column("overall_score", existing_type=sa.Float(), nullable=False)
