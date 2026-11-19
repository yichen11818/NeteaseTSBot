import asyncio
import time
import tempfile
from pathlib import Path
from collections import Counter
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from yt_dlp.utils import DownloadError, ExtractorError
from yt_dlp.networking.exceptions import HTTPError as YTDLPHTTPError

from backend import main
from backend.db import Base
from backend.models import QueueItem
from backend.runtime_config import initialize_runtime_settings


class AutoPlayRetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine('sqlite:///:memory:')
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine)
        with self.sessions() as session:
            session.add_all(QueueItem(id=i, track_id=f'netease:{i}', title=f'Track {i}', artist='Artist', album='Album', duration=180000, cover_url='https://example.test/cover', source_url='') for i in [10, 20, 30])
            session.commit()
        patches = ExitStack()
        self.addCleanup(patches.close)
        self.addAsyncCleanup(self.cancel_retry)
        patches.enter_context(patch.object(main, 'new_session', side_effect=self.sessions))
        patches.enter_context(patch.object(main, '_schedule_ts_description_update'))
        patches.enter_context(patch.object(main, '_get_admin_cookie', return_value='test-cookie'))
        patches.enter_context(patch.object(main, '_auto_play_retry_task', None, create=True))
        patches.enter_context(patch.multiple(main.settings,
            playback_recovery_enabled=True, playback_retry_count=3,
            playback_retry_initial_delay_seconds=15, playback_retry_max_delay_seconds=60,
            playback_exhausted_action='SKIP', playback_cooldown_seconds=300,
            playback_failed_tracks_before_cooldown=3))
        self.hold_retry = False
        self.delays = []
        real_sleep = asyncio.sleep

        async def fake_wait(delay):
            self.delays.append(delay)
            if self.hold_retry:
                await asyncio.Event().wait()
            await real_sleep(0)

        patches.enter_context(patch.object(main, '_recovery_wait', side_effect=fake_wait))
        patches.enter_context(patch.object(main, '_deferred_queue_item_ids', set(), create=True))
        patches.enter_context(patch.object(main, '_recovery_state', None, create=True))
        patches.enter_context(patch.multiple(main,
            _repeat_mode='none', _shuffle_enabled=False, _shuffle_queue=[], _current_shuffle_index=-1,
            _current_queue_item_id=None, _pending_queue_item_id=None, _current_source_url='',
            _pending_play_request_generation=None, _playback_lock=asyncio.Lock(), _play_request_generation=0,
            _play_started_at=None, _paused_at=None, _paused_total_s=0, _current_duration_ms=0,
            _current_artist='', _current_album='', _current_artwork_url='',
        ))
        self.play = patches.enter_context(patch.object(main.voice, 'play', AsyncMock()))
        for method in ['stop', 'pause', 'send_notice']:
            patches.enter_context(patch.object(main.voice, method, AsyncMock()))
        patches.enter_context(patch.object(main.voice, 'get_status', AsyncMock(return_value=SimpleNamespace(
            state='STATE_IDLE', now_playing_title='', now_playing_source_url='', volume_percent=100,
            config_revision='test', teamspeak_connected=True))))
        self.calls = Counter()
        self.failures = Counter()

        async def resolve(*, song_id, **kwargs):
            self.calls[song_id] += 1
            if self.failures[song_id]:
                self.failures[song_id] -= 1
                raise HTTPException(status_code=503, detail='temporary upstream risk')
            return f'stream:{song_id}', False, '', 180000, 'Artist', 'Album', 'https://example.test/cover'

        self.resolver = patches.enter_context(patch.object(main, '_resolve_netease_playback_payload', AsyncMock(side_effect=resolve)))

    async def cancel_retry(self):
        task = main._auto_play_retry_task
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def queued(self):
        with self.sessions() as session:
            return list(session.execute(select(QueueItem.id).order_by(QueueItem.id)).scalars())

    async def finish_with_failure(self, *, failures=1):
        await main._play_queue_item_internal(10, requested_by='test')
        self.failures['20'] = failures
        await main._handle_playback_finished('stream:10')

    async def wait_retry(self):
        task = main._auto_play_retry_task
        self.assertIsNotNone(task, 'Automatic continuation must arrange recovery')
        await asyncio.wait_for(task, timeout=1)

    async def test_completion_recovers_next_track_without_losing_queue(self):
        await self.finish_with_failure()
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())
        self.assertEqual(2, self.calls['20'])

    async def test_manual_selection_reports_permanent_error_without_replacing_playing_track(self):
        original = self.resolver.side_effect
        for status in [402, 403, 404, 410]:
            with self.subTest(status=status):
                async def resolve(**kwargs):
                    if kwargs['song_id'] == '20':
                        raise HTTPException(status, 'selected track unavailable')
                    return await original(**kwargs)

                self.resolver.side_effect = resolve
                await main._play_queue_item_internal(10, requested_by='test')
                with self.sessions() as session, self.assertRaises(HTTPException) as error:
                    await main.play_queue_item(20, session=session)
                self.assertEqual(status, error.exception.status_code)
                self.assertEqual(10, main._current_queue_item_id)
                self.assertEqual([10, 20, 30], self.queued())
                self.assertEqual(0, self.calls['30'])
                self.assertIsNone(main._auto_play_retry_task)

    async def test_bilibili_permission_failure_through_both_resolvers_does_not_retry(self):
        self.hold_retry = True
        real_client = httpx.Client
        transport = httpx.MockTransport(lambda request: httpx.Response(403, request=request))
        fallback_error = ExtractorError('Video unavailable', expected=True)
        fallback = MagicMock()
        fallback.YoutubeDL.return_value.__enter__.return_value.extract_info.side_effect = DownloadError(
            'Video unavailable', exc_info=(type(fallback_error), fallback_error, None))
        with tempfile.TemporaryDirectory() as directory, patch.object(main, 'BILIBILI_AUDIO_DIR', Path(directory)), patch.object(
            main.httpx, 'Client', side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)), patch.object(
            main, '_get_yt_dlp_module', return_value=fallback), patch.object(main.settings, 'playback_exhausted_action', 'WAIT'):
            with self.assertRaises(HTTPException):
                await main.add_queue_bilibili(main.AddBilibiliQueueRequest(video_id='BV1xx411c7mD', title='Video',
                    artist='Artist', album='Album', duration_ms=180000, cover_url='cover', play_now=True))
        self.assertIsNone(main._auto_play_retry_task)
        self.assertEqual([10, 20, 30], self.queued())
        self.play.assert_not_awaited()

    async def test_superseded_manual_selection_failure_does_not_restart_cancelled_target(self):
        original = self.resolver.side_effect
        for action in ['stop', 'pause', 'select another']:
            with self.subTest(action=action):
                entered = asyncio.Event()
                release = asyncio.Event()

                async def resolve(**kwargs):
                    if kwargs['song_id'] == '20':
                        entered.set()
                        await release.wait()
                        raise HTTPException(503, 'late failure')
                    return await original(**kwargs)

                self.resolver.side_effect = resolve
                await main._play_queue_item_internal(10, requested_by='test')
                with self.sessions() as session:
                    request = asyncio.create_task(main.play_queue_item(20, session=session))
                    await asyncio.wait_for(entered.wait(), timeout=1)
                    if action == 'select another':
                        await main.play_queue_item(30, session=session)
                    elif action == 'stop':
                        await main.voice_stop()
                    else:
                        await main.voice_pause()
                    release.set()
                    try:
                        with self.assertRaises(HTTPException) as error:
                            await request
                        self.assertEqual(409, error.exception.status_code)
                        self.assertIsNone(main._auto_play_retry_task)
                        self.assertEqual({'stop': None, 'pause': 10, 'select another': 30}[action], main._current_queue_item_id)
                    finally:
                        await self.cancel_retry()

    async def test_bilibili_transient_fallback_failure_recovers_through_real_download_chain(self):
        real_client = httpx.Client
        views = 0

        def respond(request):
            nonlocal views
            if request.url.path == '/x/web-interface/wbi/view':
                views += 1
                if views == 1:
                    return httpx.Response(503, request=request)
                return httpx.Response(200, request=request, json={'code': 0, 'data': {
                    'bvid': 'BV1xx411c7mD', 'cid': 123, 'title': 'Video', 'duration': 180,
                    'owner': {'name': 'Artist'}, 'tname': 'Album', 'pic': 'cover'}})
            if request.url.path == '/x/player/playurl':
                return httpx.Response(200, request=request, json={'code': 0, 'data': {
                    'dash': {'audio': [{'baseUrl': 'https://audio.example.test/song.m4s'}]}}})
            return httpx.Response(200, request=request, content=b'fixture audio')

        transport = httpx.MockTransport(respond)
        upstream_error = YTDLPHTTPError(SimpleNamespace(status=503, reason='Service Unavailable'))
        extractor_error = ExtractorError('Upstream unavailable', cause=upstream_error)
        fallback = MagicMock()
        fallback.YoutubeDL.return_value.__enter__.return_value.extract_info.side_effect = DownloadError(
            'Upstream unavailable', exc_info=(type(extractor_error), extractor_error, None))
        with tempfile.TemporaryDirectory() as directory, patch.object(main, 'BILIBILI_AUDIO_DIR', Path(directory)), patch.object(
            main.httpx, 'Client', side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)), patch.object(
            main, '_get_yt_dlp_module', return_value=fallback):
            with self.assertRaises(HTTPException) as error:
                await main.add_queue_bilibili(main.AddBilibiliQueueRequest(video_id='BV1xx411c7mD', title='Video',
                    artist='Artist', album='Album', duration_ms=180000, cover_url='cover', play_now=True))
            self.assertEqual(503, error.exception.status_code)
            await self.wait_retry()
            self.assertTrue(Path(self.play.await_args.kwargs['source_url']).is_file())
        self.assertEqual(31, main._current_queue_item_id)
        self.assertEqual([15], self.delays)
        self.play.assert_awaited_once()

    async def test_natural_completion_still_skips_permanently_unavailable_tracks(self):
        original = self.resolver.side_effect

        async def resolve(**kwargs):
            if kwargs['song_id'] == '20':
                raise HTTPException(403, 'permission denied')
            return await original(**kwargs)

        self.resolver.side_effect = resolve
        await main._play_queue_item_internal(10, requested_by='test')
        await main._handle_playback_finished('stream:10')
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual([30], self.queued())
        self.assertIsNone(main._auto_play_retry_task)

    async def test_bilibili_failure_categories_survive_metadata_and_download_wrappers(self):
        real_client = httpx.Client
        expected = ExtractorError('Video unavailable', expected=True)
        cases = [
            ('business restriction', 200, {'code': -101}, expected, None),
            ('malformed response', 200, None, TypeError('invalid extractor response'), None),
            ('fallback restriction after API outage', 503, None, expected, None),
            ('permission followed by timeout', 403, None, TimeoutError('temporary'), None),
            ('invalid protocol', httpx.UnsupportedProtocol('invalid URL'), None, httpx.UnsupportedProtocol('invalid URL'), None),
            ('rate limited', 429, None, YTDLPHTTPError(SimpleNamespace(status=429, reason='Too Many Requests')), 'rate_limited'),
            ('network timeout', httpx.ReadTimeout('temporary'), None, TimeoutError('temporary'), 'network_timeout'),
        ]
        for label, status, payload, cause, reason in cases:
            for complete_metadata in [False, True]:
                with self.subTest(case=label, complete_metadata=complete_metadata):
                    self.hold_retry = True

                    def respond(request):
                        if isinstance(status, Exception):
                            raise status
                        return httpx.Response(status, request=request, **({'json': payload} if payload is not None else {'content': b'invalid json'}))

                    wrapped = cause if isinstance(cause, ExtractorError) else ExtractorError('Fallback failed', cause=cause)
                    fallback = MagicMock()
                    fallback.YoutubeDL.return_value.__enter__.return_value.extract_info.side_effect = DownloadError(
                        'Fallback failed', exc_info=(type(wrapped), wrapped, None))
                    transport = httpx.MockTransport(respond)
                    fields = dict(artist='Artist', album='Album', duration_ms=180000, cover_url='cover') if complete_metadata else {}
                    with tempfile.TemporaryDirectory() as directory, patch.object(main, 'BILIBILI_AUDIO_DIR', Path(directory)), patch.object(
                        main.httpx, 'Client', side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)), patch.object(
                        main, '_get_yt_dlp_module', return_value=fallback):
                        with self.assertRaises(HTTPException):
                            await main.add_queue_bilibili(main.AddBilibiliQueueRequest(video_id='BV1xx411c7mD', title='Video', play_now=True, **fields))
                        await asyncio.sleep(0)
                        try:
                            if reason is None:
                                self.assertIsNone(main._auto_play_retry_task)
                                self.assertEqual([10, 20, 30], self.queued())
                            else:
                                status_payload = await main.voice_status()
                                self.assertTrue(status_payload['recovery']['pending'])
                                self.assertEqual(reason, status_payload['recovery']['last_reason'])
                                self.assertEqual([10, 20, 30, 31], self.queued())
                        finally:
                            await self.cancel_retry()
                            with self.sessions() as session:
                                for item_id in self.queued():
                                    if item_id > 30:
                                        main.delete_queue_item(item_id, session=session)

    async def test_repeat_one_retries_the_same_track(self):
        main._repeat_mode = 'one'
        await main._play_queue_item_internal(10, requested_by='test')
        self.failures['10'] = 1
        await main._handle_playback_finished('stream:10')
        await self.wait_retry()
        self.assertEqual(10, main._current_queue_item_id)
        self.assertEqual([10, 20, 30], self.queued())

    async def test_shuffle_retries_the_waiting_track_without_skipping_it(self):
        main._shuffle_enabled = True
        main._shuffle_queue = [10, 20, 30]
        await self.finish_with_failure()
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())

    async def test_repeat_all_preserves_completed_and_waiting_entries(self):
        main._repeat_mode = 'all'
        await self.finish_with_failure()
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([10, 20, 30], self.queued())

    async def test_exhausted_track_is_temporarily_skipped_and_retained(self):
        await self.finish_with_failure(failures=100)
        await self.wait_retry()
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())
        self.assertEqual(4, self.calls['20'])
        self.assertEqual(2, self.play.await_count)

    async def test_configured_retry_count_limits_attempts_before_skip(self):
        with patch.object(main.settings, 'playback_retry_count', 1):
            await self.finish_with_failure(failures=100)
            await self.wait_retry()
        self.assertEqual(2, self.calls['20'])
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())

    async def test_wait_policy_keeps_target_and_restarts_after_cooldown(self):
        with patch.object(main.settings, 'playback_exhausted_action', 'WAIT'):
            await self.finish_with_failure(failures=4)
            await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual(0, self.calls['30'])
        self.assertEqual([15, 30, 60, 300], self.delays)

    async def test_zero_retries_skips_without_requesting_failed_target_again(self):
        with patch.object(main.settings, 'playback_retry_count', 0):
            await self.finish_with_failure(failures=100)
            await self.wait_retry()
        self.assertEqual(1, self.calls['20'])
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())

    async def test_policy_snapshot_keeps_bounded_backoff_when_settings_change(self):
        with patch.object(main.settings, 'playback_retry_count', 4), patch.object(
            main.settings, 'playback_retry_max_delay_seconds', 20):
            await self.finish_with_failure(failures=4)
        # Applying a different policy does not alter a recovery already in progress.
        with patch.object(main.settings, 'playback_retry_count', 0):
            await self.wait_retry()
        self.assertEqual([15, 20, 20, 20], self.delays)
        self.assertEqual(20, main._current_queue_item_id)

    async def test_disabled_recovery_preserves_immediate_error_without_worker(self):
        self.failures['10'] = 1
        with patch.object(main.settings, 'playback_recovery_enabled', False):
            with self.assertRaises(HTTPException):
                await main.voice_play()
        self.assertIsNone(main._auto_play_retry_task)
        self.assertEqual(1, self.calls['10'])
        self.assertEqual([10, 20, 30], self.queued())

    async def test_status_exposes_safe_scheduled_recovery(self):
        self.hold_retry = True
        await self.finish_with_failure()
        await asyncio.sleep(0)
        state = await main.voice_status()
        recovery = state['recovery']
        self.assertTrue(recovery['pending'])
        self.assertEqual(20, recovery['target_id'])
        self.assertEqual((1, 3, 'retry', 'upstream_unavailable'), (
            recovery['attempt'], recovery['retry_count'], recovery['phase'], recovery['last_reason']))
        self.assertGreater(recovery['next_retry_at'], time.time())
        self.assertNotIn('source_url', recovery)
        self.assertNotIn('detail', recovery)

    async def test_save_stages_disable_and_apply_cancels_pending_recovery(self):
        self.hold_retry = True
        await self.finish_with_failure()
        task = main._auto_play_retry_task
        with tempfile.TemporaryDirectory() as folder, patch.object(
            main.settings, 'voice_config_file', str(Path(folder) / 'voice.json')
        ), self.sessions() as session:
            initialize_runtime_settings(session)
            with patch.object(main, 'require_admin', return_value=(None, None)), patch.object(main, 'require_csrf'):
                await main.admin_update_settings(SimpleNamespace(
                    values={'backend.playback_recovery_enabled': False}, apply=False), None, session)
                self.assertFalse(task.done())
                await main.admin_update_settings(SimpleNamespace(values={}, apply=True), None, session)
        await asyncio.sleep(0)
        self.assertTrue(task.cancelled())
        self.assertIsNone(main._auto_play_retry_task)
        self.assertEqual([20, 30], self.queued())

    async def test_new_qq_request_recovers_with_its_explicit_quality(self):
        with patch.object(main, '_get_admin_qqmusic_cookie', return_value='test-cookie'), patch.object(
            main.qqmusic, 'get_music_url_simple', AsyncMock(side_effect=[
                httpx.ConnectError('temporary'), 'https://audio.example.test/opaque',
            ])
        ) as resolve:
            with self.assertRaises(httpx.ConnectError):
                await main._enqueue_qqmusic_song(song_mid='song', title='QQ song', artist='Artist',
                    quality='128', play_now=True, requested_by='test')
            await self.wait_retry()
        self.assertEqual(['128', '128'], [call.args[1] for call in resolve.await_args_list])
        self.assertEqual(31, main._current_queue_item_id)

    async def test_new_bilibili_request_keeps_target_on_temporary_resolution_failure(self):
        with patch.object(main, '_hydrate_bilibili_track_metadata', AsyncMock(return_value=(
            180000, 'Artist', 'Album', 'cover'))), patch.object(main, '_resolve_bilibili_playback_payload',
            AsyncMock(side_effect=[HTTPException(503, 'temporary'), (
                'stream:bilibili', 180000, 'Artist', 'Album', 'cover')])):
            with self.assertRaises(HTTPException):
                await main._enqueue_bilibili_song(video_id='BV1234567890', title='Video', artist='Artist',
                    play_now=True, requested_by='test')
            await self.wait_retry()
        self.assertEqual(31, main._current_queue_item_id)
        self.assertEqual('stream:bilibili', self.play.await_args.kwargs['source_url'])

    async def test_next_while_waiting_advances_past_waiting_target(self):
        self.hold_retry = True
        await self.finish_with_failure()
        with patch.object(main.voice, 'skip', AsyncMock()):
            await main.voice_next()
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual(1, self.calls['20'])

    async def test_stop_endpoint_cancels_waiting_recovery(self):
        self.hold_retry = True
        await self.finish_with_failure()
        task = main._auto_play_retry_task
        await main.voice_stop()
        self.assertTrue(task.cancelled())
        self.assertIsNone(main._auto_play_retry_task)
        self.assertIsNone(main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())

    async def test_deferred_track_is_revisited_after_other_tracks_finish(self):
        await self.finish_with_failure(failures=4)
        await self.wait_retry()
        self.assertEqual(30, main._current_queue_item_id)
        await main._handle_playback_finished('stream:30')
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([20], self.queued())

    async def test_permanently_unavailable_next_track_does_not_end_deferred_recovery(self):
        original = self.resolver.side_effect

        async def resolve(**kwargs):
            if kwargs['song_id'] == '30':
                raise HTTPException(404, 'permanently unavailable')
            return await original(**kwargs)

        self.resolver.side_effect = resolve
        await self.finish_with_failure(failures=4)
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertIn(300, self.delays)
        self.assertEqual([20], self.queued())

    async def test_old_completion_or_error_after_pause_does_not_resume_or_delete(self):
        for handler in [main._handle_playback_finished, main._handle_playback_error]:
            await main._play_queue_item_internal(10, requested_by='test')
            await main.voice_pause()
            await handler('stream:10')
            self.assertEqual(10, main._current_queue_item_id)
            self.assertIsNone(main._auto_play_retry_task)
            self.assertEqual(0, self.calls['20'])
            self.assertEqual([10, 20, 30], self.queued())

    async def test_manual_queue_play_failure_arranges_recovery(self):
        self.failures['10'] = 1
        with self.assertRaises(HTTPException):
            await main.voice_play()
        await self.wait_retry()
        self.assertEqual(10, main._current_queue_item_id)

    async def test_teamspeak_queue_play_failure_arranges_recovery(self):
        self.failures['10'] = 1
        await main._handle_chat_command('user', 'play')
        await self.wait_retry()
        self.assertEqual(10, main._current_queue_item_id)

    async def test_direct_request_recovers_while_previous_track_keeps_playing(self):
        await main._play_queue_item_internal(10, requested_by='test')
        self.failures['20'] = 1
        with self.sessions() as session:
            with self.assertRaises(HTTPException):
                await main.play_queue_item(20, session=session)
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)

    async def test_old_track_finish_does_not_cancel_waiting_manual_target(self):
        await main._play_queue_item_internal(30, requested_by='test')
        self.failures['20'] = 1
        self.hold_retry = True
        with self.sessions() as session:
            with self.assertRaises(HTTPException):
                await main.play_queue_item(20, session=session)
        task = main._auto_play_retry_task
        await main._handle_playback_finished('stream:30')
        self.assertIs(task, main._auto_play_retry_task)
        self.assertFalse(task.cancelled())
        self.assertEqual([10,20], self.queued())

    async def test_new_song_transient_start_failure_arranges_recovery(self):
        self.play.side_effect = [HTTPException(status_code=503, detail='temporary start failure'), None]
        with self.assertRaises(HTTPException):
            await main._enqueue_netease_song(song_id='40', title='Track 40', artist='Artist',
                album='Album', artwork_url='cover', duration_ms=180000,
                play_now=True, requested_by='test', quality_level='standard')
        await self.wait_retry()
        self.assertEqual(31, main._current_queue_item_id)

    async def test_old_track_error_does_not_cancel_waiting_manual_target(self):
        with self.sessions() as session:
            session.add(QueueItem(id=40, track_id='netease:40', title='Track', artist='Artist',
                album='Album', duration=180000, cover_url='cover', source_url=''))
            session.commit()
        await main._play_queue_item_internal(30, requested_by='test')
        self.failures['20'] = 1
        self.hold_retry = True
        with self.sessions() as session:
            with self.assertRaises(HTTPException):
                await main.play_queue_item(20, session=session)
        task = main._auto_play_retry_task
        await main._handle_playback_error('stream:30')
        self.assertIs(task, main._auto_play_retry_task)
        self.assertIsNone(main._current_queue_item_id)
        self.assertEqual([10,20,40], self.queued())

    async def test_manual_skip_failure_arranges_recovery(self):
        await main._play_queue_item_internal(10, requested_by='test')
        self.failures['20'] = 1
        with patch.object(main.voice, 'skip', AsyncMock()):
            with self.assertRaises(HTTPException):
                await main.voice_skip()
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())

    async def test_manual_next_failure_arranges_recovery(self):
        await main._play_queue_item_internal(10, requested_by='test')
        self.failures['20'] = 1
        with patch.object(main.voice, 'skip', AsyncMock()):
            with self.assertRaises(HTTPException):
                await main.voice_next()
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)

    async def test_new_song_request_failure_keeps_entry_and_recovers(self):
        self.failures['40'] = 1
        with self.assertRaises(HTTPException):
            await main._enqueue_netease_song(song_id='40', title='Track 40', artist='Artist',
                album='Album', artwork_url='cover', duration_ms=180000,
                play_now=True, requested_by='test', quality_level='standard')
        await self.wait_retry()
        self.assertEqual(31, main._current_queue_item_id)
        self.assertEqual([10, 20, 30, 31], self.queued())

    async def test_direct_queue_selection_retries_selected_item(self):
        self.failures['20'] = 1
        with self.sessions() as session:
            with self.assertRaises(HTTPException):
                await main.play_queue_item(20, session=session)
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([10, 20, 30], self.queued())

    async def test_repeat_one_moves_on_after_repeated_transient_failure(self):
        main._repeat_mode = 'one'
        await main._play_queue_item_internal(10, requested_by='test')
        self.failures['10'] = 100
        await main._handle_playback_finished('stream:10')
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([10, 20, 30], self.queued())

    async def reach_cooldown(self):
        entered = asyncio.Event()
        original_sleep = asyncio.sleep

        async def sleep(delay):
            if delay == 300:
                entered.set()
                await asyncio.Event().wait()
            await original_sleep(0)

        with patch.object(main, '_recovery_wait', side_effect=sleep):
            self.failures['30'] = 100
            await self.finish_with_failure(failures=100)
            await asyncio.wait_for(entered.wait(), timeout=1)
        return main._auto_play_retry_task

    async def test_stop_cancels_long_cooldown_and_preserves_waiting_track(self):
        task = await self.reach_cooldown()
        self.assertEqual(4, self.calls['20'])
        self.assertEqual(4, self.calls['30'])
        self.assertIsNone(main._current_queue_item_id)
        await main._handle_chat_command('user', 'stop')
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertEqual([20, 30], self.queued())
        self.assertEqual(4, self.calls['20'])

    async def test_new_play_during_long_cooldown_supersedes_recovery(self):
        task = await self.reach_cooldown()
        self.failures['30'] = 0
        await main._play_queue_item_internal(30, requested_by='manual')
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual(4, self.calls['20'])

    async def test_three_exhausted_candidates_trigger_cooldown_before_more_tracks(self):
        with self.sessions() as session:
            session.add_all(QueueItem(id=i, track_id=f'netease:{i}', title='Track', artist='Artist',
                album='Album', duration=180000, cover_url='cover', source_url='') for i in (40,50))
            session.commit()
        self.failures['40'] = 100
        task = await self.reach_cooldown()
        self.assertEqual([20,30,40,50], self.queued())
        self.assertEqual([4,4,4,0], [self.calls[str(i)] for i in (20,30,40,50)])
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def test_shuffle_exhausted_track_moves_to_another_track(self):
        main._shuffle_enabled = True
        main._shuffle_queue = [10,20,30]
        await self.finish_with_failure(failures=100)
        await self.wait_retry()
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual([20,30], self.queued())

    async def test_cooldown_continues_past_failed_batch_without_starving_later_tracks(self):
        with self.sessions() as session:
            session.add_all(QueueItem(id=i, track_id=f'netease:{i}', title='Track', artist='Artist',
                album='Album', duration=180000, cover_url='cover', source_url='') for i in (40,50))
            session.commit()
        self.failures.update({'20':100,'30':100,'40':100})
        original_sleep = asyncio.sleep
        cooldowns = 0

        async def sleep(delay):
            nonlocal cooldowns
            if delay == 300:
                cooldowns += 1
                if cooldowns > 1:
                    await asyncio.Event().wait()
                return
            await original_sleep(0)

        with patch.object(main, '_recovery_wait', side_effect=sleep):
            await self.finish_with_failure(failures=100)
            await self.wait_retry()
        self.assertEqual(50, main._current_queue_item_id)
        self.assertEqual(1, cooldowns)
        self.assertEqual([20,30,40,50], self.queued())

    async def test_nontransient_error_during_cooldown_stops_recovery(self):
        original_resolver = self.resolver.side_effect

        async def resolve(**kwargs):
            if kwargs['song_id'] == '20' and self.calls['20'] >= 4:
                self.calls['20'] += 1
                raise HTTPException(status_code=400, detail='invalid source request')
            return await original_resolver(**kwargs)

        self.resolver.side_effect = resolve
        self.failures['30'] = 100
        await self.finish_with_failure(failures=100)
        await self.wait_retry()
        self.assertEqual(5, self.calls['20'])
        self.assertIsNone(main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())

    async def test_stop_cancels_recovery(self):
        self.hold_retry = True
        await self.finish_with_failure()
        task = main._auto_play_retry_task
        await main._handle_chat_command('user', 'stop')
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertIsNone(main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())

    async def test_clear_cancels_recovery_and_clears_queue(self):
        self.hold_retry = True
        await self.finish_with_failure()
        task = main._auto_play_retry_task
        with self.sessions() as session:
            await main._clear_queue_internal(session)
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertEqual([], self.queued())

    async def test_new_playback_supersedes_waiting_recovery(self):
        self.hold_retry = True
        await self.finish_with_failure()
        task = main._auto_play_retry_task
        await main._play_queue_item_internal(30, requested_by='manual')
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual('stream:30', self.play.await_args.kwargs['source_url'])

    async def test_pause_cancels_recovery_without_blocking_chat_worker(self):
        self.hold_retry = True
        await self.finish_with_failure()
        task = main._auto_play_retry_task
        await asyncio.wait_for(main._handle_chat_command('user', 'pause'), timeout=1)
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertIsNone(main._current_queue_item_id)

    async def test_manual_failure_keeps_existing_error_contract(self):
        self.failures['10'] = 1
        with self.assertRaises(HTTPException):
            await main._auto_play_next_from_queue()
        self.assertIsNone(main._auto_play_retry_task)
        self.assertEqual([10, 20, 30], self.queued())

    async def test_stop_during_initial_failure_prevents_stale_recovery(self):
        await main._play_queue_item_internal(10, requested_by='test')
        started, release = asyncio.Event(), asyncio.Event()

        async def blocked(**kwargs):
            started.set()
            await release.wait()
            raise HTTPException(status_code=503, detail='temporary')

        self.resolver.side_effect = blocked
        completion = asyncio.create_task(main._handle_playback_finished('stream:10'))
        await started.wait()
        await main._handle_chat_command('user', 'stop')
        release.set()
        await completion
        self.assertIsNone(main._auto_play_retry_task)
        self.assertIsNone(main._current_queue_item_id)

    async def test_playback_error_recovers_next_track_even_in_repeat_one(self):
        main._repeat_mode = 'one'
        await main._play_queue_item_internal(10, requested_by='test')
        self.failures['20'] = 1
        await main._handle_playback_error('stream:10')
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())

    async def test_manual_play_cancels_an_inflight_retry(self):
        await main._play_queue_item_internal(10, requested_by='test')
        retry_started, release = asyncio.Event(), asyncio.Event()
        attempts = 0

        async def resolve(*, song_id, **kwargs):
            nonlocal attempts
            if song_id == '20':
                attempts += 1
                if attempts == 1:
                    raise HTTPException(status_code=503, detail='temporary')
                retry_started.set()
                await release.wait()
            return f'stream:{song_id}', False, '', 180000, 'Artist', 'Album', 'cover'

        self.resolver.side_effect = resolve
        await main._handle_playback_finished('stream:10')
        task = main._auto_play_retry_task
        await asyncio.wait_for(retry_started.wait(), timeout=1)
        await main._play_queue_item_internal(30, requested_by='manual')
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertEqual(30, main._current_queue_item_id)
        self.assertIsNone(main._pending_play_request_generation)

    async def test_duplicate_finished_event_does_not_create_another_retry(self):
        self.hold_retry = True
        await self.finish_with_failure()
        task = main._auto_play_retry_task
        await main._handle_playback_finished('stream:10')
        self.assertIs(task, main._auto_play_retry_task)
        self.assertEqual(1, self.calls['20'])

    async def pause_during_initial_resolution(self, *, fails):
        await main._play_queue_item_internal(10, requested_by='test')
        started, release = asyncio.Event(), asyncio.Event()

        async def blocked(*, song_id, **kwargs):
            started.set()
            await release.wait()
            if fails:
                raise HTTPException(status_code=503, detail='temporary')
            return f'stream:{song_id}', False, '', 180000, 'Artist', 'Album', 'cover'

        self.resolver.side_effect = blocked
        completion = asyncio.create_task(main._handle_playback_finished('stream:10'))
        await started.wait()
        await main.voice_pause()
        release.set()
        await completion
        self.assertIsNone(main._auto_play_retry_task)
        self.assertIsNone(main._current_queue_item_id)
        self.assertEqual(1, self.play.await_count)

    async def test_pause_during_initial_failure_prevents_late_recovery(self):
        await self.pause_during_initial_resolution(fails=True)

    async def test_pause_during_initial_success_prevents_late_playback(self):
        await self.pause_during_initial_resolution(fails=False)

    async def recover_from_raw_http_error(self, status, payload):
        await main._play_queue_item_internal(10, requested_by='test')
        response = httpx.Response(status, json=payload, request=httpx.Request('GET', 'http://music-api.test/song/url/v1'))
        failed = False

        async def resolve(*, song_id, **kwargs):
            nonlocal failed
            if not failed:
                failed = True
                response.raise_for_status()
            return f'stream:{song_id}', False, '', 180000, 'Artist', 'Album', 'cover'

        self.resolver.side_effect = resolve
        await main._handle_playback_finished('stream:10')
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())

    async def test_raw_upstream_http503_recovers(self):
        await self.recover_from_raw_http_error(503, {'code': 503})

    async def test_raw_upstream_http400_risk_response_recovers(self):
        await self.recover_from_raw_http_error(400, {'code': -460})
