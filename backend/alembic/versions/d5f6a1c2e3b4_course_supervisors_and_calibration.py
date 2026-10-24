"""course supervisors and generalized calibration

Revision ID: d5f6a1c2e3b4
Revises: c4e1a9b7d2f5
Create Date: 2026-10-24 00:00:00.000000

督导「加入课程」与「上传者本人可校准」所需的数据结构：

1. 新增 course_supervisors 表，表达督导对课程的成员关系（主动加入），
   取代原 supervision_links（课程—督导—音频三要素）的「我查过的课」语义；
2. score_calibrations 的 supervisor_id 泛化为 calibrated_by_id + calibrated_by_role，
   使教师与督导都能对自己上传的录音做校准。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5f6a1c2e3b4"
down_revision: str | Sequence[str] | None = "c4e1a9b7d2f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 新增督导课程成员关系表
    op.create_table(
        "course_supervisors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("supervisor_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_supervisors_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["supervisor_id"],
            ["supervisors.id"],
            name=op.f("fk_course_supervisors_supervisor_id_supervisors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_supervisors")),
        sa.UniqueConstraint("course_id", "supervisor_id", name="uq_course_supervisor"),
    )
    op.create_index(
        op.f("ix_course_supervisors_course_id"), "course_supervisors", ["course_id"], unique=False
    )
    op.create_index(
        op.f("ix_course_supervisors_supervisor_id"),
        "course_supervisors",
        ["supervisor_id"],
        unique=False,
    )

    # 2. score_calibrations：supervisor_id → calibrated_by_id + calibrated_by_role
    #    先加新列（可空）并从旧列回填（旧数据全部来自督导），再删旧列与旧外键并收紧非空。
    op.add_column("score_calibrations", sa.Column("calibrated_by_id", sa.Integer(), nullable=True))
    op.add_column(
        "score_calibrations", sa.Column("calibrated_by_role", sa.String(length=20), nullable=True)
    )
    op.execute(
        "UPDATE score_calibrations SET calibrated_by_id = supervisor_id, "
        "calibrated_by_role = 'supervisor'"
    )
    with op.batch_alter_table("score_calibrations", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "fk_score_calibrations_supervisor_id_supervisors", type_="foreignkey"
        )
        batch_op.drop_column("supervisor_id")
        batch_op.alter_column("calibrated_by_id", nullable=False)
        batch_op.alter_column("calibrated_by_role", nullable=False)
    op.create_index(
        op.f("ix_score_calibrations_calibrated_by_id"),
        "score_calibrations",
        ["calibrated_by_id"],
        unique=False,
    )

    # 3. 移除已被 course_supervisors 取代的 supervision_links
    op.drop_index(op.f("ix_supervision_links_recording_id"), table_name="supervision_links")
    op.drop_index(op.f("ix_supervision_links_supervisor_id"), table_name="supervision_links")
    op.drop_index(op.f("ix_supervision_links_course_id"), table_name="supervision_links")
    op.drop_table("supervision_links")


def downgrade() -> None:
    # 3 的反向：重建 supervision_links
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

    # 2 的反向：calibrated_by_id + calibrated_by_role → supervisor_id
    op.drop_index(op.f("ix_score_calibrations_calibrated_by_id"), table_name="score_calibrations")
    op.add_column("score_calibrations", sa.Column("supervisor_id", sa.Integer(), nullable=True))
    op.execute("UPDATE score_calibrations SET supervisor_id = calibrated_by_id")
    with op.batch_alter_table("score_calibrations", recreate="always") as batch_op:
        batch_op.drop_column("calibrated_by_role")
        batch_op.drop_column("calibrated_by_id")
        batch_op.alter_column("supervisor_id", nullable=False)
        batch_op.create_foreign_key(
            "fk_score_calibrations_supervisor_id_supervisors",
            "supervisors",
            ["supervisor_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    # 1 的反向：删除 course_supervisors
    op.drop_index(op.f("ix_course_supervisors_supervisor_id"), table_name="course_supervisors")
    op.drop_index(op.f("ix_course_supervisors_course_id"), table_name="course_supervisors")
    op.drop_table("course_supervisors")
