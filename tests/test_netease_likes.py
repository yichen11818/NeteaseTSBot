from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest

import httpx
from fastapi import HTTPException
from starlette.requests import Request

from backend import main


class NeteaseLikesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.songs = [{"id": 11, "name": "First"}, {"id": 22, "name": "Second"}]
        self.client = SimpleNamespace(
            user_account=AsyncMock(return_value={"profile": {"userId": 42}}),
            likelist=AsyncMock(return_value={"ids": [11, 22]}),
            song_detail=AsyncMock(return_value={"songs": list(reversed(self.songs))}),
            user_playlist=AsyncMock(return_value={"playlist": [{"id": 99, "specialType": 5}]}),
            playlist_detail=AsyncMock(return_value={"playlist": {"trackIds": [
                {"id": 11, "at": 1000}, {"id": 22, "at": 2000},
            ]}}),
        )
        patcher = patch.object(main, "netease", self.client)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.request = Request({"type": "http", "method": "GET", "path": "/netease/likes",
                                "headers": [(b"x-netease-cookie", b"MUSIC_U=test-secret")]})

    async def load(self, **pagination):
        return await main.netease_likelist(self.request, **pagination)

    @staticmethod
    def upstream_error():
        request = httpx.Request("GET", "http://music-api.test?cookie=secret")
        response = httpx.Response(500, request=request, text="MUSIC_U=secret")
        return httpx.HTTPStatusError("MUSIC_U=secret", request=request, response=response)

    async def test_timestamps_preserve_original_order_without_mutating_source_songs(self):
        result = await self.load()
        self.assertEqual([11, 22], [song["id"] for song in result["songs"]])
        self.assertEqual([1000, 2000], [song["added_at"] for song in result["songs"]])
        self.assertFalse(result["has_more"])
        self.assertNotIn("added_at", self.songs[0])

    async def test_full_collection_fetches_every_batch(self):
        self.client.likelist.return_value = {"ids": list(range(1, 402))}
        self.client.song_detail.side_effect = lambda **args: {
            "songs": [{"id": int(value)} for value in args["song_id"].split(",")]
        }
        result = await self.load()
        self.assertEqual(401, len(result["songs"]))
        self.assertEqual(3, self.client.song_detail.await_count)
        self.assertFalse(result["has_more"])

    async def test_failed_song_batch_is_not_returned_as_complete_collection(self):
        self.client.song_detail.side_effect = self.upstream_error()
        with self.assertRaises(HTTPException) as raised:
            await self.load()
        self.assertEqual(502, raised.exception.status_code)
        self.assertIn("HTTP 500", raised.exception.detail)
        self.assertNotIn("secret", raised.exception.detail)

    async def test_timestamp_http_and_business_errors_are_visible(self):
        self.client.playlist_detail.side_effect = self.upstream_error()
        with self.assertRaises(HTTPException) as raised:
            await self.load()
        self.assertIn("收藏时间", raised.exception.detail)
        self.assertNotIn("MUSIC_U", raised.exception.detail)
        self.client.playlist_detail.side_effect = None
        self.client.playlist_detail.return_value = {"code": 500}
        with self.assertRaises(HTTPException):
            await self.load()

    async def test_missing_liked_playlist_is_an_explicit_error(self):
        self.client.user_playlist.return_value = {"playlist": []}
        with self.assertRaises(HTTPException) as raised:
            await self.load()
        self.assertIn("喜欢歌单", raised.exception.detail)

    async def test_empty_collection_does_not_request_song_details_or_timestamps(self):
        self.client.likelist.return_value = {"ids": []}
        result = await self.load()
        self.assertEqual([], result["songs"])
        self.assertEqual(0, result["total"])
        self.client.song_detail.assert_not_awaited()
        self.client.user_playlist.assert_not_awaited()

    async def test_pagination_remains_available_for_api_consumers(self):
        result = await self.load(offset=1, limit=1)
        self.assertEqual([22], [song["id"] for song in result["songs"]])
        self.assertEqual(2, result["total"])
        self.assertFalse(result["has_more"])
        first = await self.load(offset=-1, limit=1)
        self.assertEqual(0, first["offset"])
        self.assertTrue(first["has_more"])

    async def test_ignores_another_users_liked_playlist(self):
        self.client.user_playlist.return_value = {"playlist": [
            {"id": 98, "specialType": 5, "creator": {"userId": 7}},
            {"id": 99, "specialType": 5, "creator": {"userId": 42}},
        ]}
        await self.load()
        self.client.playlist_detail.assert_awaited_once_with("99", cookie="MUSIC_U=test-secret")

    async def test_malformed_timestamp_is_not_silently_omitted(self):
        self.client.playlist_detail.return_value = {"playlist": {"trackIds": [{"id": 11, "at": "invalid"}]}}
        with self.assertRaises(HTTPException):
            await self.load()

    async def test_non_json_timestamp_response_returns_safe_upstream_error(self):
        self.client.playlist_detail.side_effect = ValueError("MUSIC_U=secret")
        with self.assertRaises(HTTPException) as raised:
            await self.load()
        self.assertEqual(502, raised.exception.status_code)
        self.assertNotIn("secret", raised.exception.detail)
