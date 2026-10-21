"""Short-lived, claim-bound audio capabilities for cloud ASR."""

import hashlib
import hmac
import ipaddress
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.core.config import settings


def public_base():
    base = settings.audio_public_base_url.rstrip("/")
    parsed = urlsplit(base)
    valid = (
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and parsed.path == ""
        and parsed.port in (None, 443)
    )
    if valid:
        host = parsed.hostname.lower()
        valid = host != "localhost" and not host.endswith((".localhost", ".local"))
        try:
            valid = valid and ipaddress.ip_address(host).is_global
        except ValueError:
            valid = valid and "." in host
    if not valid:
        raise HTTPException(503, "Configure AUDIO_PUBLIC_BASE_URL with a public HTTPS origin")
    if len(settings.audio_signing_key) < 32:
        raise HTTPException(503, "Configure AUDIO_SIGNING_KEY with at least 32 characters")
    return base


def signature(task, expires):
    message = f"audio-v1\n{task.id}\n{task.recording_id}\n{task.claim_token}\n{expires}"
    return hmac.new(
        settings.audio_signing_key.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
