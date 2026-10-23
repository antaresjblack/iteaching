from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import String, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DatabaseSession, require_role
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models import AccountBase, Admin, Supervisor, Teacher
from app.schemas.business import (
    LoginRequest,
    PasswordChange,
    PasswordReset,
    Role,
    UserCreate,
    UserRead,
)

router = APIRouter()

# 登录查账顺序：三张表允许存在同名账号时，按此顺序取第一个命中者
ACCOUNT_LOOKUP_ORDER: tuple[type[AccountBase], ...] = (Admin, Supervisor, Teacher)

# 角色 → 账号模型，用于按角色定位账号（如管理员重置密码）
ACCOUNT_MODELS: dict[Role, type[AccountBase]] = {
    Role.ADMIN: Admin,
    Role.SUPERVISOR: Supervisor,
    Role.TEACHER: Teacher,
}

# 工号自动生成规则：督导 1xxxx、教师 2xxxx，同角色内递增（每种角色可容纳 9999 个账号）
EMPLOYEE_NO_PREFIX: dict[Role, int] = {Role.SUPERVISOR: 1, Role.TEACHER: 2}
EMPLOYEE_NO_BASE = 10000


def _next_employee_no(db: Session, model: type[AccountBase], role: Role) -> str:
    """按角色前缀取当前最大工号 +1；非数字的历史工号不参与计算。"""
    prefix = EMPLOYEE_NO_PREFIX[role]
    existing = db.scalars(select(model.employee_no)).all()
    numbers = [
        int(no) for no in existing if no and no.isdigit() and int(no) // EMPLOYEE_NO_BASE == prefix
    ]
    return str(max(numbers, default=prefix * EMPLOYEE_NO_BASE) + 1)


@router.post("/auth/login")
def login(body: LoginRequest, db: DatabaseSession) -> dict[str, object]:
    user: AccountBase | None = None
    for model in ACCOUNT_LOOKUP_ORDER:
        user = db.scalar(select(model).where(model.username == body.username))
        if user is not None:
            break
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return {
        "code": 0,
        "message": "success",
        "data": {
            "access_token": create_access_token(
                str(user.id), additional_claims={"role": user.role}
            ),
            "token_type": "bearer",
            "user": UserRead.model_validate(user),
        },
    }


@router.get("/auth/me")
def get_me(user: CurrentUser) -> dict[str, object]:
    return {"code": 0, "message": "success", "data": UserRead.model_validate(user)}


@router.post("/auth/password")
def change_password(
    body: PasswordChange, user: CurrentUser, db: DatabaseSession
) -> dict[str, object]:
    """本人修改密码：校验旧密码后写入新密码（最小长度 12 位由 schema 校验）。"""
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Old password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"code": 0, "message": "success", "data": None}


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    body: PasswordReset,
    role: Annotated[Role, Query()],
    user: CurrentUser,
    db: DatabaseSession,
) -> dict[str, object]:
    """管理员强制重置指定账号密码；role 用于在三张分表中定位账号。"""
    require_role(user, Role.ADMIN.value)
    model = ACCOUNT_MODELS[role]
    target = db.get(model, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Account not found")
    target.password_hash = hash_password(body.new_password)
    db.commit()
    return {"code": 0, "message": "success", "data": None}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, user: CurrentUser, db: DatabaseSession) -> dict[str, object]:
    require_role(user, Role.ADMIN.value)
    # 用户名需在三张账号表中全局唯一
    for model in ACCOUNT_LOOKUP_ORDER:
        if db.scalar(select(model.id).where(model.username == body.username)) is not None:
            raise HTTPException(status_code=409, detail="Username already exists")
    password_hash = hash_password(body.password)
    new_user: AccountBase
    if body.role == Role.ADMIN:
        new_user = Admin(username=body.username, password_hash=password_hash, is_active=True)
    elif body.role == Role.SUPERVISOR:
        # name / department / level 已由 UserCreate 的校验器保证非空；工号由系统生成
        new_user = Supervisor(
            username=body.username,
            password_hash=password_hash,
            is_active=True,
            employee_no=_next_employee_no(db, Supervisor, body.role),
            department=body.department,
            level=body.level,
            phone=body.phone,
            name=body.name,
        )
    else:
        new_user = Teacher(
            username=body.username,
            password_hash=password_hash,
            is_active=True,
            employee_no=_next_employee_no(db, Teacher, body.role),
            department=body.department,
            phone=body.phone,
            name=body.name,
        )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"code": 0, "message": "success", "data": UserRead.model_validate(new_user)}


@router.get("/users")
def list_users(user: CurrentUser, db: DatabaseSession) -> dict[str, object]:
    require_role(user, Role.ADMIN.value)
    # 合并三张账号表，按 (角色, id) 排序返回
    users = sorted(
        (
            *db.scalars(select(Admin)).all(),
            *db.scalars(select(Supervisor)).all(),
            *db.scalars(select(Teacher)).all(),
        ),
        key=lambda item: (item.role, item.id),
    )
    return {
        "code": 0,
        "message": "success",
        "data": [UserRead.model_validate(item) for item in users],
    }


@router.get("/teachers")
def search_teachers(
    keyword: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    *,
    user: CurrentUser,
    db: DatabaseSession,
) -> dict[str, object]:
    """教师模糊搜索：admin 与 supervisor 均可访问，用于课程表单中绑定教师。

    命中字段：name（姓名）、department（院系）、employee_no（工号），任一字段包含关键词即返回。
    """

    require_role(user, Role.ADMIN.value, Role.SUPERVISOR.value)
    query = select(Teacher).where(Teacher.is_active.is_(True))
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                Teacher.name.ilike(like),
                Teacher.department.ilike(like),
                func.cast(Teacher.employee_no, String()).ilike(like),
            )
        )
    teachers = db.scalars(query.limit(limit)).all()
    return {
        "code": 0,
        "message": "success",
        "data": [
            {
                "id": t.id,
                "name": t.name,
                "employee_no": t.employee_no,
                "department": t.department,
                "username": t.username,
            }
            for t in teachers
        ],
    }


def initialize_admin() -> None:
    """Create the first admin only when a password is explicitly configured."""
    if not settings.initial_admin_password:
        return
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        if db.scalar(select(Admin.id).limit(1)) is not None:
            return
        db.add(
            Admin(
                username=settings.initial_admin_username,
                password_hash=hash_password(settings.initial_admin_password),
                is_active=True,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if db.scalar(select(Admin.id).limit(1)) is None:
                raise
