"""supervision links and recording metadata

Revision ID: c4e1a9b7d2f5
Revises: 9c2f4b6a8d10
Create Date: 2026-10-22 00:00:00.000000

督导端功能改造所需的数据结构：

1. 新增 supervision_links 表，显式记录课程—督导—音频三要素；
   同一督导对同一课程允许多条关联（多次听课），
   同一音频重复关联由 (supervisor_id, recording_id) 唯一约束保证幂等；
2. recordings 增加 uploaded_by_role，用于区分教师上传（督导只读）与督导听课上传，
   历史数据统一回填为 teacher；
3. recordings 增加 description（内容说明，选填）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4e1a9b7d2f5"
down_revision: str | Sequence[str] | None = "9c2f4b6a8d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. recordings 新增上传者角色与内容说明
    op.add_column(
        "recordings",
        sa.Column(
            "uploaded_by_role",
            sa.String(length=20),
            nullable=False,
            server_default="teacher",
        ),
    )
    op.add_column("recordings", sa.Column("description", sa.String(length=500), nullable=True))

    # 2. 督导听课关联表
    op.create_table(
        "supervision_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("supervisor_id", sa.Integer(), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_supervision_links_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["supervisor_id"],
            ["supervisors.id"],
            name=op.f("fk_supervision_links_supervisor_id_supervisors"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.id"],
            name=op.f("fk_supervision_links_recording_id_recordings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supervision_links")),
        sa.UniqueConstraint(
            "supervisor_id", "recording_id", name="uq_supervision_supervisor_recording"
        ),
    )
    op.create_index(
        op.f("ix_supervision_links_course_id"), "supervision_links", ["course_id"], unique=False
    )
    op.create_index(
        op.f("ix_supervision_links_supervisor_id"),
        "supervision_links",
        ["supervisor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supervision_links_recording_id"),
        "supervision_links",
        ["recording_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_supervision_links_recording_id"), table_name="supervision_links")
    op.drop_index(op.f("ix_supervision_links_supervisor_id"), table_name="supervision_links")
    op.drop_index(op.f("ix_supervision_links_course_id"), table_name="supervision_links")
    op.drop_table("supervision_links")
    op.drop_column("recordings", "description")
    op.drop_column("recordings", "uploaded_by_role")
