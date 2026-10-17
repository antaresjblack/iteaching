from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DatabaseSession, require_role
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.business import LoginRequest, Role, UserCreate, UserRead

router = APIRouter()


@router.post("/auth/login")
def login(body: LoginRequest, db: DatabaseSession) -> dict[str, object]:
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
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


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, user: CurrentUser, db: DatabaseSession) -> dict[str, object]:
    require_role(user, Role.ADMIN.value)
    existing = db.scalar(select(User.id).where(User.username == body.username))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Username already exists")
    new_user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role.value,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"code": 0, "message": "success", "data": UserRead.model_validate(new_user)}


@router.get("/users")
def list_users(user: CurrentUser, db: DatabaseSession) -> dict[str, object]:
    require_role(user, Role.ADMIN.value)
    users = db.scalars(select(User).order_by(User.id)).all()
    return {
        "code": 0,
        "message": "success",
        "data": [UserRead.model_validate(item) for item in users],
    }


def initialize_admin() -> None:
    """Create the first admin only when a password is explicitly configured."""
    if not settings.initial_admin_password:
        return
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.role == Role.ADMIN.value)) is not None:
            return
        db.add(
            User(
                username=settings.initial_admin_username,
                password_hash=hash_password(settings.initial_admin_password),
                role=Role.ADMIN.value,
                is_active=True,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if db.scalar(select(User.id).where(User.role == Role.ADMIN.value)) is None:
                raise
