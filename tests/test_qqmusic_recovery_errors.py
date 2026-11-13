import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend.qqmusic import QQMusicClient


class QQRecoveryErrorsTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_failure_is_not_misreported_as_permanent_missing_song(self):
        client = QQMusicClient()
        with patch.object(client, 'get_music_url', AsyncMock(side_effect=httpx.ConnectError('temporary'))):
            with self.assertRaises(httpx.ConnectError):
                await client.get_music_url_simple('song', '128')

    async def test_membership_restriction_still_has_no_playable_url(self):
        client = QQMusicClient()
        data = {'req_1': {'data': {'sip': ['https://audio.example.test/'], 'midurlinfo': [{'result': 104003}]}}}
        with patch.object(client, 'get_music_url', AsyncMock(return_value=data)):
            self.assertIsNone(await client.get_music_url_simple('song', '128'))
