import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from backend.levels import LevelService


class LevelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = SimpleNamespace(
            levels_db=self.temp.name + '/levels.db', levels_poll_seconds=60,
            levels_thresholds='{"0.01": 20, "0.03": 21}',
            levels_protected_groups='6,7', levels_afk_channels='9',
            levels_excluded_uids='bot', levels_webquery_url='http://127.0.0.1:10080',
            levels_api_key='secret', levels_server_id=1)
        self.service = LevelService(self.settings)
        self.service.claim(1000)

    def client(self, uid='uid', **changes):
        result = dict(client_type='0', client_unique_identifier=uid, cid='1', clid='2',
                      client_lastconnected='900', client_database_id='42')
        result.update(changes)
        return result

    def row(self, uid='uid'):
        with self.service.db() as db:
            return db.execute('SELECT * FROM level_users WHERE uid=?', (uid,)).fetchone()

    def test_thresholds_duplicate_and_nickname(self):
        self.service.account([self.client(client_nickname='old')], 1000)
        self.service.account([self.client(client_nickname='new')], 1060)
        self.service.account([self.client()], 1060)
        self.assertEqual(60, self.row()['seconds'])
        self.assertEqual(1, self.row()['level'])
        self.service.account([self.client()], 1120)
        self.assertEqual(2, self.row()['level'])

    def test_afk_bot_query_and_offline(self):
        clients = [self.client(), self.client('bot'), self.client('query', client_type='1')]
        self.service.account(clients, 1000)
        self.service.account([self.client(cid='9'), self.client('bot')], 1060)
        self.service.account([self.client()], 1120)
        self.assertEqual(0, self.row()['seconds'])
        self.assertEqual(0, self.row('bot')['seconds'])
        self.assertIsNone(self.row('query'))
        self.service.account([], 1130)
        self.service.account([self.client()], 1140)
        self.assertEqual(0, self.row()['seconds'])

    def test_reconnect_gap_restart_and_lease(self):
        self.service.account([self.client()], 1000)
        self.service.account([self.client(client_lastconnected='1050')], 1060)
        self.assertEqual(0, self.row()['seconds'])
        other = LevelService(self.settings)
        self.assertFalse(other.claim(1060))
        self.assertEqual([], other.account([self.client()], 1060))
        self.assertTrue(other.claim(1200))
        other.account([self.client()], 1200)
        self.assertEqual(0, self.row()['seconds'])
        other.claim(1500)
        other.account([self.client()], 1500)
        self.assertEqual(0, self.row()['seconds'])

    def test_bad_snapshot_rolls_back(self):
        self.service.account([self.client()], 1000)
        with self.assertRaises(ValueError):
            self.service.account([self.client(), self.client()], 1060)
        self.assertEqual(0, self.row()['seconds'])

    def test_clock_rollback_breaks_continuity(self):
        self.service.account([self.client()], 1000)
        self.service.account([self.client()], 1060)
        self.service.account([self.client()], 1040)
        self.service.account([self.client()], 1100)
        self.assertEqual(60, self.row()['seconds'])

    def test_protected_groups_rejected(self):
        self.settings.levels_thresholds = '{"1":6}'
        with self.assertRaises(ValueError):
            LevelService(self.settings)

    def test_webquery_sync_retry_and_protection(self):
        calls = []
        groups = {6, 7, 20, 999}
        fail_add = [True]
        def handler(request):
            command = request.url.path.rsplit('/', 1)[-1]
            calls.append(command)
            self.assertEqual('secret', request.headers['x-api-key'])
            body = []
            code = 0
            if command == 'servergrouplist':
                body = [{'sgid': str(g), 'type': '1'} for g in (20, 21)]
            elif command == 'servergrouppermlist':
                body = [{'permsid': name, 'permvalue': value} for name, value in (
                    ('i_icon_id', '123'), ('i_group_sort_id', '10'),
                    ('i_group_show_name_in_tree', '1'),
                    ('i_group_needed_modify_power', '75'),
                    ('i_group_needed_member_add_power', '75'),
                    ('i_group_needed_member_remove_power', '75'),
                    ('b_group_is_permanent', '1'))]
            elif command == 'clientlist':
                self.assertIn('-uid', request.url.params)
                body = [self.client()]
            elif command == 'servergroupsbyclientid':
                body = [{'sgid': str(g)} for g in groups]
            elif command == 'servergroupaddclient':
                if fail_add[0]:
                    code = 2568
                else:
                    groups.add(int(request.url.params['sgid']))
            elif command == 'servergroupdelclient':
                groups.remove(int(request.url.params['sgid']))
            return httpx.Response(200, json={'status': {'code': code}, 'body': body})

        async def run():
            async with httpx.AsyncClient(base_url='http://localhost',
                    headers={'x-api-key': 'secret'}, transport=httpx.MockTransport(handler)) as client:
                self.service.account([self.client()], 1000)
                self.service.account([self.client()], 1120)
                with patch('backend.levels.time.time', return_value=1120):
                    with self.assertRaises(RuntimeError):
                        await self.service.tick(client)
                    self.assertNotIn('servergroupdelclient', calls)
                    fail_add[0] = False
                    await self.service.tick(client)
                    await self.service.tick(client)
                self.assertEqual({6, 7, 21, 999}, groups)
                self.assertEqual(120, self.row()['seconds'])
                self.assertEqual(1, self.row()['synced'])
        asyncio.run(run())

    def test_query_failure_breaks_continuity(self):
        self.service.account([self.client()], 1000)
        async def run():
            async with httpx.AsyncClient(base_url='http://localhost', transport=httpx.MockTransport(
                    lambda request: httpx.Response(503))) as client:
                with patch('backend.levels.time.time', return_value=1060):
                    with self.assertRaises(httpx.HTTPStatusError):
                        await self.service.tick(client)
        asyncio.run(run())
        self.service.account([self.client()], 1120)
        self.assertEqual(0, self.row()['seconds'])

    def test_admin_group_detected_even_without_protected_list(self):
        calls = []
        def handler(request):
            calls.append(request.url.path)
            if request.url.path.endswith('/servergrouplist'):
                return httpx.Response(200, json={'status': {'code': 0}, 'body': [
                    {'sgid': '20', 'type': '1'}, {'sgid': '21', 'type': '1'}]})
            return httpx.Response(200, json={'status': {'code': 0}, 'body': [
                {'permsid': 'i_permission_modify_power', 'permvalue': '75'}]})
        async def run():
            async with httpx.AsyncClient(base_url='http://localhost',
                    transport=httpx.MockTransport(handler)) as client:
                with patch('backend.levels.time.time', return_value=1060):
                    with self.assertRaises(ValueError):
                        await self.service.tick(client)
        asyncio.run(run())
        self.assertEqual(['/1/servergrouplist', '/1/servergrouppermlist'], calls)

    def test_non_regular_or_missing_groups_rejected_before_mutation(self):
        for group_type in ('0', '2', '3', None):
            with self.subTest(group_type=group_type):
                groups = [{'sgid': '20', 'type': '1'}]
                if group_type is not None:
                    groups.append({'sgid': '21', 'type': group_type})
                command = AsyncMock(return_value=groups)
                with patch.object(self.service, 'command', command), patch(
                        'backend.levels.time.time', return_value=1060):
                    with self.assertRaises(ValueError):
                        asyncio.run(self.service.tick(None))
                command.assert_awaited_once_with(None, 'servergrouplist')

    def test_nonzero_capabilities_and_unknown_permissions_rejected(self):
        for permission in ('i_group_modify_power', 'i_group_member_add_power',
                           'i_group_member_remove_power', 'i_permission_modify_power',
                           'b_virtualserver_modify_name', 'unknown_permission'):
            with self.subTest(permission=permission):
                command = AsyncMock(side_effect=[
                    [{'sgid': '20', 'type': '1'}, {'sgid': '21', 'type': '1'}],
                    [{'permsid': permission, 'permvalue': '75'}]])
                with patch.object(self.service, 'command', command), patch(
                        'backend.levels.time.time', return_value=1060):
                    with self.assertRaises(ValueError):
                        asyncio.run(self.service.tick(None))
                self.assertEqual(['servergrouplist', 'servergrouppermlist'],
                                 [call.args[1] for call in command.await_args_list])

    def test_zero_unknown_permission_allowed(self):
        command = AsyncMock(side_effect=[
            [{'sgid': '20', 'type': '1'}, {'sgid': '21', 'type': '1'}],
            [{'permsid': 'unknown_permission', 'permvalue': '0'}], [], []])
        with patch.object(self.service, 'command', command), patch(
                'backend.levels.time.time', return_value=1060):
            asyncio.run(self.service.tick(None))
        self.assertEqual('clientlist', command.await_args_list[-1].args[1])


if __name__ == '__main__':
    unittest.main()
