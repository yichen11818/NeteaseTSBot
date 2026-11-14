import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, Mock, patch

import httpx

from backend import main
from backend.logger import logger
from backend.qqmusic import QQMusicClient


COOKIE_SECRET = "fixture-cookie-secret"
LOGIN_SECRET = "fixture-login-signature"
QR_SECRET = "fixture-qr-signature"
URL_SECRET = "fixture-url-signature"
COOKIE = f"uin=12345; qqmusic_key={COOKIE_SECRET}"
AUTH_URL = f"https://example.test/confirm?ptsigx={URL_SECRET}"


class QQMusicLoggingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = QQMusicClient()
        self.stdout = self.enterContext(redirect_stdout(io.StringIO()))
        self.logs = self.enterContext(self.assertLogs(logger, level="DEBUG"))

    def assert_no_credentials(self):
        output = self.stdout.getvalue() + "\n".join(self.logs.output)
        for secret in (COOKIE_SECRET, LOGIN_SECRET, QR_SECRET, URL_SECRET):
            self.assertNotIn(secret, output)
        self.assertEqual("", self.stdout.getvalue())

    def transport(self, handler):
        real_client = httpx.AsyncClient
        factory = lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)
        self.enterContext(patch("backend.qqmusic.httpx.AsyncClient", side_effect=factory))

    async def test_cookie_diagnostics_do_not_contain_values(self):
        for value in (COOKIE, {"uin": "12345", "qqmusic_key": COOKIE_SECRET},
                      f"unrelated={COOKIE_SECRET}"):
            self.client.set_cookie(value)
        self.assert_no_credentials()

    async def test_qr_generation_does_not_log_cookies_or_signatures(self):
        def respond(request):
            cookie = f"pt_login_sig={LOGIN_SECRET}" if request.url.path.endswith("xlogin") else f"qrsig={QR_SECRET}"
            return httpx.Response(200, headers={"set-cookie": cookie}, content=b"qr-image")

        self.transport(respond)
        result = await self.client.get_qr_key()
        self.assertEqual(QR_SECRET, result["qr_key"])
        self.assertEqual(LOGIN_SECRET, result["pt_login_sig"])
        self.assert_no_credentials()

    async def test_qr_generation_errors_log_type_without_exception_text(self):
        def fail(request):
            raise httpx.ConnectError(f"failed request {AUTH_URL}", request=request)

        self.transport(fail)
        with self.assertRaises(Exception):
            await self.client.get_qr_key()
        self.assertTrue(any("ConnectError" in line for line in self.logs.output))
        self.assert_no_credentials()

    async def test_confirmation_and_cookie_refresh_do_not_log_credentials(self):
        self.client._session_cookies = {"pt_login_sig": LOGIN_SECRET, "qrsig": QR_SECRET}
        self.transport(lambda request: httpx.Response(200, headers={"set-cookie": f"qqmusic_key={COOKIE_SECRET}"}))
        result = await self.client.confirm_qr_login(AUTH_URL)
        self.assertTrue(result["ok"])
        self.assertIn(COOKIE_SECRET, self.client.get_cookie())
        self.assert_no_credentials()

    async def test_cookie_refresh_errors_log_type_without_exception_text(self):
        def fail(request):
            raise httpx.ReadTimeout(f"failed request {AUTH_URL}", request=request)

        self.transport(fail)
        await self.client._fetch_qqmusic_cookies()
        self.assertTrue(any("ReadTimeout" in line for line in self.logs.output))
        self.assert_no_credentials()

    async def test_playback_response_does_not_log_signed_urls(self):
        for url_field in ("purl", "opi30surl", "opi48kurl"):
            response = {"req_1": {"data": {"sip": ["https://example.test/"],
                        "midurlinfo": [{url_field: f"audio?key={URL_SECRET}"}]}}}
            with patch.object(self.client, "get_music_url", AsyncMock(return_value=response)):
                result = await self.client.get_music_url_simple("song")
            self.assertIn(URL_SECRET, result)
        self.assert_no_credentials()

    async def test_malformed_playback_response_keeps_safe_error_diagnostics(self):
        with patch.object(self.client, "get_music_url", AsyncMock(side_effect=ValueError(AUTH_URL))):
            self.assertIsNone(await self.client.get_music_url_simple("song"))
        self.assertTrue(any("ValueError" in line for line in self.logs.output))
        self.assert_no_credentials()

    async def test_admin_confirmation_saves_cookie_without_logging_it(self):
        with (
            patch.object(main, "_require_admin_token"),
            patch.object(main.qqmusic, "confirm_qr_login", AsyncMock(return_value={"ok": True})),
            patch.object(main.qqmusic, "get_cookie", return_value=COOKIE),
            patch.object(main, "_set_secret") as save,
        ):
            session = Mock()
            result = await main.admin_qqmusic_qr_confirm(
                main.QQMusicQRConfirmRequest(auth_url=AUTH_URL), Mock(), session,
            )
        save.assert_called_once_with(session, "qqmusic_cookie", COOKIE)
        self.assertTrue(result["admin_cookie_set"])
        self.assert_no_credentials()
