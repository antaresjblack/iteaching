from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.schemas.common import APIResponse

router = APIRouter(tags=["Health"])


class HealthData(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/health", response_model=APIResponse[HealthData])
def health_check() -> APIResponse[HealthData]:
    return APIResponse(data=HealthData())
