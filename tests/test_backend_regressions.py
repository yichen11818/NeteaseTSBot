import asyncio
from contextlib import ExitStack
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend import main
from backend.db import Base
from backend.models import QueueItem


class BilibiliAudioCacheTests(unittest.TestCase):
    def test_cache_lookup_removes_expired_audio_and_stale_partial_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            audio_path = cache_dir / "BVEXPIRED.m4a"
            partial_path = cache_dir / "BVFAILED.m4s.part"
            audio_path.write_bytes(b"audio")
            partial_path.write_bytes(b"partial")

            old_timestamp = time.time() - 7200
            os.utime(audio_path, (old_timestamp, old_timestamp))
            os.utime(partial_path, (old_timestamp, old_timestamp))

            with (
                patch.object(main, "BILIBILI_AUDIO_DIR", cache_dir),
                patch.object(main, "BILIBILI_AUDIO_CACHE_TTL_SECONDS", 3600, create=True),
                patch.object(main, "BILIBILI_AUDIO_CACHE_MAX_BYTES", 0, create=True),
                patch.object(main, "BILIBILI_AUDIO_PARTIAL_TTL_SECONDS", 3600, create=True),
            ):
                cached = main._find_cached_bilibili_audio("BVEXPIRED")

            self.assertEqual("", cached)
            self.assertFalse(audio_path.exists())
            self.assertFalse(partial_path.exists())

    def test_cache_lookup_evicts_oldest_audio_when_size_limit_is_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            oldest_path = cache_dir / "BVOLDEST.m4a"
            newest_path = cache_dir / "BVNEWEST.m4a"
            oldest_path.write_bytes(b"a" * 700_000)
            newest_path.write_bytes(b"b" * 700_000)

            now = time.time()
            os.utime(oldest_path, (now - 120, now - 120))
            os.utime(newest_path, (now - 60, now - 60))

            with (
                patch.object(main, "BILIBILI_AUDIO_DIR", cache_dir),
                patch.object(main, "BILIBILI_AUDIO_CACHE_TTL_SECONDS", 0, create=True),
                patch.object(main, "BILIBILI_AUDIO_CACHE_MAX_BYTES", 1_000_000, create=True),
            ):
                main._find_cached_bilibili_audio("BVMISSING")

            self.assertFalse(oldest_path.exists())
            self.assertTrue(newest_path.exists())

    def test_cache_lookup_does_not_evict_the_requested_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            requested_path = cache_dir / "BVREQUESTED.m4a"
            other_path = cache_dir / "BVOTHER.m4a"
            requested_path.write_bytes(b"a" * 700_000)
            other_path.write_bytes(b"b" * 700_000)

            now = time.time()
            os.utime(requested_path, (now - 120, now - 120))
            os.utime(other_path, (now - 60, now - 60))

            with (
                patch.object(main, "BILIBILI_AUDIO_DIR", cache_dir),
                patch.object(main, "BILIBILI_AUDIO_CACHE_TTL_SECONDS", 0),
                patch.object(main, "BILIBILI_AUDIO_CACHE_MAX_BYTES", 1_000_000),
            ):
                cached = main._find_cached_bilibili_audio("BVREQUESTED")

            self.assertEqual(str(requested_path.resolve()), cached)
            self.assertTrue(requested_path.exists())
            self.assertFalse(other_path.exists())


class AdminCookieStatusTests(unittest.TestCase):
    def test_encrypted_empty_cookie_is_not_reported_as_configured(self) -> None:
        session = unittest.mock.Mock()
        session.get.return_value = unittest.mock.Mock(value="encrypted-empty-cookie")

        with (
            patch.object(main, "_require_admin_token"),
            patch.object(main, "decrypt_text", return_value=""),
        ):
            result = main.admin_status(object(), session)

        self.assertFalse(result["admin_cookie_set"])

    def test_encrypted_empty_cookie_is_treated_as_not_configured(self) -> None:
        session = unittest.mock.Mock()
        session.get.return_value = unittest.mock.Mock(value="encrypted-empty-cookie")

        with patch.object(main, "decrypt_text", return_value=""):
            with self.assertRaises(HTTPException) as raised:
                main._get_admin_cookie(session)

        self.assertEqual(400, raised.exception.status_code)

    def test_metadata_only_cookie_is_treated_as_not_configured(self) -> None:
        session = unittest.mock.Mock()
        session.get.return_value = unittest.mock.Mock(value="encrypted-metadata-cookie")
        metadata_cookie = "NMTID=device-id; __csrf=csrf-token"

        with (
            patch.object(main, "_require_admin_token"),
            patch.object(main, "decrypt_text", return_value=metadata_cookie),
        ):
            status = main.admin_status(object(), session)
            with self.assertRaises(HTTPException) as raised:
                main._get_admin_cookie(session)

        self.assertFalse(status["admin_cookie_set"])
        self.assertEqual(400, raised.exception.status_code)

    def test_metadata_only_cookie_is_not_saved_manually(self) -> None:
        session = unittest.mock.Mock()
        metadata_cookie = "NMTID=device-id; __csrf=csrf-token"

        with (
            patch.object(main, "_require_admin_token"),
            patch.object(main, "_set_secret") as set_secret,
            self.assertRaises(HTTPException) as raised,
        ):
            main.admin_set_cookie(main.AdminCookieSetRequest(cookie=metadata_cookie), object(), session)

        self.assertEqual(400, raised.exception.status_code)
        set_secret.assert_not_called()


class NeteaseQrCookieTests(unittest.IsolatedAsyncioTestCase):
    async def test_qr_success_without_core_auth_cookie_is_rejected(self) -> None:
        qr_response = {
            "code": 803,
            "cookie": "NMTID=device-id; __csrf=csrf-token; MUSIC_SNS=",
        }

        with (
            patch.object(main, "_require_admin_token"),
            patch.object(main, "_set_secret") as set_secret,
            patch.object(main.netease, "qr_check", AsyncMock(return_value=qr_response)),
        ):
            result = await main.admin_qr_check("qr-key", object(), object())

        self.assertEqual(803, result["code"])
        self.assertFalse(result["admin_cookie_set"])
        set_secret.assert_not_called()

    async def test_qr_cookie_keeps_valid_auth_value_when_later_duplicate_is_empty(self) -> None:
        qr_response = {
            "code": 803,
            "cookie": (
                "MUSIC_U=valid-token; Path=/;;"
                "MUSIC_U=; Max-Age=0; Path=/; __csrf=csrf-token"
            ),
        }

        with (
            patch.object(main, "_require_admin_token"),
            patch.object(main, "_set_secret") as set_secret,
            patch.object(main.netease, "qr_check", AsyncMock(return_value=qr_response)),
        ):
            result = await main.admin_qr_check("qr-key", object(), object())

        self.assertTrue(result["admin_cookie_set"])
        set_secret.assert_called_once_with(
            unittest.mock.ANY,
            "netease_cookie",
            "MUSIC_U=valid-token; __csrf=csrf-token",
        )


class TsChatCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        main._ts_playlist_results.clear()

    async def test_playlist_search_then_select_enqueues_netease_tracks(self) -> None:
        search_result = {
            "result": {
                "playlists": [
                    {
                        "id": 123,
                        "name": "测试歌单",
                        "creator": {"nickname": "创建者"},
                        "trackCount": 2,
                    }
                ]
            }
        }
        tracks = [
            {"id": 1, "name": "歌曲一", "ar": [{"name": "歌手一"}], "al": {"name": "专辑一"}},
            {"id": 2, "name": "歌曲二", "ar": [{"name": "歌手二"}], "al": {"name": "专辑二"}},
        ]

        with (
            patch.object(main.netease, "search", AsyncMock(return_value=search_result)) as search,
            patch.object(main.netease, "playlist_detail", AsyncMock(return_value={"playlist": {"name": "测试歌单"}})),
            patch.object(main, "_load_netease_playlist_tracks", AsyncMock(return_value=("测试歌单", tracks))),
            patch.object(main, "_enqueue_netease_song", AsyncMock(return_value=(1, False))) as enqueue,
            patch.object(main, "_get_admin_cookie_or_none", return_value="cookie"),
            patch.object(main.voice, "get_status", AsyncMock(return_value=SimpleNamespace(state="STATE_PLAYING"))),
            patch.object(main.voice, "send_notice", AsyncMock()) as notice,
        ):
            await main._handle_chat_command("Alice", "playlist 测试", invoker_unique_id="alice-uid")
            await main._handle_chat_command("Alice", "select 1", invoker_unique_id="alice-uid")

        search.assert_awaited_once_with(keywords="测试", limit=5, type_=1000)
        self.assertEqual(2, enqueue.await_count)
        self.assertEqual("1", enqueue.await_args_list[0].kwargs["song_id"])
        self.assertEqual("2", enqueue.await_args_list[1].kwargs["song_id"])
        self.assertIn("使用 select <编号>", notice.await_args_list[0].args[0])
        self.assertIn("已从歌单《测试歌单》加入 2 首歌曲", notice.await_args_list[1].args[0])

    async def test_play_without_argument_plays_first_queue_item(self) -> None:
        row = SimpleNamespace(id=42, title="队首歌曲", artist="歌手")
        session = unittest.mock.Mock()
        session.execute.return_value.scalars.return_value.first.return_value = row

        with (
            patch.object(main, "new_session", return_value=session),
            patch.object(main, "_play_queue_item_internal", AsyncMock(return_value=True)) as play_item,
            patch.object(main.voice, "send_notice", AsyncMock()) as notice,
        ):
            await main._handle_chat_command("Bob", "play")

        session.close.assert_called_once_with()
        play_item.assert_awaited_once_with(42, requested_by="Bob")
        self.assertIn("已播放队列第一首: 队首歌曲 - 歌手", notice.await_args.args[0])

    async def test_random_and_order_commands_switch_shuffle_mode(self) -> None:
        with (
            patch.object(main, "_set_shuffle_enabled", AsyncMock(return_value={"ok": True})) as shuffle,
            patch.object(main.voice, "get_status", AsyncMock(return_value=SimpleNamespace(state="STATE_PLAYING"))),
            patch.object(main.voice, "send_notice", AsyncMock()) as notice,
        ):
            await main._handle_chat_command("Carol", "随机播放")
            await main._handle_chat_command("Carol", "顺序播放")

        self.assertEqual([True, False], [call.args[0] for call in shuffle.await_args_list])
        self.assertIn("已切换为随机播放", notice.await_args_list[0].args[0])
        self.assertIn("已切换为顺序播放", notice.await_args_list[1].args[0])

    async def test_clear_command_clears_queue_and_playback_state(self) -> None:
        count_result = unittest.mock.Mock()
        count_result.scalar.return_value = 3
        session = unittest.mock.Mock()
        session.execute.side_effect = [count_result, unittest.mock.Mock()]

        with (
            patch.object(main, "new_session", return_value=session),
            patch.object(main, "_shuffle_queue", [1, 2, 3]),
            patch.object(main, "_current_shuffle_index", 1),
            patch.object(main, "_invalidate_play_requests", AsyncMock()) as invalidate,
            patch.object(main, "_set_now_playing_queue_item", AsyncMock()) as clear_now_playing,
            patch.object(main, "_schedule_ts_description_update"),
            patch.object(main.voice, "stop", AsyncMock()) as stop,
            patch.object(main.voice, "send_notice", AsyncMock()) as notice,
        ):
            await main._handle_chat_command("Dave", "清空")

            self.assertEqual([], main._shuffle_queue)
            self.assertEqual(-1, main._current_shuffle_index)

        session.commit.assert_called_once_with()
        session.close.assert_called_once_with()
        invalidate.assert_awaited_once_with()
        clear_now_playing.assert_awaited_once_with(None)
        stop.assert_awaited_once_with()
        self.assertIn("已清空播放队列（3 首）", notice.await_args.args[0])

    def test_playlist_results_are_isolated_by_unique_id_and_expire(self) -> None:
        alice_key = main._ts_playlist_result_key(invoker_unique_id="alice-uid", invoker_name="SameName")
        bob_key = main._ts_playlist_result_key(invoker_unique_id="bob-uid", invoker_name="SameName")
        playlists = [{"id": "123", "name": "测试", "creator": "", "track_count": "1"}]

        with patch.object(main.time, "monotonic", return_value=100.0):
            main._remember_ts_playlist_results(alice_key, playlists)

        with patch.object(main.time, "monotonic", return_value=101.0):
            self.assertEqual(playlists, main._get_ts_playlist_results(alice_key))
            self.assertEqual([], main._get_ts_playlist_results(bob_key))

        with patch.object(main.time, "monotonic", return_value=100.0 + main._TS_PLAYLIST_RESULTS_TTL_S):
            self.assertEqual([], main._get_ts_playlist_results(alice_key))

    def test_netease_search_metadata_accepts_artists_field(self) -> None:
        raw = {
            "result": {
                "songs": [
                    {
                        "id": 123,
                        "name": "歌曲",
                        "ar": [],
                        "artists": [{"name": "歌手一"}, {"name": "歌手二"}],
                    }
                ]
            }
        }

        self.assertEqual(("123", "歌曲", "歌手一, 歌手二"), main._extract_song_meta_from_search_first(raw))


class PlaybackCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeat_one_replays_finished_item_without_deleting_it(self) -> None:
        with (
            patch.object(main, "_repeat_mode", "one"),
            patch.object(main, "_take_now_playing_if_match", AsyncMock(return_value=7)),
            patch.object(main, "_play_queue_item_internal", AsyncMock(return_value=True)) as replay,
            patch.object(main, "_delete_queue_item", AsyncMock()) as delete_item,
            patch.object(main, "_auto_play_next_from_queue", AsyncMock()) as play_next,
        ):
            await main._handle_playback_finished("source")

        replay.assert_awaited_once_with(7, requested_by="auto")
        delete_item.assert_not_awaited()
        play_next.assert_not_awaited()

    async def test_normal_completion_deletes_item_and_plays_next(self) -> None:
        with (
            patch.object(main, "_repeat_mode", "none"),
            patch.object(main, "_take_now_playing_if_match", AsyncMock(return_value=8)),
            patch.object(main, "_play_queue_item_internal", AsyncMock()) as replay,
            patch.object(main, "_delete_queue_item", AsyncMock()) as delete_item,
            patch.object(main, "_auto_play_next_from_queue", AsyncMock()) as play_next,
        ):
            await main._handle_playback_finished("source")

        replay.assert_not_awaited()
        delete_item.assert_awaited_once_with(8)
        play_next.assert_awaited_once_with(start_after_id=8)


class PlaybackQueueCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def _assert_completion_sequence(
        self, *, repeat_mode: str, play_order: list[int], shuffle: bool = False
    ) -> None:
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        queue_ids = sorted(play_order)
        with sessions() as session:
            session.add_all(
                QueueItem(
                    id=item_id,
                    track_id=f"test:{item_id}",
                    title=f"Track {item_id}",
                    source_url=f"https://example.com/{item_id}.mp3",
                )
                for item_id in queue_ids
            )
            session.commit()

        expected_plays = play_order * 2 + play_order[:1] if repeat_mode == "all" else play_order
        with (
            patch.object(main, "new_session", side_effect=sessions),
            patch.multiple(
                main,
                _repeat_mode=repeat_mode,
                _shuffle_enabled=shuffle,
                _shuffle_queue=play_order.copy() if shuffle else [],
                _current_shuffle_index=-1,
                _current_queue_item_id=None,
                _pending_queue_item_id=None,
                _pending_play_request_generation=None,
                _current_source_url="",
                _playback_lock=asyncio.Lock(),
                _play_request_generation=0,
                _play_started_at=None,
                _paused_at=None,
                _paused_total_s=0.0,
                _current_duration_ms=0,
                _current_artist="",
                _current_album="",
                _current_artwork_url="",
            ),
            patch.object(main, "_schedule_ts_description_update"),
            patch.object(main.voice, "play", AsyncMock()) as play,
        ):
            await main._auto_play_next_from_queue()
            for index, item_id in enumerate(expected_plays):
                self.assertEqual(item_id, main._current_queue_item_id)
                self.assertEqual(index + 1, play.await_count)
                with sessions() as session:
                    remaining_ids = session.execute(
                        select(QueueItem.id).order_by(QueueItem.id.asc())
                    ).scalars().all()
                expected_queue = queue_ids if repeat_mode == "all" else sorted(play_order[index:])
                self.assertEqual(expected_queue, remaining_ids)
                if index < len(expected_plays) - 1 or repeat_mode == "none":
                    await main._handle_playback_finished(main._current_source_url)

            if repeat_mode == "none":
                self.assertIsNone(main._current_queue_item_id)
                self.assertEqual("", main._current_source_url)
                self.assertEqual(len(play_order), play.await_count)
                with sessions() as session:
                    self.assertEqual([], session.execute(select(QueueItem.id)).scalars().all())

    async def test_repeat_all_preserves_queue_and_wraps_in_order_for_two_rounds(self) -> None:
        await self._assert_completion_sequence(repeat_mode="all", play_order=[10, 20, 30])

    async def test_repeat_all_preserves_shuffled_queue_for_two_rounds(self) -> None:
        await self._assert_completion_sequence(repeat_mode="all", play_order=[30, 10, 20], shuffle=True)

    async def test_repeat_all_with_one_item_keeps_replaying(self) -> None:
        await self._assert_completion_sequence(repeat_mode="all", play_order=[10])

    async def test_no_repeat_consumes_queue_and_stops(self) -> None:
        await self._assert_completion_sequence(repeat_mode="none", play_order=[10, 20, 30])

    async def test_no_repeat_consumes_shuffled_queue_and_stops(self) -> None:
        await self._assert_completion_sequence(repeat_mode="none", play_order=[30, 10, 20], shuffle=True)


class PlaybackControlsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine)
        with self.sessions() as session:
            session.add_all(
                QueueItem(id=i, track_id=f"test:{i}", title=f"Track {i}", source_url=f"source:{i}")
                for i in [10, 20, 30]
            )
            session.commit()

        patches = ExitStack()
        self.addCleanup(patches.close)
        patches.enter_context(patch.object(main, "new_session", side_effect=self.sessions))
        patches.enter_context(patch.object(main, "_schedule_ts_description_update"))
        patches.enter_context(patch.multiple(
            main,
            _repeat_mode="none", _shuffle_enabled=False, _shuffle_queue=[], _current_shuffle_index=-1,
            _current_queue_item_id=None, _pending_queue_item_id=None, _current_source_url="",
            _pending_play_request_generation=None,
            _playback_lock=asyncio.Lock(), _play_request_generation=0,
            _play_started_at=None, _paused_at=None, _paused_total_s=0.0,
            _current_duration_ms=0, _current_artist="", _current_album="", _current_artwork_url="",
        ))
        self.play = patches.enter_context(patch.object(main.voice, "play", AsyncMock()))
        self.skip = patches.enter_context(patch.object(main.voice, "skip", AsyncMock()))
        self.stop = patches.enter_context(patch.object(main.voice, "stop", AsyncMock()))
        patches.enter_context(patch.object(main.voice, "send_notice", AsyncMock()))

    def _queue_ids(self) -> list[int]:
        with self.sessions() as session:
            return list(session.execute(select(QueueItem.id).order_by(QueueItem.id.asc())).scalars())

    def _shuffle(self, order: list[int]) -> None:
        main._shuffle_enabled = True
        main._shuffle_queue = order.copy()
        main._current_shuffle_index = -1

    def _make_netease_item(self, item_id: int) -> None:
        with self.sessions() as session:
            session.get(QueueItem, item_id).track_id = f"netease:{item_id}"
            session.commit()

    async def test_next_and_previous_preserve_queue_in_repeat_modes(self) -> None:
        for mode in ["one", "all"]:
            with self.subTest(mode=mode):
                main._repeat_mode = mode
                await main._play_queue_item_internal(10, requested_by="test")
                await main.voice_next()
                self.assertEqual(20, main._current_queue_item_id)
                self.assertEqual([10, 20, 30], self._queue_ids())
                await main._handle_playback_finished("source:20")
                self.assertEqual(20 if mode == "one" else 30, main._current_queue_item_id)
                await main.voice_previous()
                self.assertEqual(10 if mode == "one" else 20, main._current_queue_item_id)

    async def test_shuffled_next_wraps_and_preserves_repeat_all_queue(self) -> None:
        self._shuffle([30, 10, 20])
        main._repeat_mode = "all"
        await main._play_queue_item_internal(20, requested_by="test")
        await main.voice_next()
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual([10, 20, 30], self._queue_ids())
        await main.voice_previous()
        self.assertEqual(20, main._current_queue_item_id)

    async def test_shuffle_consumes_remaining_tracks_when_started_at_last_item(self) -> None:
        self._shuffle([30, 10, 20])
        await main._play_queue_item_internal(20, requested_by="test")
        for expected_id in [30, 10]:
            await main._handle_playback_finished(main._current_source_url)
            self.assertEqual(expected_id, main._current_queue_item_id)
        await main._handle_playback_finished(main._current_source_url)
        self.assertIsNone(main._current_queue_item_id)
        self.assertEqual([], self._queue_ids())

    async def test_shuffled_completion_uses_actual_finished_item_as_cursor(self) -> None:
        self._shuffle([30, 10, 20])
        main._repeat_mode = "all"
        main._current_shuffle_index = 0
        await main._set_now_playing_queue_item(10, "source:10")
        await main._handle_playback_finished("source:10")
        self.assertEqual(20, main._current_queue_item_id)

    async def test_shuffled_next_includes_tracks_added_after_shuffle_was_enabled(self) -> None:
        self._shuffle([10, 20])
        main._repeat_mode = "all"
        await main._play_queue_item_internal(20, requested_by="test")
        await main.voice_next()
        self.assertEqual(30, main._current_queue_item_id)

    async def test_repeat_one_moves_on_when_current_item_was_deleted(self) -> None:
        main._repeat_mode = "one"
        await main._play_queue_item_internal(10, requested_by="test")
        with self.sessions() as session:
            main.delete_queue_item(10, session=session)
        await main._handle_playback_finished("source:10")
        self.assertEqual(20, main._current_queue_item_id)

    async def test_skip_deletes_even_in_repeat_all_and_advances_from_removed_item(self) -> None:
        main._repeat_mode = "all"
        await main._play_queue_item_internal(20, requested_by="test")
        await main.voice_skip()
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual([10, 30], self._queue_ids())

    async def test_auto_play_skips_unavailable_track_without_stalling(self) -> None:
        self._make_netease_item(10)
        with (
            patch.object(main, "_get_admin_cookie", return_value="test-cookie"),
            patch.object(main, "_resolve_netease_playback_payload", AsyncMock(
                side_effect=HTTPException(status_code=403, detail="unavailable")
            )),
        ):
            await main._auto_play_next_from_queue()
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([20, 30], self._queue_ids())

    async def test_voice_rpc_failure_clears_current_state_and_keeps_queue(self) -> None:
        self.play.side_effect = RuntimeError("voice offline")
        with self.assertRaises(RuntimeError):
            await main._play_queue_item_internal(10, requested_by="test")
        self.assertIsNone(main._current_queue_item_id)
        self.assertIsNone(main._pending_queue_item_id)
        self.assertEqual("", main._current_source_url)
        self.assertEqual([10, 20, 30], self._queue_ids())

    async def test_finished_old_track_does_not_supersede_pending_manual_play(self) -> None:
        await main._play_queue_item_internal(10, requested_by="test")
        self._make_netease_item(20)
        resolving = asyncio.Event()
        release = asyncio.Event()

        async def resolve(**kwargs):
            resolving.set()
            await release.wait()
            return ("source:20", False, "", 1000, "artist", "album", "artwork")

        with (
            patch.object(main, "_get_admin_cookie", return_value="test-cookie"),
            patch.object(main, "_resolve_netease_playback_payload", side_effect=resolve),
        ):
            task = asyncio.create_task(main._play_queue_item_internal(20, requested_by="manual"))
            try:
                await asyncio.wait_for(resolving.wait(), timeout=2)
                completion = asyncio.create_task(main._handle_playback_finished("source:10"))
                await asyncio.sleep(0)
            finally:
                release.set()
                await task
            await completion
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual("manual", self.play.await_args.kwargs["requested_by"])

    async def test_old_request_cleanup_does_not_clear_newer_request_for_same_item(self) -> None:
        old_generation = await main._begin_play_request(10)
        await main._begin_play_request(10)
        cleared = await main._clear_pending_play_request(request_generation=old_generation)
        self.assertFalse(cleared)
        self.assertEqual(10, main._pending_queue_item_id)

    async def test_failed_pause_does_not_change_backend_progress_state(self) -> None:
        await main._play_queue_item_internal(10, requested_by="test")
        with patch.object(main.voice, "pause", AsyncMock(side_effect=RuntimeError("offline"))):
            with self.assertRaises(RuntimeError):
                await main.voice_pause()
        self.assertIsNone(main._paused_at)

    async def test_failed_resume_keeps_backend_paused(self) -> None:
        await main._play_queue_item_internal(10, requested_by="test")
        await main._mark_playback_paused()
        paused_at = main._paused_at
        with (
            patch.object(main.voice, "get_status", AsyncMock(return_value=SimpleNamespace(state="STATE_PAUSED"))),
            patch.object(main.voice, "resume", AsyncMock(side_effect=RuntimeError("offline"))),
        ):
            with self.assertRaises(RuntimeError):
                await main.voice_play()
        self.assertEqual(paused_at, main._paused_at)

    async def test_stop_during_resolution_prevents_late_play(self) -> None:
        self._make_netease_item(10)
        resolving = asyncio.Event()
        release = asyncio.Event()

        async def resolve(**kwargs):
            resolving.set()
            await release.wait()
            return ("source:10", False, "", 1000, "artist", "album", "artwork")

        with (
            patch.object(main, "_get_admin_cookie", return_value="test-cookie"),
            patch.object(main, "_resolve_netease_playback_payload", side_effect=resolve),
        ):
            task = asyncio.create_task(main._play_queue_item_internal(10, requested_by="test"))
            try:
                await asyncio.wait_for(resolving.wait(), timeout=2)
                await main._handle_chat_command("user", "stop")
            finally:
                release.set()
                await task
        self.play.assert_not_awaited()
        self.assertIsNone(main._current_queue_item_id)
        self.assertIsNone(main._pending_queue_item_id)
        self.assertEqual([10, 20, 30], self._queue_ids())

    def _source_patches(self) -> ExitStack:
        patches = ExitStack()
        patches.enter_context(patch.object(main, "_get_admin_cookie", return_value="test-cookie"))
        patches.enter_context(patch.object(main, "_get_admin_qqmusic_cookie", return_value="test-cookie"))
        patches.enter_context(patch.object(main.qqmusic, "set_cookie"))
        patches.enter_context(patch.object(main, "_resolve_netease_playback_payload", AsyncMock(
            return_value=("source:new", False, "", 1000, "artist", "album", "artwork")
        )))
        patches.enter_context(patch.object(main.qqmusic, "get_music_url_simple", AsyncMock(return_value="source:new")))
        patches.enter_context(patch.object(main, "_hydrate_bilibili_track_metadata", AsyncMock(
            return_value=(1000, "artist", "album", "artwork")
        )))
        patches.enter_context(patch.object(main, "_resolve_bilibili_playback_payload", AsyncMock(
            return_value=("source:new", 1000, "artist", "album", "artwork")
        )))
        return patches

    async def _assert_bilibili_chat_metadata_superseded(self, *, stop: bool) -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def extract(video_id):
            entered.set()
            await release.wait()
            return dict(title="old chat request", artist="artist", album="album",
                        duration_ms=1000, artwork_url="artwork")

        with self._source_patches(), patch.object(main, "_extract_bilibili_video_info", side_effect=extract):
            await main._handle_chat_command("user", "b站 BV1xx411c7mD")
            tasks = list(main._bilibili_chat_tasks)
            try:
                await asyncio.wait_for(entered.wait(), timeout=2)
                if stop:
                    await main._handle_chat_command("user", "stop")
                else:
                    await main._play_queue_item_internal(20, requested_by="newer")
            finally:
                release.set()
                await asyncio.gather(*tasks)
                await asyncio.sleep(0)

        if stop:
            self.play.assert_not_awaited()
            self.assertIsNone(main._current_queue_item_id)
        else:
            self.play.assert_awaited_once()
            self.assertEqual("source:20", self.play.call_args.kwargs["source_url"])
            self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([10, 20, 30], self._queue_ids())
        self.assertIsNone(main._pending_play_request_generation)
        self.assertIn("替代", main.voice.send_notice.call_args.args[0])

    async def test_bilibili_chat_stop_during_metadata_prevents_late_play(self) -> None:
        await self._assert_bilibili_chat_metadata_superseded(stop=True)

    async def test_bilibili_chat_metadata_cannot_override_newer_play(self) -> None:
        await self._assert_bilibili_chat_metadata_superseded(stop=False)

    async def test_newer_bilibili_chat_request_wins_when_metadata_finishes_first(self) -> None:
        entered = asyncio.Event()
        release = asyncio.Event()
        older = "BV1xx411c7mD"
        newer = "BV1Q541167Qg"

        async def extract(video_id):
            if video_id == older:
                entered.set()
                await release.wait()
            return dict(title=video_id, artist="artist", album="album",
                        duration_ms=1000, artwork_url="artwork")

        with self._source_patches(), patch.object(main, "_extract_bilibili_video_info", side_effect=extract):
            await main._handle_chat_command("user", f"b站 {older}")
            old_tasks = set(main._bilibili_chat_tasks)
            try:
                await asyncio.wait_for(entered.wait(), timeout=2)
                await main._handle_chat_command("user", f"b站 {newer}")
                await asyncio.gather(*(main._bilibili_chat_tasks - old_tasks))
            finally:
                release.set()
                await asyncio.gather(*old_tasks)
                await asyncio.sleep(0)
        self.play.assert_awaited_once()
        self.assertEqual(newer, self.play.call_args.kwargs["title"])
        self.assertEqual(4, len(self._queue_ids()))
        self.assertIsNone(main._pending_play_request_generation)

    async def _enqueue_source(self, source: str) -> tuple[int, bool]:
        common = dict(title="new", artist="artist", play_now=True, requested_by="manual")
        if source == "netease":
            return await main._enqueue_netease_song(song_id="new", **common)
        if source == "qqmusic":
            return await main._enqueue_qqmusic_song(song_mid="new", **common)
        return await main._enqueue_bilibili_song(video_id="BVNEW", **common)

    async def test_all_sources_clear_pending_state_after_immediate_play(self) -> None:
        with self._source_patches():
            for source in ["netease", "qqmusic", "bilibili"]:
                with self.subTest(source=source):
                    item_id, _ = await self._enqueue_source(source)
                    self.assertEqual(item_id, main._current_queue_item_id)
                    self.assertIsNone(main._pending_play_request_generation)
                    self.assertIsNone(main._pending_queue_item_id)

    async def test_all_sources_honor_stop_while_immediate_play_is_loading(self) -> None:
        with self._source_patches():
            for source in ["netease", "qqmusic", "bilibili"]:
                with self.subTest(source=source):
                    resolving = asyncio.Event()
                    release = asyncio.Event()
                    resolver = {
                        "netease": main._resolve_netease_playback_payload,
                        "qqmusic": main.qqmusic.get_music_url_simple,
                        "bilibili": main._resolve_bilibili_playback_payload,
                    }[source]
                    payload = resolver.return_value

                    async def resolve(*args, **kwargs):
                        resolving.set()
                        await release.wait()
                        return payload

                    resolver.side_effect = resolve
                    task = asyncio.create_task(self._enqueue_source(source))
                    try:
                        await asyncio.wait_for(resolving.wait(), timeout=2)
                        self.assertIsNotNone(main._pending_play_request_generation)
                        await main._handle_chat_command("user", "stop")
                    finally:
                        release.set()
                    with self.assertRaises(HTTPException) as raised:
                        await task
                    self.assertEqual(409, raised.exception.status_code)
                    resolver.side_effect = None
                    self.assertIsNone(main._pending_play_request_generation)
        self.play.assert_not_awaited()
        self.assertIsNone(main._current_queue_item_id)
        self.assertEqual([10, 20, 30], self._queue_ids())

    async def test_repeat_one_also_repeats_in_shuffle_mode(self) -> None:
        self._shuffle([30, 10, 20])
        main._repeat_mode = "one"
        await main._play_queue_item_internal(10, requested_by="test")
        for _ in range(3):
            await main._handle_playback_finished("source:10")
            self.assertEqual(10, main._current_queue_item_id)
            self.assertEqual([10, 20, 30], self._queue_ids())

    async def test_repeat_one_skips_song_that_becomes_unavailable(self) -> None:
        main._repeat_mode = "one"
        await main._play_queue_item_internal(10, requested_by="test")
        self._make_netease_item(10)
        with self._source_patches():
            main._resolve_netease_playback_payload.side_effect = HTTPException(status_code=404, detail="removed")
            await main._handle_playback_finished("source:10")
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual([20, 30], self._queue_ids())

    async def test_auto_play_stops_when_entire_repeat_all_queue_is_unavailable(self) -> None:
        main._repeat_mode = "all"
        for item_id in [10, 20, 30]:
            self._make_netease_item(item_id)
        with self._source_patches():
            main._resolve_netease_playback_payload.side_effect = HTTPException(status_code=403, detail="unavailable")
            await main._auto_play_next_from_queue()
        self.assertEqual([], self._queue_ids())
        self.assertIsNone(main._current_queue_item_id)
        self.play.assert_not_awaited()

    async def test_transient_resolution_error_keeps_queue_for_retry(self) -> None:
        self._make_netease_item(10)
        with self._source_patches():
            main._resolve_netease_playback_payload.side_effect = HTTPException(status_code=502, detail="temporary")
            with self.assertRaises(HTTPException):
                await main._auto_play_next_from_queue()
        self.assertEqual([10, 20, 30], self._queue_ids())
        self.assertIsNone(main._pending_play_request_generation)

    async def test_qqmusic_repeat_refreshes_url_and_preserves_quality(self) -> None:
        main._repeat_mode = "one"
        with self.sessions() as session:
            item = session.get(QueueItem, 10)
            item.track_id = "qqmusic:song"
            item.source_url = "https://example.com/M500song.mp3?expired=1"
            session.commit()
        with self._source_patches():
            urls = main.qqmusic.get_music_url_simple
            urls.side_effect = ["https://example.com/M500song.mp3?fresh=1", "https://example.com/M500song.mp3?fresh=2"]
            await main._play_queue_item_internal(10, requested_by="test")
            await main._handle_playback_finished(main._current_source_url)
            self.assertEqual(2, urls.await_count)
            self.assertEqual("128", urls.await_args.args[1])
        self.assertEqual("https://example.com/M500song.mp3?fresh=2", self.play.await_args.kwargs["source_url"])

    async def test_play_restarts_when_voice_retains_stale_playing_status(self) -> None:
        with patch.object(main.voice, "get_status", AsyncMock(return_value=SimpleNamespace(state="STATE_PLAYING"))):
            await main.voice_play()
        self.assertEqual(10, main._current_queue_item_id)

    async def test_repeat_all_previous_wraps_from_first_to_last(self) -> None:
        main._repeat_mode = "all"
        await main._play_queue_item_internal(10, requested_by="test")
        await main.voice_previous()
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual([10, 20, 30], self._queue_ids())

    async def test_switching_to_no_repeat_continues_after_current_item(self) -> None:
        main._repeat_mode = "all"
        await main._play_queue_item_internal(20, requested_by="test")
        await main.voice_repeat(main.RepeatRequest(mode="none"))
        await main._handle_playback_finished("source:20")
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual([10, 30], self._queue_ids())

    async def test_stale_finished_event_does_not_advance_new_track(self) -> None:
        await main._play_queue_item_internal(20, requested_by="test")
        await main._handle_playback_finished("source:10")
        self.assertEqual(20, main._current_queue_item_id)
        self.assertEqual(1, self.play.await_count)

    async def test_playback_error_advances_from_failed_item_in_repeat_one(self) -> None:
        main._repeat_mode = "one"
        await main._play_queue_item_internal(20, requested_by="test")
        await main._handle_playback_error("source:20")
        self.assertEqual(30, main._current_queue_item_id)
        self.assertEqual([10, 30], self._queue_ids())

    async def test_pending_request_prevents_duplicate_play_from_web(self) -> None:
        await main._begin_play_request()
        with patch.object(main.voice, "get_status", AsyncMock(return_value=SimpleNamespace(state="STATE_IDLE"))):
            result = await main.voice_play()
        self.assertEqual("pending", result["action"])
        self.play.assert_not_awaited()

    async def test_stop_during_error_notice_prevents_automatic_restart(self) -> None:
        await main._play_queue_item_internal(10, requested_by="test")

        async def stop_during_notice(*args, **kwargs):
            await main._invalidate_play_requests()
            await main._set_now_playing_queue_item(None)

        with patch.object(main.voice, "send_notice", AsyncMock(side_effect=stop_during_notice)):
            await main._handle_playback_error("source:10")
        self.assertIsNone(main._current_queue_item_id)
        self.assertEqual(1, self.play.await_count)

    async def test_stop_during_next_prevents_late_automatic_play(self) -> None:
        await main._play_queue_item_internal(10, requested_by="test")
        self.skip.side_effect = main._invalidate_play_requests
        result = await main.voice_next()
        self.assertEqual("superseded", result["action"])
        self.assertIsNone(main._current_queue_item_id)
        self.assertEqual(1, self.play.await_count)

    async def test_idle_voice_retries_current_track_in_repeat_one(self) -> None:
        main._repeat_mode = "one"
        await main._play_queue_item_internal(20, requested_by="test")
        with patch.object(main.voice, "get_status", AsyncMock(return_value=SimpleNamespace(state="STATE_IDLE"))):
            await main.voice_play()
        self.assertEqual(20, main._current_queue_item_id)

    async def test_shuffled_previous_selects_predecessor_of_deleted_current_item(self) -> None:
        self._shuffle([30, 10, 20])
        await main._play_queue_item_internal(20, requested_by="test")
        with self.sessions() as session:
            main.delete_queue_item(20, session=session)
        await main.voice_previous()
        self.assertEqual(10, main._current_queue_item_id)


class VoiceStatusFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_voice_service_returns_offline_status(self) -> None:
        with (
            patch.object(main.voice, "get_status", AsyncMock(side_effect=RuntimeError("offline"))),
            patch.object(main, "_current_queue_item_id", None),
        ):
            result = await main.voice_status()

        self.assertFalse(result["voice_connected"])
        self.assertEqual("idle", result["state"])
        self.assertEqual("", result["now_playing_title"])


if __name__ == "__main__":
    unittest.main()
