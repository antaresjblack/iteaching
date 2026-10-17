from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import settings

ASGIMessage = dict[str, Any]
ASGIReceive = Callable[[], Awaitable[ASGIMessage]]
ASGISend = Callable[[ASGIMessage], Awaitable[None]]
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class _RequestBodyTooLarge(Exception):
    pass


class UploadBodyLimitMiddleware:
    """Reject oversized upload requests before multipart parsing can spool them to disk."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app
        self.upload_path = re.compile(
            rf"^{re.escape(settings.api_v1_prefix)}/courses/\d+/recordings/?$"
        )

    async def __call__(self, scope: dict[str, Any], receive: ASGIReceive, send: ASGISend) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or not self.upload_path.fullmatch(scope.get("path", ""))
        ):
            await self.app(scope, receive, send)
            return

        request_limit = settings.max_upload_size_mb * 1024 * 1024 + MULTIPART_OVERHEAD_BYTES
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > request_limit:
                    await self._respond_too_large(send)
                    return
            except ValueError:
                pass

        received_bytes = 0

        async def limited_receive() -> ASGIMessage:
            nonlocal received_bytes
            message = await receive()
            if message.get("type") == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > request_limit:
                    raise _RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestBodyTooLarge:
            await self._respond_too_large(send)

    @staticmethod
    async def _respond_too_large(send: ASGISend) -> None:
        body = b'{"code":41300,"message":"Request body exceeds configured size limit","data":null}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
