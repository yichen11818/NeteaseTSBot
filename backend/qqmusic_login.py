"""Administrator-only access to the shared QQ Music login session."""
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel


class QQMusicCookieSetRequest(BaseModel):
    cookie: str


@dataclass(frozen=True)
class QQMusicLogin:
    client: Any

    async def qr_key(self) -> dict:
        return await self.client.get_qr_key()

    async def qr_check(self, qr_key: str, ptqrtoken: str, pt_login_sig: str = "") -> dict:
        if pt_login_sig:
            self.client._pt_login_sig = pt_login_sig
        return await self.client.check_qr_status(qr_key, ptqrtoken)

    async def set_cookie(self, req: QQMusicCookieSetRequest) -> dict:
        self.client.set_cookie(req.cookie)
        return {"success": True, "message": "Cookie设置成功", "uin": self.client.get_uin()}

    async def status(self) -> dict:
        if not self.client.get_cookie():
            return {"logged_in": False, "message": "未设置Cookie"}
        result = await self.client.refresh_login()
        # Status responses never expose the shared account's credentials.
        return {
            "logged_in": result["success"],
            "message": result["message"],
            "uin": self.client.get_uin(),
        }

    async def refresh(self) -> dict:
        return await self.client.refresh_login()


def create_qqmusic_login_router(client: Any, authorize: Callable[[Request], None]) -> APIRouter:
    router = APIRouter(prefix="/qqmusic/login", dependencies=[Depends(authorize)])
    login = QQMusicLogin(client)
    router.add_api_route("/qr/key", login.qr_key, methods=["GET"])
    router.add_api_route("/qr/check", login.qr_check, methods=["GET"])
    router.add_api_route("/cookie", login.set_cookie, methods=["POST"])
    router.add_api_route("/status", login.status, methods=["GET"])
    router.add_api_route("/refresh", login.refresh, methods=["POST"])
    return router
