from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints.auth import initialize_admin
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db.session import ensure_database_directory
from app.middleware import UploadBodyLimitMiddleware
from app.services.storage import ensure_private_directory


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    ensure_private_directory(settings.upload_dir)
    ensure_database_directory()
    initialize_admin()
    yield


def create_application() -> FastAPI:
    setup_logging(settings.log_level)

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.add_middleware(UploadBodyLimitMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    register_exception_handlers(application)
    return application


app = create_application()
