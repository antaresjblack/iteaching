"""上传体积限制中间件测试。

UploadBodyLimitMiddleware 在上传端点上拦截超过 max_upload_size_mb 的请求。
本文件验证最棘手的一种情形：客户端使用分块传输（chunked），
请求头中没有 Content-Length，中间件必须边读边累计、超限即截断为 413，
而不是把整个请求体读完才拒绝（否则限制形同虚设）。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.config import settings
from app.middleware import MULTIPART_OVERHEAD_BYTES, UploadBodyLimitMiddleware


@pytest.mark.asyncio
async def test_upload_body_limit_rejects_chunked_request_without_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无 Content-Length 的分块上传在流式累计超限后立即返回 413。"""
    # 限制设为 1MB，构造总量略超 1MB + multipart 开销的分块流
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    chunk_size = 64 * 1024
    request_limit = 1024 * 1024 + MULTIPART_OVERHEAD_BYTES
    request_chunks: Iterator[dict[str, object]] = iter(
        {
            "type": "http.request",
            "body": b"x" * chunk_size,
            "more_body": True,
        }
        for _ in range(request_limit // chunk_size + 1)
    )
    sent: list[dict[str, object]] = []

    # 模拟 ASGI receive 通道：逐块吐出请求体
    async def receive() -> dict[str, object]:
        return next(request_chunks)

    # 模拟 ASGI send 通道：记录应用发出的所有响应消息
    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    # 下游应用：若能正常走完请求体会返回 200；本用例不应走到这里
    async def app(scope, inner_receive, inner_send) -> None:
        while (await inner_receive()).get("more_body"):
            pass
        await inner_send({"type": "http.response.start", "status": 200, "headers": []})
        await inner_send({"type": "http.response.body", "body": b"ok"})

    middleware = UploadBodyLimitMiddleware(app)
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/courses/1/recordings",  # 上传端点才会触发限制
            "headers": [(b"content-type", b"multipart/form-data; boundary=test")],
        },
        receive,
        send,
    )

    # 第一个响应消息即 413，且响应体为标准错误包 code=41300
    assert sent[0]["status"] == 413
    assert b'"code":41300' in sent[1]["body"]
