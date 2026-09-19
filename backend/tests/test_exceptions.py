import httpx
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.core.exceptions import AppException, register_exception_handlers


def _build_test_app() -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/app-error")
    def app_error() -> None:
        raise AppException(code=40001, message="invalid request", status_code=400)

    @test_app.get("/validation-error")
    def validation_error() -> None:
        raise RequestValidationError(
            [{"type": "missing", "loc": ("query", "name"), "msg": "Field required", "input": None}]
        )

    @test_app.get("/unexpected-error")
    def unexpected_error() -> None:
        raise RuntimeError("sensitive implementation detail")

    return test_app


@pytest.mark.asyncio
async def test_app_exception_uses_standard_response() -> None:
    transport = httpx.ASGITransport(app=_build_test_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/app-error")

    assert response.status_code == 400
    assert response.json() == {"code": 40001, "message": "invalid request", "data": None}


@pytest.mark.asyncio
async def test_validation_exception_uses_standard_response() -> None:
    transport = httpx.ASGITransport(app=_build_test_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/validation-error")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 42200
    assert body["message"] == "Request validation failed"
    assert body["data"][0]["loc"] == ["query", "name"]


@pytest.mark.asyncio
async def test_unexpected_exception_does_not_leak_internal_details() -> None:
    transport = httpx.ASGITransport(app=_build_test_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/unexpected-error")

    assert response.status_code == 500
    assert response.json() == {"code": 50000, "message": "Internal server error", "data": None}
    assert "sensitive implementation detail" not in response.text
