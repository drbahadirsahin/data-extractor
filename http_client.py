from __future__ import annotations

import ssl
from typing import Any
from urllib import request

_HTTPS_CONTEXT: ssl.SSLContext | None = None


def trusted_https_context() -> ssl.SSLContext:
    global _HTTPS_CONTEXT
    if _HTTPS_CONTEXT is not None:
        return _HTTPS_CONTEXT
    try:
        import certifi

        _HTTPS_CONTEXT = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        _HTTPS_CONTEXT = ssl.create_default_context()
    return _HTTPS_CONTEXT


def urlopen(url: str | request.Request, **kwargs: Any):
    target_url = url.full_url if isinstance(url, request.Request) else str(url)
    if target_url.lower().startswith("https://") and "context" not in kwargs:
        kwargs["context"] = trusted_https_context()
    return request.urlopen(url, **kwargs)
