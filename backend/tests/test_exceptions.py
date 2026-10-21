"""全局异常处理器测试。

验证 register_exception_handlers 的三条核心承诺：
1. 业务异常 AppException 按自带 code/message/status_code 输出标准响应包；
2. FastAPI 请求校验异常（422）对外隐藏用户输入等敏感细节，防信息泄露；
3. 未预期的内部异常（500）统一文案，不向客户端泄露堆栈/实现细节。
"""

import httpx
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.core.exceptions import AppException, register_exception_handlers


def _build_test_app() -> FastAPI:
    """构造一个挂载了全局异常处理器、并各抛一类异常的测试应用。"""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/app-error")
    def app_error() -> None:
        # 业务异常：应原样透出 code=40001 与 message
        raise AppException(code=40001, message="invalid request", status_code=400)

    @test_app.get("/validation-error")
    def validation_error() -> None:
        # 请求校验异常：input 中含手机号，响应里不得回显
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "contact"),
                    "msg": "Invalid value",
                    "input": "13800138000",
                }
            ]
        )

    @test_app.get("/unexpected-error")
    def unexpected_error() -> None:
        # 未捕获异常：模拟内部实现细节，响应里不得泄露
        raise RuntimeError("sensitive implementation detail")

    return test_app


@pytest.mark.asyncio
async def test_app_exception_uses_standard_response() -> None:
    """业务异常按标准响应包返回，HTTP 状态码与业务码由异常自身决定。"""
    transport = httpx.ASGITransport(app=_build_test_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/app-error")

    assert response.status_code == 400
    assert response.json() == {"code": 40001, "message": "invalid request", "data": None}


@pytest.mark.asyncio
async def test_validation_exception_uses_standard_response() -> None:
    """请求校验失败返回 42200，错误条目中不含用户原始输入（防敏感信息回显）。"""
    transport = httpx.ASGITransport(app=_build_test_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/validation-error")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 42200
    assert body["message"] == "Request validation failed"
    assert body["data"][0]["loc"] == ["query", "contact"]
    # 用户输入（手机号）既不在结构化字段中，也不出现在响应原文里
    assert "input" not in body["data"][0]
    assert "13800138000" not in response.text


@pytest.mark.asyncio
async def test_unexpected_exception_does_not_leak_internal_details() -> None:
    """未预期异常统一返回 50000/Internal server error，不泄露内部错误细节。"""
    transport = httpx.ASGITransport(app=_build_test_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/unexpected-error")

    assert response.status_code == 500
    assert response.json() == {"code": 50000, "message": "Internal server error", "data": None}
    assert "sensitive implementation detail" not in response.text
