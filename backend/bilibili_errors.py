"""Preserve playback failure categories across the API and yt-dlp adapters."""

import httpx
from fastapi import HTTPException
from yt_dlp.networking.exceptions import HTTPError, TransportError
from yt_dlp.utils import DownloadError, ExtractorError


class BilibiliPlaybackError(HTTPException):
    def __init__(self, detail: str, *, status_code: int = 502, recovery_reason: str | None = None):
        super().__init__(status_code=status_code, detail=detail)
        self.recovery_reason = recovery_reason


def bilibili_playback_error(exc: Exception, *, detail: str) -> BilibiliPlaybackError:
    seen: set[int] = set()
    while id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, BilibiliPlaybackError):
            return exc
        cause = None
        if isinstance(exc, DownloadError) and exc.exc_info:
            cause = exc.exc_info[1]
        elif isinstance(exc, ExtractorError):
            cause = exc.cause
        if not isinstance(cause, Exception):
            break
        exc = cause

    status = 502
    reason = None
    if isinstance(exc, HTTPException):
        status = exc.status_code
    elif isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
    elif isinstance(exc, HTTPError):
        status = exc.status
    elif isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return BilibiliPlaybackError(detail, recovery_reason="network_timeout")
    elif isinstance(exc, (httpx.UnsupportedProtocol, httpx.LocalProtocolError)):
        return BilibiliPlaybackError(detail)
    elif isinstance(exc, (httpx.RequestError, TransportError, ConnectionError)):
        return BilibiliPlaybackError(detail, recovery_reason="network_error")
    else:
        # Expected restrictions, malformed data and programming errors do not
        # become retryable just because their public response uses HTTP 502.
        return BilibiliPlaybackError(detail)

    if status == 429:
        reason = "rate_limited"
    elif status in (502, 503, 504):
        reason = "upstream_unavailable"
    return BilibiliPlaybackError(detail, status_code=status, recovery_reason=reason)


def bilibili_fallback_error(primary: Exception | None, fallback: Exception) -> BilibiliPlaybackError:
    detail = "B站 API 和备用解析均失败"
    errors = [bilibili_playback_error(error, detail=detail) for error in (primary, fallback) if error is not None]
    # A fallback succeeds normally even after an API restriction. If both fail,
    # do not let a transient error mask a restriction or an unclassified failure.
    return next((error for error in errors if error.recovery_reason is None), errors[-1])
