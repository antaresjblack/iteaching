from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import AccountBase, Admin, Supervisor, Teacher
from app.schemas.business import Role

bearer_scheme = HTTPBearer(auto_error=False)

DatabaseSession = Annotated[Session, Depends(get_db)]

# role claim → 对应账号表；物理分表后按角色路由查询
ACCOUNT_MODELS: dict[str, type[AccountBase]] = {
    Role.ADMIN.value: Admin,
    Role.SUPERVISOR.value: Supervisor,
    Role.TEACHER.value: Teacher,
}


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DatabaseSession,
) -> AccountBase:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
        role = str(payload.get("role") or "")
    except (ValueError, TypeError, KeyError, jwt.PyJWTError) as exc:
        raise unauthorized from exc
    model = ACCOUNT_MODELS.get(role)
    if model is None:
        raise unauthorized
    user = db.get(model, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[AccountBase, Depends(get_current_user)]


def require_role(user: AccountBase, *roles: str) -> None:
    if user.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
