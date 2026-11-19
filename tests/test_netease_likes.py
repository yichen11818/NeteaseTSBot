from unittest.mock import AsyncMock, patch
import unittest

from starlette.requests import Request

from backend import main


class NeteaseLikesTests(unittest.IsolatedAsyncioTestCase):
    async def test_likelist_adds_track_added_timestamps_for_sorting(self):
        request = Request({
            "type": "http",
            "method": "GET",
            "path": "/netease/likes",
            "headers": [(b"x-netease-cookie", b"MUSIC_U=test-secret")],
        })
        with (
            patch.object(main.netease, "user_account", AsyncMock(return_value={
                "profile": {"userId": 42},
            })),
            patch.object(main.netease, "likelist", AsyncMock(return_value={
                "ids": [11, 22],
            })),
            patch.object(main.netease, "song_detail", AsyncMock(return_value={
                "songs": [{"id": 11, "name": "First"}, {"id": 22, "name": "Second"}],
            })),
            patch.object(main.netease, "user_playlist", AsyncMock(return_value={
                "playlist": [{"id": 99, "specialType": 5}],
            })),
            patch.object(main.netease, "playlist_detail", AsyncMock(return_value={
                "playlist": {
                    "trackIds": [
                        {"id": 11, "at": 1000},
                        {"id": 22, "at": 2000},
                    ],
                },
            })),
        ):
            result = await main.netease_likelist(request, offset=0, limit=0)

        self.assertEqual([1000, 2000], [song["added_at"] for song in result["songs"]])


if __name__ == "__main__":
    unittest.main()
