from contextlib import ExitStack
from functools import partial
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from backend import main
from backend.netease import NeteaseClient


class NeteaseQualityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.requests = []
        self.responses = []

        def respond(request):
            self.requests.append(request)
            status, payload = self.responses.pop(0)
            return httpx.Response(status, json=payload)

        client = NeteaseClient()
        client._base = "http://music-api.test"
        patches = ExitStack()
        self.addCleanup(patches.close)
        patches.enter_context(patch.object(main, "netease", client))
        patches.enter_context(patch.object(main, "_get_admin_cookie", return_value="MUSIC_U=test-secret"))
        patches.enter_context(patch("backend.netease.httpx.AsyncClient", partial(httpx.AsyncClient, transport=httpx.MockTransport(respond))))

    @staticmethod
    def playable(level="standard"):
        return {"code": 200, "data": [{"id": 22699090, "code": 200, "url": "https://audio.example/song.mp3", "level": level, "br": 128000}]}

    async def test_auto_recovers_from_risk_error_with_one_standard_request(self):
        self.responses = [(400, {"code": -460, "message": "network risk"}), (200, self.playable())]
        result = await main.song_url("22699090", "auto", session=None)
        self.assertEqual("https://audio.example/song.mp3", result["url"])
        self.assertEqual("standard", result["level"])
        self.assertFalse(result["trial"])
        self.assertEqual(["jymaster", "standard"], [r.url.params["level"] for r in self.requests])
        self.assertTrue(all("MUSIC_U=test-secret" in r.headers["cookie"] for r in self.requests))

    async def test_auto_also_handles_risk_code_in_successful_http_response(self):
        self.responses = [(200, {"code": -460, "message": "network risk"}), (200, self.playable())]
        result = await main.song_url("22699090", "auto", session=None)
        self.assertEqual("standard", result["level"])

    async def test_explicit_quality_reports_risk_without_silent_downgrade(self):
        self.responses = [(400, {"code": -460, "message": "MUSIC_U=do-not-reflect"})]
        with self.assertRaises(HTTPException) as raised:
            await main.song_url("22699090", "exhigh", session=None)
        self.assertEqual(503, raised.exception.status_code)
        self.assertIn("-460", raised.exception.detail)
        self.assertNotIn("MUSIC_U", raised.exception.detail)
        self.assertNotIn("music-api.test", raised.exception.detail)
        self.assertEqual(1, len(self.requests))

    async def test_auto_risk_tries_legacy_bitrate_endpoint_after_standard(self):
        self.responses = [
            (400, {"code": -460}),
            (400, {"code": -460}),
            (200, self.playable()),
        ]
        result = await main.song_url("22699090", "auto", session=None)
        self.assertEqual("https://audio.example/song.mp3", result["url"])
        self.assertEqual(3, len(self.requests))
        self.assertEqual("/song/url", self.requests[2].url.path)
        self.assertEqual("320000", self.requests[2].url.params["br"])

    async def test_standard_risk_error_ends_auto_fallback_after_legacy_retry(self):
        self.responses = [
            (400, {"code": -460}),
            (400, {"code": -460}),
            (400, {"code": -460}),
        ]
        with self.assertRaises(HTTPException) as raised:
            await main.song_url("22699090", "auto", session=None)
        self.assertEqual(503, raised.exception.status_code)
        self.assertEqual(3, len(self.requests))
        self.assertEqual("/song/url", self.requests[2].url.path)
        self.assertEqual("320000", self.requests[2].url.params["br"])

    async def test_unrelated_upstream_error_is_not_retried(self):
        self.responses = [(400, {"code": 400, "message": "bad parameter"})]
        with self.assertRaises(HTTPException) as raised:
            await main.song_url("22699090", "auto", session=None)
        self.assertEqual(502, raised.exception.status_code)
        self.assertEqual(1, len(self.requests))

    async def test_legacy_http_errors_are_not_misreported_as_risk_control(self):
        for status in (404, 500):
            self.responses = [(400, {"code": -460}), (400, {"code": -460}),
                              (status, {"message": "MUSIC_U=do-not-reflect"})]
            with self.subTest(status=status), self.assertRaises(HTTPException) as raised:
                await main.song_url("22699090", "auto", session=None)
            self.assertEqual(502, raised.exception.status_code)
            self.assertIn(f"HTTP {status}", raised.exception.detail)
            self.assertNotIn("-460", raised.exception.detail)
            self.assertNotIn("MUSIC_U", raised.exception.detail)
            self.assertNotIn("music-api.test", raised.exception.detail)

    async def test_legacy_http_success_preserves_risk_and_other_api_errors(self):
        cases = [({"code": -460, "data": [{}]}, 503), ({"code": 500}, 502),
                 ({"code": 200, "data": []}, 502), ([], 502)]
        for payload, expected in cases:
            self.responses = [(400, {"code": -460}), (400, {"code": -460}), (200, payload)]
            with self.subTest(payload=payload), self.assertRaises(HTTPException) as raised:
                await main.song_url("22699090", "auto", session=None)
            self.assertEqual(expected, raised.exception.status_code)

    async def test_legacy_non_json_http_error_keeps_status_without_body(self):
        self.responses = [(400, {"code": -460}), (400, {"code": -460})]
        response = httpx.Response(502, text="MUSIC_U=do-not-reflect", request=httpx.Request("GET", "http://music-api.test"))
        error = httpx.HTTPStatusError("upstream failed", request=response.request, response=response)
        with patch.object(main.netease, "song_url", side_effect=error):
            with self.assertRaises(HTTPException) as raised:
                await main.song_url("22699090", "auto", session=None)
        self.assertEqual(502, raised.exception.status_code)
        self.assertIn("HTTP 502", raised.exception.detail)
        self.assertNotIn("MUSIC_U", raised.exception.detail)

    async def test_playback_payload_uses_the_same_auto_fallback(self):
        self.responses = [(400, {"code": -460}), (200, self.playable())]
        result = await main._resolve_netease_playback_payload(
            song_id="22699090", cookie="MUSIC_U=test-secret", quality_level="auto",
            artist="Artist", album="Album", artwork_url="https://img.example/cover.jpg", duration_ms=180000,
        )
        self.assertEqual("https://audio.example/song.mp3", result[0])
        self.assertFalse(result[1])

    async def test_successful_high_quality_does_not_make_fallback_request(self):
        self.responses = [(200, self.playable("jymaster"))]
        result = await main.song_url("22699090", "auto", session=None)
        self.assertEqual("jymaster", result["level"])
        self.assertEqual(1, len(self.requests))

    async def test_existing_paid_track_trial_fallback_is_preserved(self):
        self.responses = [
            (200, {"code": 200, "data": [{"id": 22699090, "code": 200, "url": None, "fee": 1}]}),
            (200, self.playable()),
        ]
        result = await main.song_url("22699090", "auto", session=None)
        self.assertTrue(result["trial"])
        self.assertEqual("/song/url", self.requests[1].url.path)
        self.assertEqual("128000", self.requests[1].url.params["br"])
