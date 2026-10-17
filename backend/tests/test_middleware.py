from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.config import settings
from app.middleware import MULTIPART_OVERHEAD_BYTES, UploadBodyLimitMiddleware


@pytest.mark.asyncio
async def test_upload_body_limit_rejects_chunked_request_without_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    async def receive() -> dict[str, object]:
        return next(request_chunks)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

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
            "path": "/api/v1/courses/1/recordings",
            "headers": [(b"content-type", b"multipart/form-data; boundary=test")],
        },
        receive,
        send,
    )

    assert sent[0]["status"] == 413
    assert b'"code":41300' in sent[1]["body"]
