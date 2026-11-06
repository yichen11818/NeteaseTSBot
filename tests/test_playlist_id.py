from contextlib import ExitStack
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend import main
from backend.db import Base
from backend.models import QueueItem


class PlaylistIdTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine)
        patches = ExitStack()
        self.addCleanup(patches.close)
        patches.enter_context(patch.object(main, "new_session", side_effect=self.sessions))
        patches.enter_context(patch.object(main, "_schedule_ts_description_update"))
        patches.enter_context(patch.object(main, "_ts_playlist_results", {}))
        patches.enter_context(patch.object(main, "_get_admin_cookie_or_none", return_value="test-cookie"))
        self.search = patches.enter_context(patch.object(main.netease, "search", AsyncMock(return_value={"result": {"playlists": []}})))
        self.detail = patches.enter_context(patch.object(main.netease, "playlist_detail", AsyncMock(return_value={
            "playlist": {"name": "By ID", "tracks": [
                {"id": 11, "name": "First", "ar": [{"name": "Artist"}], "al": {"name": "Album"}},
                {"id": 22, "name": "Second", "ar": [{"name": "Artist"}], "al": {"name": "Album"}},
            ]}
        })))
        patches.enter_context(patch.object(main.voice, "get_status", AsyncMock(return_value=SimpleNamespace(state="STATE_PLAYING"))))
        self.notice = patches.enter_context(patch.object(main.voice, "send_notice", AsyncMock()))

    def queued(self):
        with self.sessions() as session:
            return [(row.track_id, row.title) for row in session.execute(select(QueueItem).order_by(QueueItem.id)).scalars()]

    async def test_direct_id_enqueues_without_prior_search(self):
        await main._handle_chat_command("Alice", "playlist id:123456789", invoker_unique_id="alice")
        self.assertEqual([("netease:11", "First"), ("netease:22", "Second")], self.queued())
        self.detail.assert_awaited_once_with(playlist_id="123456789", cookie="test-cookie")
        self.search.assert_not_awaited()
        self.assertIn("加入 2 首歌曲", self.notice.await_args.args[0])

    async def test_chinese_alias_accepts_case_insensitive_id_prefix(self):
        await main._handle_chat_command("Alice", "歌单 ID: 00123", invoker_unique_id="alice")
        self.assertEqual(2, len(self.queued()))
        self.detail.assert_awaited_once_with(playlist_id="123", cookie="test-cookie")

    async def test_invalid_explicit_ids_do_not_make_music_api_requests(self):
        for value in ["", "0", "000", "-1", "+123", "12x", "123 456", "１２３"]:
            with self.subTest(value=value):
                await main._handle_chat_command("Alice", "playlist id:" + value, invoker_unique_id="alice")
                self.assertIn("ID", self.notice.await_args.args[0])
        self.assertEqual([], self.queued())
        self.detail.assert_not_awaited()
        self.search.assert_not_awaited()

    async def test_numeric_keyword_still_searches(self):
        await main._handle_chat_command("Alice", "playlist 123456789", invoker_unique_id="alice")
        self.search.assert_awaited_once_with(keywords="123456789", limit=5, type_=1000)
        self.detail.assert_not_awaited()
        self.assertEqual([], self.queued())

    async def test_direct_id_preserves_previous_search_selection(self):
        main._remember_ts_playlist_results("uid:alice", [{"id": "987", "name": "Previous"}])
        await main._handle_chat_command("Alice", "playlist id:123", invoker_unique_id="alice")
        await main._handle_chat_command("Alice", "select 1", invoker_unique_id="alice")
        self.assertEqual(4, len(self.queued()))
        self.assertEqual("987", self.detail.await_args.kwargs["playlist_id"])

    async def test_empty_playlist_reports_no_tracks_without_changing_queue(self):
        self.detail.return_value = {"playlist": {"name": "Empty", "tracks": []}}
        await main._handle_chat_command("Alice", "playlist id:123", invoker_unique_id="alice")
        self.assertEqual([], self.queued())
        self.assertIn("歌单为空", self.notice.await_args.args[0])
