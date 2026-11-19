import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import main, runtime_config
from backend.db import Base


class PersistedCacheSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.cache = self.directory / "cache"
        self.cache.mkdir()
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine)()
        self.addCleanup(self.session.close)
        self.settings = main.settings.model_copy(deep=True)
        self.settings.voice_config_file = str(self.directory / "voice.json")
        for target, attribute, value in [
            (main, "settings", self.settings),
            (runtime_config, "settings", self.settings),
            (main, "BILIBILI_AUDIO_DIR", self.cache),
        ]:
            replacement = patch.object(target, attribute, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.enterContext(patch.object(runtime_config, "reconfigure_logger"))
        runtime_config.initialize_runtime_settings(self.session)

    def save_limits(self, *, ttl=0, size=0, partial=0):
        runtime_config.update_settings(self.session, {
            "backend.bilibili_audio_cache_ttl_hours": ttl,
            "backend.bilibili_audio_cache_max_mb": size,
            "backend.bilibili_audio_partial_ttl_minutes": partial,
        }, apply=False)

    def audio(self, name, *, age=0, size=1):
        path = self.cache / name
        path.write_bytes(b"a" * size)
        timestamp = time.time() - age
        os.utime(path, (timestamp, timestamp))
        return path

    def test_restart_uses_persisted_ttl_for_audio_and_partial_files(self):
        self.save_limits(ttl=1, partial=1)
        runtime_config.initialize_runtime_settings(self.session)
        expired = self.audio("BVOLD.m4a", age=7200)
        partial = self.audio("BVFAILED.m4a.part", age=120)
        fresh = self.audio("BVFRESH.m4a")
        main._find_cached_bilibili_audio("BVMISSING")
        self.assertFalse(expired.exists())
        self.assertFalse(partial.exists())
        self.assertTrue(fresh.exists())

    def test_restart_uses_persisted_capacity_and_protects_requested_audio(self):
        self.save_limits(size=1)
        runtime_config.initialize_runtime_settings(self.session)
        requested = self.audio("BVREQUESTED.m4a", age=120, size=700_000)
        other = self.audio("BVOTHER.m4a", age=60, size=700_000)
        self.assertEqual(str(requested.resolve()), main._find_cached_bilibili_audio("BVREQUESTED"))
        self.assertTrue(requested.exists())
        self.assertFalse(other.exists())

    def test_save_only_keeps_active_policy_until_apply(self):
        self.save_limits()
        runtime_config.update_settings(self.session, {})
        self.save_limits(ttl=1)
        old = self.audio("BVOLD.m4a", age=7200)
        main._find_cached_bilibili_audio("BVMISSING")
        self.assertTrue(old.exists())
        runtime_config.update_settings(self.session, {})
        main._find_cached_bilibili_audio("BVMISSING")
        self.assertFalse(old.exists())
