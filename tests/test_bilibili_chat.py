import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

from fastapi import HTTPException

from backend import main


BV = 'BV1xx411c7mD'
META = dict(title='视频标题', artist='UP主', album='音乐', duration_ms=120000,
            artwork_url='https://example.test/cover.jpg')


class BilibiliChatTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        state = patch.multiple(main, _playback_lock=asyncio.Lock(), _play_request_generation=0,
                               _pending_play_request_generation=None, _pending_queue_item_id=None,
                               _bilibili_chat_tasks=set())
        state.start()
        self.addCleanup(state.stop)

    async def asyncTearDown(self):
        tasks = list(main._bilibili_chat_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        main._bilibili_chat_tasks.clear()

    async def drain(self):
        await asyncio.gather(*list(main._bilibili_chat_tasks))
        await asyncio.sleep(0)

    async def test_commands_reuse_metadata_and_enqueue_with_correct_mode(self):
        for command, play_now in [('b站', True), ('点播b站', False)]:
            with self.subTest(command=command), patch.object(
                    main, '_extract_bilibili_video_info', AsyncMock(return_value=META)) as extract, patch.object(
                    main, '_enqueue_bilibili_song', AsyncMock(return_value=(42, False))) as enqueue, patch.object(
                    main.voice, 'send_notice', AsyncMock()) as notice, patch.object(
                    main.netease, 'search', AsyncMock()) as search:
                await main._handle_chat_command('Alice', f'{command} {BV}',
                                                target_mode=1, invoker_unique_id='alice-uid')
                await self.drain()
                extract.assert_awaited_once_with(BV)
                enqueue.assert_awaited_once_with(
                    video_id=BV, title=META['title'], artist=META['artist'], album=META['album'],
                    duration_ms=META['duration_ms'], artwork_url=META['artwork_url'],
                    play_now=play_now, requested_by='Alice',
                    request_generation=ANY if play_now else None)
                self.assertIn('已开始播放' if play_now else '已加入队列', notice.call_args.args[0])
                self.assertEqual(1, notice.call_args.kwargs['target_mode'])
                search.assert_not_awaited()

    async def test_full_links_and_teamspeak_markup(self):
        for value in (BV, f'https://www.bilibili.com/video/{BV}/?p=1&share_source=copy',
                      f'https://m.bilibili.com/video/{BV}',
                      f'[URL=https://www.bilibili.com/video/{BV}]视频[/URL]',
                      f'[url]https://www.bilibili.com/video/{BV}[/url]'):
            with self.subTest(value=value):
                self.assertEqual(BV, main._parse_bilibili_chat_video_id(value))

    async def test_invalid_input_does_not_resolve_or_enqueue(self):
        with patch.object(main, '_extract_bilibili_video_info', AsyncMock()) as extract, patch.object(
                main, '_enqueue_bilibili_song', AsyncMock()) as enqueue, patch.object(
                main.voice, 'send_notice', AsyncMock()) as notice:
            for value in ('', 'BVshort', BV + 'extra', 'av123', f'https://evil.test/{BV}',
                          f'https://www.bilibili.com.evil.test/video/{BV}',
                          f'https://user@www.bilibili.com/video/{BV}'):
                await main._handle_chat_command('Alice', 'b站 ' + value)
                self.assertIn('用法', notice.call_args.args[0])
            extract.assert_not_awaited()
            enqueue.assert_not_awaited()
            self.assertFalse(main._bilibili_chat_tasks)

    async def test_friendly_metadata_failures_do_not_enqueue_or_leak_details(self):
        for error in (HTTPException(403, 'private-cookie'), HTTPException(404, 'private-cookie'),
                      HTTPException(502, 'private-cookie'), RuntimeError('private-cookie')):
            with self.subTest(error=error), patch.object(
                    main, '_extract_bilibili_video_info', AsyncMock(side_effect=error)), patch.object(
                    main, '_enqueue_bilibili_song', AsyncMock()) as enqueue, patch.object(
                    main.voice, 'send_notice', AsyncMock()) as notice:
                await main._handle_chat_command('Alice', f'b站 {BV}')
                await self.drain()
                self.assertIn('B站', notice.call_args.args[0])
                self.assertNotIn('private-cookie', notice.call_args.args[0])
                enqueue.assert_not_awaited()
                self.assertIsNone(main._pending_play_request_generation)

    async def test_enqueue_failure_never_reports_success(self):
        for code, expected in ((400, '时长限制'), (409, '替代'), (502, '失败')):
            with self.subTest(code=code), patch.object(
                    main, '_extract_bilibili_video_info', AsyncMock(return_value=META)), patch.object(
                    main, '_enqueue_bilibili_song', AsyncMock(side_effect=HTTPException(code, 'internal'))), patch.object(
                    main.voice, 'send_notice', AsyncMock()) as notice:
                await main._handle_chat_command('Alice', f'b站 {BV}')
                await self.drain()
                self.assertIn(expected, notice.call_args.args[0])
                self.assertNotIn('已开始播放', notice.call_args.args[0])

    async def test_slow_bilibili_request_does_not_block_other_chat_commands(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        async def slow_extract(video_id):
            entered.set()
            await release.wait()
            return META
        with patch.object(main, '_extract_bilibili_video_info', side_effect=slow_extract), patch.object(
                main, '_enqueue_bilibili_song', AsyncMock(return_value=(1, False))), patch.object(
                main.voice, 'send_notice', AsyncMock()) as notice:
            await asyncio.wait_for(main._handle_chat_command('Alice', f'b站 {BV}'), 1)
            await asyncio.wait_for(entered.wait(), 1)
            await asyncio.wait_for(main._handle_chat_command('Bob', '帮助'), 1)
            self.assertIn('Commands', notice.call_args.args[0])
            self.assertEqual(1, len(main._bilibili_chat_tasks))
            release.set()
            await self.drain()
            self.assertFalse(main._bilibili_chat_tasks)

    async def test_pending_requests_are_bounded(self):
        async def slow_extract(video_id):
            await asyncio.Event().wait()
        with patch.object(main, '_extract_bilibili_video_info', side_effect=slow_extract), patch.object(
                main.voice, 'send_notice', AsyncMock()) as notice:
            for _ in range(main._BILIBILI_CHAT_MAX_PENDING + 1):
                await main._handle_chat_command('Alice', f'b站 {BV}')
            self.assertEqual(main._BILIBILI_CHAT_MAX_PENDING, len(main._bilibili_chat_tasks))
            self.assertIn('稍后再试', notice.call_args.args[0])
            # Cancel before leaving the mock context: queued tasks must never
            # start real metadata lookups during async test teardown.
            tasks = list(main._bilibili_chat_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_failed_old_metadata_does_not_clear_newer_pending_request(self):
        old_entered = asyncio.Event()
        new_entered = asyncio.Event()
        release_old = asyncio.Event()
        release_new = asyncio.Event()

        async def extract(video_id):
            if video_id == BV:
                old_entered.set()
                await release_old.wait()
                raise HTTPException(502, 'internal')
            new_entered.set()
            await release_new.wait()
            return META

        with patch.object(main, '_extract_bilibili_video_info', side_effect=extract), patch.object(
                main, '_enqueue_bilibili_song', AsyncMock(return_value=(42, False))), patch.object(
                main.voice, 'send_notice', AsyncMock()):
            await main._handle_chat_command('Alice', f'b站 {BV}')
            old_tasks = set(main._bilibili_chat_tasks)
            try:
                await asyncio.wait_for(old_entered.wait(), 2)
                await main._handle_chat_command('Bob', 'b站 BV1Q541167Qg')
                await asyncio.wait_for(new_entered.wait(), 2)
                newer_generation = main._pending_play_request_generation
                self.assertIsNotNone(newer_generation)
                release_old.set()
                await asyncio.gather(*old_tasks)
                self.assertEqual(newer_generation, main._pending_play_request_generation)
            finally:
                release_old.set()
                release_new.set()
                await self.drain()
        self.assertIsNone(main._pending_play_request_generation)

    async def test_netease_keyword_commands_keep_existing_path(self):
        result = {'result': {'songs': [{'id': 123, 'name': '网易歌曲', 'artists': [{'name': '歌手'}]}]}}
        for command, play_now in [('点歌', False), ('播放', True)]:
            with self.subTest(command=command), patch.object(
                    main.netease, 'search', AsyncMock(return_value=result)), patch.object(
                    main, '_enqueue_netease_song', AsyncMock(return_value=(5, False))) as enqueue, patch.object(
                    main.voice, 'get_status', AsyncMock(return_value=SimpleNamespace(state='STATE_PLAYING'))), patch.object(
                    main.voice, 'send_notice', AsyncMock()), patch.object(
                    main, '_enqueue_bilibili_song', AsyncMock()) as bilibili:
                await main._handle_chat_command('Alice', f'{command} 网易歌曲')
                self.assertEqual('123', enqueue.call_args.kwargs['song_id'])
                self.assertEqual(play_now, enqueue.call_args.kwargs['play_now'])
                bilibili.assert_not_awaited()

    async def test_shutdown_cancels_pending_bilibili_tasks(self):
        task = asyncio.create_task(asyncio.Event().wait())
        main._bilibili_chat_tasks.add(task)
        with patch.object(main, '_levels_task', None), patch.object(main, '_chat_task', None), patch.object(
                main, 'close_all_bilibili_qr_sessions', AsyncMock()), patch.object(
                main.voice, 'close', AsyncMock()):
            await main._shutdown()
        self.assertTrue(task.cancelled())
        self.assertFalse(main._bilibili_chat_tasks)
        self.assertIsNone(main._pending_play_request_generation)
