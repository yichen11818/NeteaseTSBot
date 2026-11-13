import asyncio
from contextlib import ExitStack
from types import SimpleNamespace
import tempfile
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend import main
from backend.db import Base
from backend.models import HistoryItem, QueueItem
from backend.queue_quality import qqmusic_queue_quality
from backend.runtime_config import initialize_runtime_settings, settings_payload, update_settings


class SourceQualityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine('sqlite:///:memory:')
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine)
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(main, 'new_session', side_effect=self.sessions))
        stack.enter_context(patch.object(main, '_schedule_ts_description_update'))
        stack.enter_context(patch.multiple(main.settings, netease_default_quality='standard', qqmusic_default_quality='128'))
        stack.enter_context(patch.object(main, '_get_admin_qqmusic_cookie', return_value='fixture'))
        self.qq_url = stack.enter_context(patch.object(main.qqmusic, 'get_music_url_simple', AsyncMock(return_value='https://audio.example.test/opaque')))
        self.start = stack.enter_context(patch.object(main, '_start_resolved_queue_item', AsyncMock()))
        stack.enter_context(patch.multiple(main, _playback_lock=asyncio.Lock(), _play_request_generation=0,
            _pending_play_request_generation=None, _pending_queue_item_id=None))

    async def add_netease(self, **kwargs):
        return await main._enqueue_netease_song(song_id='1', title='Song', artist='Artist',
            requested_by='test', play_now=False, **kwargs)

    async def add_qq(self, **kwargs):
        return await main._enqueue_qqmusic_song(song_mid='mid', title='Song', artist='Artist',
            requested_by='test', play_now=False, **kwargs)

    def row(self, item_id):
        with self.sessions() as session:
            return session.get(QueueItem, item_id)

    async def test_omitted_and_null_follow_provider_defaults_but_auto_is_explicit(self):
        for kwargs, expected in [({}, 'standard'), ({'quality_level': None}, 'standard'),
            ({'quality_level': 'auto'}, 'auto'), ({'quality_level': 'hires'}, 'hires')]:
            item_id, _ = await self.add_netease(**kwargs)
            self.assertEqual(expected, main._extract_netease_queue_level(self.row(item_id).source_url))
        for kwargs, expected in [({}, '128'), ({'quality': None}, '128'), ({'quality': '320'}, '320')]:
            item_id, _ = await self.add_qq(**kwargs)
            self.assertEqual(expected, self.qq_url.await_args.args[1])
            self.assertEqual(expected, qqmusic_queue_quality(self.row(item_id).source_url))

    async def test_invalid_or_cross_provider_quality_is_rejected_without_enqueue(self):
        for kwargs in [{'quality_level': '320'}, {'quality_level': ''}]:
            with self.assertRaises(HTTPException):
                await self.add_netease(**kwargs)
        for quality in ['auto', 'lossless', '', 'flac']:
            with self.assertRaises(HTTPException):
                await self.add_qq(quality=quality)
        with self.sessions() as session:
            self.assertEqual([], list(session.execute(select(QueueItem)).scalars()))
        self.qq_url.assert_not_awaited()

    async def test_new_defaults_do_not_rewrite_queued_choices_or_public_urls(self):
        ncm_id, _ = await self.add_netease()
        qq_id, _ = await self.add_qq()
        with patch.multiple(main.settings, netease_default_quality='auto', qqmusic_default_quality='320'):
            await main._play_queue_item_internal(qq_id, requested_by='test')
            ncm_new, _ = await self.add_netease()
        self.assertEqual('128', self.qq_url.await_args.args[1])
        self.assertEqual('standard', main._extract_netease_queue_level(self.row(ncm_id).source_url))
        self.assertEqual('auto', main._extract_netease_queue_level(self.row(ncm_new).source_url))
        self.assertEqual('https://audio.example.test/opaque', main._serialize_queue_item(self.row(qq_id))['source_url'])

    async def test_history_is_new_enqueue_and_accepts_explicit_provider_override(self):
        ncm = HistoryItem(track_id='netease:1', title='NCM', artist='Artist')
        qq = HistoryItem(track_id='qqmusic:mid', title='QQ', artist='Artist')
        first = await main._replay_history_item(ncm, play_now=False, requested_by='history')
        second = await main._replay_history_item(qq, play_now=False, requested_by='history')
        third = await main._replay_history_item(qq, play_now=False, requested_by='history', quality='m4a')
        self.assertEqual('standard', main._extract_netease_queue_level(self.row(first['queue_id']).source_url))
        self.assertEqual('128', qqmusic_queue_quality(self.row(second['queue_id']).source_url))
        self.assertEqual('m4a', qqmusic_queue_quality(self.row(third['queue_id']).source_url))

    async def test_request_models_represent_follow_server_as_none(self):
        self.assertIsNone(main.AddNeteaseQueueRequest(song_id='1', title='s').level)
        self.assertIsNone(main.AddQQMusicQueueRequest(song_mid='mid', title='s').quality)
        self.assertIsNone(main.ExternalQueueRequest().level)
        self.assertIsNone(main.ExternalQueueRequest().quality)

    async def test_web_and_external_enqueues_resolve_the_same_provider_defaults(self):
        web = await main.add_queue_netease(main.AddNeteaseQueueRequest(song_id='1', title='Web'))
        external = await main.external_add_queue(main.ExternalQueueRequest(song_id='2', title='External',
            artist='Artist', album='Album', cover_url='cover', duration_ms=180000))
        qq = await main.external_add_queue(main.ExternalQueueRequest(source='qqmusic', song_mid='mid',
            title='QQ', artist='Artist', album='Album', cover_url='cover', duration_ms=180000))
        for item_id in [web['id'], external['queue_id']]:
            self.assertEqual('standard', main._extract_netease_queue_level(self.row(item_id).source_url))
        self.assertEqual('128', qqmusic_queue_quality(self.row(qq['queue_id']).source_url))
        with self.assertRaises(HTTPException):
            await main.external_add_queue(main.ExternalQueueRequest(source='qqmusic', level='standard'))

    async def test_chat_add_and_playlist_import_follow_server(self):
        with patch.object(main.netease, 'search', AsyncMock(return_value={'result': {'songs': [
            {'id': 1, 'name': 'Chat', 'ar': [{'name': 'Artist'}]}]}})), patch.object(
            main.netease, 'playlist_detail', AsyncMock(return_value={'playlist': {'tracks': [
                {'id': 2, 'name': 'Playlist'}]}})), patch.object(main, '_get_admin_cookie_or_none', return_value='fixture'), patch.object(
            main.voice, 'get_status', AsyncMock(return_value=SimpleNamespace(state='STATE_PLAYING'))), patch.object(
            main.voice, 'send_notice', AsyncMock()):
            await main._handle_chat_command('Alice', 'add test', invoker_unique_id='alice')
            await main._handle_chat_command('Alice', 'playlist id:123', invoker_unique_id='alice')
        with self.sessions() as session:
            rows = session.execute(select(QueueItem)).scalars().all()
        self.assertEqual(2, len(rows))
        self.assertEqual(['standard', 'standard'], [main._extract_netease_queue_level(row.source_url) for row in rows])

    async def test_console_persists_defaults_and_exposes_only_safe_public_values(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(main.settings, 'voice_config_file', str(Path(directory) / 'voice.json')), self.sessions() as session:
            initialize_runtime_settings(session)
            fields = {item['key']: item for item in settings_payload(session)['fields']}
            self.assertEqual('music_netease', fields['backend.netease_default_quality']['group'])
            self.assertEqual(['m4a', '128', '320'], fields['backend.qqmusic_default_quality']['options'])
            update_settings(session, {'backend.netease_default_quality': 'hires', 'backend.qqmusic_default_quality': 'm4a'})
            initialize_runtime_settings(session)
            self.assertEqual(('hires', 'm4a'), (main.settings.netease_default_quality, main.settings.qqmusic_default_quality))
            public = main.public_config()['music_quality']
            self.assertEqual('hires', public['netease']['default'])
            self.assertEqual(['m4a', '128', '320'], public['qqmusic']['options'])
