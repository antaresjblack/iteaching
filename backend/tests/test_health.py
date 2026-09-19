import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_returns_standard_success_response() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "success",
        "data": {"status": "ok"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "status_code", "message"),
    [
        ("GET", "/api/v1/missing", 404, "Not Found"),
        ("POST", "/api/v1/health", 405, "Method Not Allowed"),
    ],
)
async def test_http_errors_use_standard_response(
    method: str,
    path: str,
    status_code: int,
    message: str,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(method, path)

    assert response.status_code == status_code
    assert response.json() == {
        "code": status_code * 100,
        "message": message,
        "data": None,
    }
