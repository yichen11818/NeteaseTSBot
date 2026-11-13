import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.db import Base
from backend.runtime_config import DEFINITION_BY_KEY, _env_value, get_value, initialize_runtime_settings, settings_payload, update_settings


class RecoverySettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.addCleanup(self.session.close)
        self.patch = patch.object(settings, 'voice_config_file', str(Path(self.temp.name) / 'voice.json'))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        defaults = patch.multiple(settings, playback_recovery_enabled=True, playback_retry_count=3,
            playback_retry_initial_delay_seconds=15, playback_retry_max_delay_seconds=60,
            playback_exhausted_action='SKIP', playback_cooldown_seconds=300,
            playback_failed_tracks_before_cooldown=3)
        defaults.start()
        self.addCleanup(defaults.stop)
        initialize_runtime_settings(self.session)

    def test_console_exposes_validated_retry_policy_without_restarting_voice(self):
        fields = {item['key']: item for item in settings_payload(self.session)['fields']}
        retry = fields['backend.playback_retry_count']
        self.assertEqual((3, 0, 10, 'recovery', 'none'), (
            retry['value'], retry['minimum'], retry['maximum'], retry['group'], retry['restart']))
        original = Path(settings.voice_config_file).read_text()
        effects = update_settings(self.session, {'backend.playback_retry_count': 1})
        self.assertEqual({'none'}, effects)
        self.assertEqual(1, settings.playback_retry_count)
        self.assertEqual(original, Path(settings.voice_config_file).read_text())

    def test_invalid_policy_update_is_atomic_and_rejects_fractional_or_boolean_counts(self):
        for invalid in [1.5, True, '2.0', -1, 11]:
            with self.subTest(invalid=invalid), self.assertRaises(HTTPException):
                update_settings(self.session, {'backend.playback_retry_count': invalid,
                    'backend.playback_cooldown_seconds': 600})
            self.assertEqual(300, settings.playback_cooldown_seconds)
        with self.assertRaises(HTTPException):
            update_settings(self.session, {'backend.playback_retry_initial_delay_seconds': 120,
                'backend.playback_retry_count': 1})
        self.assertEqual(3, get_value(self.session, DEFINITION_BY_KEY['backend.playback_retry_count']))
        update_settings(self.session, {'backend.playback_retry_initial_delay_seconds': 120,
            'backend.playback_retry_max_delay_seconds': 120, 'backend.playback_retry_count': 0})
        self.assertEqual(0, settings.playback_retry_count)

    def test_save_persists_without_applying_until_apply(self):
        key = 'backend.playback_retry_count'
        update_settings(self.session, {key: 10}, apply=False)
        self.assertEqual(3, settings.playback_retry_count)
        self.assertEqual(10, get_value(self.session, DEFINITION_BY_KEY[key]))
        update_settings(self.session, {})
        self.assertEqual(10, settings.playback_retry_count)
        initialize_runtime_settings(self.session)
        self.assertEqual(10, settings.playback_retry_count)

    def test_environment_policy_is_normalized_and_invalid_values_use_defaults(self):
        action = DEFINITION_BY_KEY['backend.playback_exhausted_action']
        count = DEFINITION_BY_KEY['backend.playback_retry_count']
        with patch.dict('os.environ', {action.env: 'wait', count.env: '0'}):
            self.assertEqual('WAIT', _env_value(action))
            self.assertEqual(0, _env_value(count))
        with patch.dict('os.environ', {action.env: 'delete', count.env: '3.5'}):
            self.assertEqual('SKIP', _env_value(action))
            self.assertEqual(3, _env_value(count))
