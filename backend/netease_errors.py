"""Classify Netease risk control without reflecting upstream credentials."""
import httpx
from fastapi import HTTPException


NETEASE_RISK_CODE = "-460"
LEGACY_AUTO_BITRATE = 320000


def is_risk_response(payload: dict) -> bool:
    return str(payload.get("code")) == NETEASE_RISK_CODE


def risk_response_or_raise(error: httpx.HTTPStatusError) -> dict:
    try:
        payload = error.response.json()
    except ValueError:
        payload = {}
    if isinstance(payload, dict) and is_risk_response(payload):
        return payload
    raise HTTPException(
        status_code=502,
        detail=f"网易云音乐接口返回 HTTP {error.response.status_code}，请稍后重试或检查 API 服务",
    ) from None
