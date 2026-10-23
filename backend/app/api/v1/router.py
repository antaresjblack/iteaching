from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.courses import router as courses_router
from app.api.v1.endpoints.evaluations import router as evaluations_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.internal import router as internal_router
from app.api.v1.endpoints.recordings import router as recordings_router
from app.api.v1.endpoints.supervisions import router as supervisions_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(courses_router, tags=["courses"])
api_router.include_router(recordings_router, tags=["recordings"])
api_router.include_router(internal_router, tags=["ai-worker"])
api_router.include_router(evaluations_router, tags=["evaluations"])
api_router.include_router(supervisions_router, tags=["supervisions"])
