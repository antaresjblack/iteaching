"""course schedule fields

Revision ID: 9c2f4b6a8d10
Revises: 7c3d9f1a2b48
Create Date: 2026-10-22 00:00:00.000000

课程表结构调整：

1. 课程不再直接挂督导外键，多对多关系改由“课程—督导—音频”关联（recordings）表达；
2. 新增课程编号（唯一）、上课地址、授课班级、多时间段 JSON、考察形式、简介、
   教师姓名快照与状态，历史数据回填默认值；
3. 教师外键改为可空（未匹配状态），教师账号删除时置空。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9c2f4b6a8d10"
down_revision: str | Sequence[str] | None = "7c3d9f1a2b48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("code", sa.String(length=40)),
    ("location", sa.String(length=200)),
    ("class_name", sa.String(length=200)),
    ("schedules", sa.JSON()),
    ("assessment_form", sa.String(length=20)),
    ("description", sa.String(length=500)),
    ("teacher_name", sa.String(length=80)),
    ("status", sa.String(length=20)),
)


def upgrade() -> None:
    # 1. 删除课程上的督导外键与索引，教师外键改为可空 + SET NULL
    op.drop_index("ix_courses_supervisor_id", table_name="courses")
    with op.batch_alter_table("courses") as batch:
        batch.drop_constraint("fk_courses_supervisor_id_supervisors", type_="foreignkey")
        batch.drop_column("supervisor_id")
        batch.drop_constraint("fk_courses_teacher_id_teachers", type_="foreignkey")
        batch.create_foreign_key(
            op.f("fk_courses_teacher_id_teachers"),
            "teachers",
            ["teacher_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.alter_column("teacher_id", existing_type=sa.Integer(), nullable=True)
        # 2. 新列先以可空形式加入，便于回填历史行
        for name, column_type in NEW_COLUMNS:
            batch.add_column(sa.Column(name, column_type, nullable=True))

    # 3. 回填历史数据：编号用 LEGACY- 前缀保证唯一，教师姓名取账号快照
    op.execute(
        sa.text(
            "UPDATE courses SET "
            "code = 'LEGACY-' || CAST(id AS TEXT), "
            "location = '未填写', "
            "class_name = '未填写', "
            "schedules = '[]', "
            "assessment_form = 'percent', "
            "teacher_name = COALESCE("
            "(SELECT teachers.name FROM teachers WHERE teachers.id = courses.teacher_id), "
            "'未匹配'), "
            "status = 'not_started'"
        )
    )

    # 4. 回填完成后收紧非空约束（简介保持可空），并建立编号唯一索引
    with op.batch_alter_table("courses") as batch:
        for name, column_type in NEW_COLUMNS:
            batch.alter_column(
                name,
                existing_type=column_type,
                nullable=name == "description",
            )
    op.create_index("ix_courses_code", "courses", ["code"], unique=True)


def downgrade() -> None:
    connection = op.get_bind()
    # 1. 先确认可无损还原：存在未匹配教师或没有督导账号时禁止降级
    unmatched = connection.execute(
        sa.text("SELECT COUNT(*) FROM courses WHERE teacher_id IS NULL")
    ).scalar()
    if unmatched:
        raise RuntimeError("Cannot downgrade while courses have unmatched teachers")

    # 2. 恢复督导列（先可空）、教师外键回到 RESTRICT
    op.drop_index("ix_courses_code", table_name="courses")
    with op.batch_alter_table("courses") as batch:
        batch.add_column(sa.Column("supervisor_id", sa.Integer(), nullable=True))
        batch.drop_constraint("fk_courses_teacher_id_teachers", type_="foreignkey")
        batch.create_foreign_key(
            op.f("fk_courses_teacher_id_teachers"),
            "teachers",
            ["teacher_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.alter_column("teacher_id", existing_type=sa.Integer(), nullable=False)

    # 3. 历史课程无法还原原督导归属，统一挂到第一个督导账号
    op.execute(sa.text("UPDATE courses SET supervisor_id = (SELECT MIN(id) FROM supervisors)"))
    missing = connection.execute(
        sa.text("SELECT COUNT(*) FROM courses WHERE supervisor_id IS NULL")
    ).scalar()
    if missing:
        raise RuntimeError("Cannot downgrade without supervisor accounts")

    # 4. 收紧督导列并恢复外键/索引，删除新增列
    with op.batch_alter_table("courses") as batch:
        batch.alter_column("supervisor_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            op.f("fk_courses_supervisor_id_supervisors"),
            "supervisors",
            ["supervisor_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        for name, _ in NEW_COLUMNS:
            batch.drop_column(name)
    op.create_index("ix_courses_supervisor_id", "courses", ["supervisor_id"], unique=False)
