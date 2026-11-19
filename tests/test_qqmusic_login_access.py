from contextlib import ExitStack
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import main
from backend.auth import SESSION_COOKIE, create_session
from backend.db import Base
from backend.models import AdminCredential


class QQMusicLoginAccessTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", poolclass=StaticPool,
                               connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine)
        with self.sessions() as session:
            credential = AdminCredential(id=1, password_hash="unused", must_change_password=False)
            session.add(credential)
            session.commit()
            self.token, row = create_session(session, credential)
            self.csrf = row.csrf_token
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(main, "new_session", self.sessions))
        stack.enter_context(patch.multiple(main.settings, api_token="", api_tokens="external-only"))
        stack.enter_context(patch.object(main.qqmusic, "get_cookie", return_value="credential-fixture"))
        stack.enter_context(patch.object(main.qqmusic, "get_uin", return_value="12345"))
        self.refresh = stack.enter_context(patch.object(main.qqmusic, "refresh_login",
            AsyncMock(return_value={"success": True, "message": "logged in"})))
        self.write = stack.enter_context(patch.object(main.qqmusic, "set_cookie", Mock()))
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def sign_in(self):
        self.client.cookies.set(SESSION_COOKIE, self.token)

    def test_anonymous_login_routes_reject_external_tokens(self):
        paths = [("GET", "/status"), ("POST", "/cookie"), ("POST", "/refresh"),
                 ("GET", "/qr/key"), ("GET", "/qr/check?qr_key=x&ptqrtoken=y")]
        for method, path in paths:
            with self.subTest(path=path):
                response = self.client.request(method, "/qqmusic/login" + path,
                    headers={"Authorization": "Bearer external-only"}, json={"cookie": "fixture"})
                self.assertEqual(401, response.status_code)
        self.write.assert_not_called()
        self.refresh.assert_not_awaited()

    def test_status_does_not_return_credentials(self):
        self.sign_in()
        response = self.client.get("/qqmusic/login/status")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"logged_in": True, "message": "logged in", "uin": "12345"}, response.json())
        self.assertNotIn("credential-fixture", response.text)

    def test_mutations_require_csrf_and_work_with_valid_session(self):
        self.sign_in()
        for path in ("/cookie", "/refresh"):
            response = self.client.post("/qqmusic/login" + path, json={"cookie": "fixture"})
            self.assertEqual(403, response.status_code)
        self.write.assert_not_called()
        self.refresh.assert_not_awaited()
        headers = {"X-CSRF-Token": self.csrf}
        response = self.client.post("/qqmusic/login/cookie", json={"cookie": "fixture"}, headers=headers)
        self.assertEqual(200, response.status_code)
        self.write.assert_called_once_with("fixture")
        self.assertEqual(200, self.client.post("/qqmusic/login/refresh", headers=headers).status_code)

    def test_first_login_and_revoked_sessions_cannot_access_account(self):
        self.sign_in()
        with self.sessions() as session:
            session.get(AdminCredential, 1).must_change_password = True
            session.commit()
        self.assertEqual(403, self.client.get("/qqmusic/login/status").status_code)
        with self.sessions() as session:
            session.get(AdminCredential, 1).password_version += 1
            session.commit()
        self.assertEqual(401, self.client.get("/qqmusic/login/status").status_code)

    def test_authorized_qr_flow_remains_available(self):
        self.sign_in()
        with patch.object(main.qqmusic, "get_qr_key", AsyncMock(return_value={"qr_key": "fixture"})):
            self.assertEqual(200, self.client.get("/qqmusic/login/qr/key").status_code)
        with patch.object(main.qqmusic, "check_qr_status", AsyncMock(return_value={"status": "waiting"})):
            response = self.client.get("/qqmusic/login/qr/check?qr_key=x&ptqrtoken=y")
            self.assertEqual({"status": "waiting"}, response.json())
