"""split shared users table into admins/supervisors/teachers

Revision ID: 7c3d9f1a2b48
Revises: 2a10_ai_nullable_scores
Create Date: 2026-10-21 00:00:00.000000

废弃共用的 users 表，按角色拆为 admins / supervisors / teachers 三张物理表：

1. 新建三张账号表（id 保持原值，既有 courses 等外键数据仍能对上）；
2. 按 users.role 迁移数据，历史行回填专属字段（工号 LEGACY-<id>、姓名取用户名、
   督导级别默认“校级”）；
3. batch 重建 courses / evaluation_reviews / score_calibrations 的外键指向新表，
   recordings.uploaded_by_id 去掉外键（上传者可能是任意角色），仅保留索引；
4. 删除 users 表。downgrade 做逆向操作。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c3d9f1a2b48"
down_revision: str | Sequence[str] | None = "2a10_ai_nullable_scores"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 账号基类公共列（三张新表结构一致的部分）
ACCOUNT_COLUMNS = "id, username, password_hash, is_active, last_login_at, created_at, updated_at"


def _create_account_table(name: str, extra_columns: list[sa.Column]) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *extra_columns,
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{name}")),
    )
    op.create_index(op.f(f"ix_{name}_username"), name, ["username"], unique=True)


def _drop_account_table(name: str) -> None:
    op.drop_index(op.f(f"ix_{name}_username"), table_name=name)
    op.drop_table(name)


def _point_fk(table: str, column: str, old: str, new: str) -> None:
    """把 table.column 的外键从 old 表改指 new 表（SQLite 走 batch 重建）。"""
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(f"fk_{table}_{column}_{old}", type_="foreignkey")
        batch.create_foreign_key(
            op.f(f"fk_{table}_{column}_{new}"),
            new,
            [column],
            ["id"],
            ondelete="RESTRICT",
        )


def upgrade() -> None:
    # 1. 新建三张账号表
    _create_account_table("admins", [])
    _create_account_table(
        "supervisors",
        [
            sa.Column("employee_no", sa.String(length=40), nullable=False),
            sa.Column("department", sa.String(length=100), nullable=True),
            sa.Column("level", sa.String(length=10), nullable=False),
            sa.Column("phone", sa.String(length=40), nullable=True),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.UniqueConstraint("employee_no", name=op.f("uq_supervisors_employee_no")),
        ],
    )
    _create_account_table(
        "teachers",
        [
            sa.Column("employee_no", sa.String(length=40), nullable=False),
            sa.Column("department", sa.String(length=100), nullable=True),
            sa.Column("phone", sa.String(length=40), nullable=True),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.UniqueConstraint("employee_no", name=op.f("uq_teachers_employee_no")),
        ],
    )

    # 2. 按 role 迁移数据：id 原样保留，历史行回填专属字段
    op.execute(
        sa.text(
            f"INSERT INTO admins ({ACCOUNT_COLUMNS}) "
            "SELECT id, username, password_hash, is_active, NULL, created_at, updated_at "
            "FROM users WHERE role = 'admin'"
        )
    )
    op.execute(
        sa.text(
            f"INSERT INTO supervisors ({ACCOUNT_COLUMNS},"
            " employee_no, department, level, phone, name) "
            "SELECT id, username, password_hash, is_active, NULL, created_at, updated_at, "
            "'LEGACY-' || id, NULL, '校级', NULL, username FROM users WHERE role = 'supervisor'"
        )
    )
    op.execute(
        sa.text(
            f"INSERT INTO teachers ({ACCOUNT_COLUMNS}, employee_no, department, phone, name) "
            "SELECT id, username, password_hash, is_active, NULL, created_at, updated_at, "
            "'LEGACY-' || id, NULL, NULL, username FROM users WHERE role = 'teacher'"
        )
    )

    # 3. 外键改指新表；recordings 上传者可能是任意角色，去掉外键只留索引
    _point_fk("courses", "supervisor_id", "users", "supervisors")
    _point_fk("courses", "teacher_id", "users", "teachers")
    _point_fk("evaluation_reviews", "supervisor_id", "users", "supervisors")
    _point_fk("score_calibrations", "supervisor_id", "users", "supervisors")
    with op.batch_alter_table("recordings") as batch:
        batch.drop_constraint("fk_recordings_uploaded_by_id_users", type_="foreignkey")
        batch.create_index(op.f("ix_recordings_uploaded_by_id"), ["uploaded_by_id"])

    # 4. 删除旧 users 表
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")


def downgrade() -> None:
    # 1. 重建 users 表（恢复拆分前的结构）
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    # 2. 三张账号表按角色回填（拆分前迁移过来的行 id 互不重叠）
    op.execute(
        sa.text(
            "INSERT INTO users (id, username, password_hash, role, is_active,"
            " created_at, updated_at) "
            "SELECT id, username, password_hash, 'admin', is_active, created_at, updated_at "
            "FROM admins UNION ALL "
            "SELECT id, username, password_hash, 'supervisor', is_active, created_at, updated_at "
            "FROM supervisors UNION ALL "
            "SELECT id, username, password_hash, 'teacher', is_active, created_at, updated_at "
            "FROM teachers"
        )
    )

    # 3. 还原外键与 recordings 的旧外键
    _point_fk("courses", "supervisor_id", "supervisors", "users")
    _point_fk("courses", "teacher_id", "teachers", "users")
    _point_fk("evaluation_reviews", "supervisor_id", "supervisors", "users")
    _point_fk("score_calibrations", "supervisor_id", "supervisors", "users")
    with op.batch_alter_table("recordings") as batch:
        batch.drop_index(op.f("ix_recordings_uploaded_by_id"))
        batch.create_foreign_key(
            op.f("fk_recordings_uploaded_by_id_users"),
            "users",
            ["uploaded_by_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    # 4. 删除三张账号表
    _drop_account_table("teachers")
    _drop_account_table("supervisors")
    _drop_account_table("admins")
