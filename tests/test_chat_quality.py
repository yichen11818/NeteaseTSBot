import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend import main
from backend.config import Settings, settings
from backend.runtime_config import DEFINITION_BY_KEY, validate_value


class ChatQualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_play_uses_server_standard_preference(self):
        with (
            patch.dict(settings.__dict__, {'netease_chat_quality': 'STANDARD'}),
            patch.object(main, 'new_session'),
            patch.object(main, '_get_admin_cookie', return_value='test-cookie'),
            patch.object(main.netease, 'song_detail', AsyncMock(return_value={'songs': [{'id': 123, 'name': 'Track', 'ar': [], 'al': {}}]})),
            patch.object(main, '_enqueue_netease_song', AsyncMock(return_value=(1, False))) as enqueue,
            patch.object(main.voice, 'send_notice', AsyncMock()),
        ):
            await main._handle_chat_command('user', 'play 123')
        self.assertEqual('standard', enqueue.await_args.kwargs['quality_level'])

    async def test_chat_playlist_uses_server_standard_preference(self):
        with (
            patch.dict(settings.__dict__, {'netease_chat_quality': 'STANDARD'}),
            patch.object(main, '_ts_playlist_results', {}),
            patch.object(main.netease, 'search', AsyncMock(return_value={'result': {'playlists': [{'id': 123, 'name': 'List'}]}})),
            patch.object(main.netease, 'playlist_detail', AsyncMock(return_value={'playlist': {'name': 'List', 'tracks': [{'id': 11, 'name': 'Track', 'ar': [], 'al': {}}]}})),
            patch.object(main, '_get_admin_cookie_or_none', return_value='test-cookie'),
            patch.object(main, '_enqueue_netease_song', AsyncMock(return_value=(1, False))) as enqueue,
            patch.object(main.voice, 'get_status', AsyncMock(return_value=SimpleNamespace(state='STATE_PLAYING'))),
            patch.object(main.voice, 'send_notice', AsyncMock()),
        ):
            await main._handle_chat_command('user', 'playlist List', invoker_unique_id='user')
            await main._handle_chat_command('user', 'select 1', invoker_unique_id='user')
        self.assertEqual('standard', enqueue.await_args.kwargs['quality_level'])

    async def test_server_preference_is_validated_runtime_setting(self):
        self.assertEqual('STANDARD', Settings(netease_chat_quality='STANDARD').netease_chat_quality)
        definition = DEFINITION_BY_KEY['backend.netease_chat_quality']
        self.assertEqual('STANDARD', validate_value(definition, 'standard'))
        with self.assertRaises(ValueError):
            validate_value(definition, 'unsupported')
