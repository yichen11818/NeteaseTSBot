import asyncio
from collections import Counter
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend import main
from backend.db import Base
from backend.models import QueueItem


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
        patches.enter_context(patch.object(main, '_AUTO_PLAY_RETRY_DELAYS', (0, 0, 0), create=True))
        patches.enter_context(patch.object(main, '_AUTO_PLAY_COOLDOWN_DELAY', 0, create=True))
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
        patches.enter_context(patch.object(main.voice, 'get_status', AsyncMock(return_value=SimpleNamespace(state='STATE_IDLE'))))
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

    async def test_cooldown_recovers_same_track_after_short_retries_exhaust(self):
        await self.finish_with_failure(failures=6)
        await self.wait_retry()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())
        self.assertEqual(7, self.calls['20'])
        self.assertEqual(2, self.play.await_count)

    async def reach_cooldown(self):
        entered = asyncio.Event()
        original_sleep = asyncio.sleep
        main._AUTO_PLAY_COOLDOWN_DELAY = 300

        async def sleep(delay):
            if delay == 300:
                entered.set()
                await asyncio.Event().wait()
            await original_sleep(delay)

        with patch.object(main.asyncio, 'sleep', side_effect=sleep):
            await self.finish_with_failure(failures=100)
            await asyncio.wait_for(entered.wait(), timeout=1)
        return main._auto_play_retry_task

    async def test_stop_cancels_long_cooldown_and_preserves_waiting_track(self):
        task = await self.reach_cooldown()
        self.assertEqual(4, self.calls['20'])
        self.assertIsNone(main._current_queue_item_id)
        await main._handle_chat_command('user', 'stop')
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertEqual([20, 30], self.queued())
        self.assertEqual(4, self.calls['20'])

    async def test_new_play_during_long_cooldown_supersedes_recovery(self):
        task = await self.reach_cooldown()
        await main._play_queue_item_internal(30, requested_by='manual')
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual(4, self.calls['20'])

    async def test_nontransient_error_during_cooldown_stops_recovery(self):
        original_resolver = self.resolver.side_effect

        async def resolve(**kwargs):
            if kwargs['song_id'] == '20' and self.calls['20'] >= 4:
                self.calls['20'] += 1
                raise HTTPException(status_code=400, detail='invalid source request')
            return await original_resolver(**kwargs)

        self.resolver.side_effect = resolve
        await self.finish_with_failure(failures=100)
        await self.wait_retry()
        self.assertEqual(5, self.calls['20'])
        self.assertIsNone(main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())

    async def test_stop_cancels_recovery(self):
        main._AUTO_PLAY_RETRY_DELAYS = (60,)
        await self.finish_with_failure()
        task = main._auto_play_retry_task
        await main._handle_chat_command('user', 'stop')
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertIsNone(main._current_queue_item_id)
        self.assertEqual([20, 30], self.queued())

    async def test_clear_cancels_recovery_and_clears_queue(self):
        main._AUTO_PLAY_RETRY_DELAYS = (60,)
        await self.finish_with_failure()
        task = main._auto_play_retry_task
        with self.sessions() as session:
            await main._clear_queue_internal(session)
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertEqual([], self.queued())

    async def test_new_playback_supersedes_waiting_recovery(self):
        main._AUTO_PLAY_RETRY_DELAYS = (60,)
        await self.finish_with_failure()
        task = main._auto_play_retry_task
        await main._play_queue_item_internal(30, requested_by='manual')
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual('stream:30', self.play.await_args.kwargs['source_url'])

    async def test_pause_cancels_recovery_without_blocking_chat_worker(self):
        main._AUTO_PLAY_RETRY_DELAYS = (60,)
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
        main._AUTO_PLAY_RETRY_DELAYS = (60,)
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
