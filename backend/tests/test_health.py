"""健康检查与全局 HTTP 错误响应契约测试。

验证两点对外承诺：
1. /api/v1/health 返回统一成功响应包 {code, message, data}；
2. 框架级 HTTP 错误（404/405 等）同样被收敛为标准错误响应，code = 状态码 * 100。
"""

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_returns_standard_success_response() -> None:
    """健康检查端点返回 code=0 的标准成功响应。"""
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
    """未注册路由（404）与方法不允许（405）均返回标准错误响应包。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(method, path)

    assert response.status_code == status_code
    assert response.json() == {
        "code": status_code * 100,
        "message": message,
        "data": None,
    }
