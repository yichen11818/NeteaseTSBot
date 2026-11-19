import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from backend import auth
from backend.config import Settings
from backend.db import Base
from backend.models import AdminCredential


def request(cookie: str) -> Request:
    return Request({"type": "http", "scheme": "http", "path": "/auth/status",
                    "headers": [(b"cookie", cookie.encode())]})


class MultiServerAuthTests(unittest.TestCase):
    def test_cookie_name_accepts_per_server_names_and_rejects_header_injection(self):
        with patch.dict(os.environ, {"TSBOT_SESSION_COOKIE_NAME": "tsbot_admin_home"}):
            self.assertEqual("tsbot_admin_home", Settings(_env_file=None).session_cookie_name)
        with self.assertRaises(ValidationError):
            Settings(session_cookie_name="bad; Path=/", _env_file=None)

    def test_other_servers_cookie_cannot_authenticate_and_logout_is_scoped(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session, patch.object(auth, "SESSION_COOKIE", "tsbot_admin_home"):
            credential = AdminCredential(id=1, username="admin", password_hash="unused", must_change_password=False)
            session.add(credential)
            session.commit()
            token, _ = auth.create_session(session, credential)
            with self.assertRaises(HTTPException) as raised:
                auth.require_admin(request(f"tsbot_admin_friends={token}"), session)
            self.assertEqual(401, raised.exception.status_code)
            auth.require_admin(request(f"tsbot_admin_home={token}; tsbot_admin_friends=unrelated"), session)
            response = Response()
            auth.set_session_cookie(response, token, request(""))
            self.assertTrue(response.headers["set-cookie"].startswith("tsbot_admin_home="))
            logout = Response()
            auth.clear_session_cookie(logout)
            self.assertIn("tsbot_admin_home=", logout.headers["set-cookie"])
            self.assertNotIn("tsbot_admin_friends", logout.headers["set-cookie"])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
