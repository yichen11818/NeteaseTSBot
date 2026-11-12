import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from starlette.requests import Request

from backend.auth import (
    SESSION_COOKIE,
    create_session,
    hash_password,
    initialize_admin,
    require_admin,
    require_csrf,
    verify_password,
)
from backend.config import settings
from backend.db import Base
from backend.models import AdminCredential, AppSetting
from backend import managed_assets
from backend.managed_assets import ASSET_BY_KEY, asset_path, delete_asset, save_asset, validate_image
from backend.runtime_config import (
    DEFINITION_BY_KEY,
    get_value,
    initialize_runtime_settings,
    settings_payload,
    update_settings,
    write_voice_config,
)


class AdminAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_password_hash_is_salted_and_verifiable(self) -> None:
        first = hash_password("test-password-123")
        second = hash_password("test-password-123")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("test-password-123", first))
        self.assertFalse(verify_password("wrong-password", first))

    def test_admin_is_initialized_only_once(self) -> None:
        password_file = Path(self.temp_dir.name) / "initial.txt"
        with (
            patch.object(settings, "initial_admin_password", "temporary-password-123"),
            patch.object(settings, "admin_token", ""),
            patch.object(settings, "initial_password_file", str(password_file)),
        ):
            first = initialize_admin(self.session)
            second = initialize_admin(self.session)

        credential = self.session.get(AdminCredential, 1)
        self.assertEqual("temporary-password-123", first)
        self.assertIsNone(second)
        self.assertIsNotNone(credential)
        self.assertTrue(credential.must_change_password)
        self.assertTrue(verify_password("temporary-password-123", credential.password_hash))
        self.assertEqual("temporary-password-123", password_file.read_text().strip())

    def test_initial_session_is_restricted_to_password_change(self) -> None:
        password_file = Path(self.temp_dir.name) / "initial.txt"
        with (
            patch.object(settings, "initial_admin_password", "temporary-password-123"),
            patch.object(settings, "admin_token", ""),
            patch.object(settings, "initial_password_file", str(password_file)),
        ):
            initialize_admin(self.session)
        credential = self.session.get(AdminCredential, 1)
        raw_token, admin_session = create_session(self.session, credential)
        request = Request({
            "type": "http",
            "method": "PUT",
            "path": "/admin/settings",
            "headers": [
                (b"cookie", f"{SESSION_COOKIE}={raw_token}".encode()),
                (b"x-csrf-token", admin_session.csrf_token.encode()),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        })

        with self.assertRaises(HTTPException) as raised:
            require_admin(request, self.session)
        self.assertEqual(403, raised.exception.status_code)
        _, allowed_session = require_admin(request, self.session, allow_password_change=True)
        require_csrf(request, allowed_session)


class RuntimeSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.voice_file = Path(self.temp_dir.name) / "voice.json"
        self.asset_dir_patch = patch.object(managed_assets, "ASSET_DIR", Path(self.temp_dir.name) / "uploads")
        self.voice_config_patch = patch.object(settings, "voice_config_file", str(self.voice_file))
        self.asset_dir_patch.start()
        self.voice_config_patch.start()
        initialize_runtime_settings(self.session)

    def tearDown(self) -> None:
        self.voice_config_patch.stop()
        self.asset_dir_patch.stop()
        self.session.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_sensitive_values_are_never_returned(self) -> None:
        update_settings(self.session, {"voice.ts3_server_password": "server-secret"})
        field = next(item for item in settings_payload(self.session)["fields"] if item["key"] == "voice.ts3_server_password")
        self.assertIsNone(field["value"])
        self.assertTrue(field["configured"])

    def test_clearing_sensitive_value_overrides_environment_seed(self) -> None:
        update_settings(self.session, {"voice.ts3_server_password": "server-secret"})
        update_settings(self.session, {"voice.ts3_server_password": None})
        definition = DEFINITION_BY_KEY["voice.ts3_server_password"]
        self.assertEqual("", get_value(self.session, definition))

    def test_unchanged_form_does_not_request_voice_restart(self) -> None:
        values = {
            field["key"]: field["value"]
            for field in settings_payload(self.session)["fields"]
            if not field["sensitive"]
        }
        effects = update_settings(self.session, values)
        self.assertEqual(set(), effects)

    def test_voice_change_writes_shared_configuration(self) -> None:
        effects = update_settings(self.session, {"voice.ts3_host": "ts.example.test"})
        written = json.loads(self.voice_file.read_text(encoding="utf-8"))
        self.assertIn("voice", effects)
        self.assertEqual("ts.example.test", written["TSBOT_TS3_HOST"])
        self.assertTrue(written["TSBOT_VOICE_CONFIG_REVISION"])

    def test_pcm_buffer_setting_has_safe_console_bounds_and_default(self) -> None:
        field = next(item for item in settings_payload(self.session)["fields"] if item["key"] == "voice.pcm_buffer_seconds")
        self.assertEqual((5, 1, 30, "integer", "backend", "voice"), (
            field["value"], field["minimum"], field["maximum"], field["type"], field["group"], field["restart"],
        ))
        written = json.loads(self.voice_file.read_text())
        self.assertEqual("5", written["TSBOT_VOICE_PCM_BUFFER_SECONDS"])

    def test_pcm_buffer_save_stages_until_apply_and_reset_restores_default(self) -> None:
        before = self.voice_file.read_text()
        effects = update_settings(self.session, {"voice.pcm_buffer_seconds": 10}, apply=False)
        self.assertIn("voice", effects)
        self.assertEqual(before, self.voice_file.read_text())
        self.assertTrue(settings_payload(self.session)["apply_pending"])
        update_settings(self.session, {}, apply=True)
        self.assertEqual("10", json.loads(self.voice_file.read_text())["TSBOT_VOICE_PCM_BUFFER_SECONDS"])
        self.assertFalse(settings_payload(self.session)["apply_pending"])
        update_settings(self.session, {"voice.pcm_buffer_seconds": None})
        self.assertEqual("5", json.loads(self.voice_file.read_text())["TSBOT_VOICE_PCM_BUFFER_SECONDS"])

    def test_pcm_buffer_rejects_invalid_values_without_partial_update(self) -> None:
        definition = DEFINITION_BY_KEY["voice.pcm_buffer_seconds"]
        name_definition = DEFINITION_BY_KEY["web.app_name"]
        before_name = get_value(self.session, name_definition)
        before_file = self.voice_file.read_text()
        for invalid in (0, -1, 31, True, 1.5, "1.5", "invalid", "０"):
            with self.subTest(value=invalid), self.assertRaises(HTTPException) as raised:
                update_settings(self.session, {"voice.pcm_buffer_seconds": invalid, "web.app_name": "must-not-persist"})
            self.assertEqual(422, raised.exception.status_code)
            self.assertEqual(5, get_value(self.session, definition))
            self.assertEqual(before_name, get_value(self.session, name_definition))
            self.assertEqual(before_file, self.voice_file.read_text())

    def test_pcm_buffer_boundaries_are_written_to_voice_configuration(self) -> None:
        for seconds in (1, 30):
            with self.subTest(seconds=seconds):
                effects = update_settings(self.session, {"voice.pcm_buffer_seconds": seconds})
                self.assertIn("voice", effects)
                self.assertEqual(str(seconds), json.loads(self.voice_file.read_text())["TSBOT_VOICE_PCM_BUFFER_SECONDS"])

    def test_pcm_buffer_imports_environment_once_and_persists(self) -> None:
        definition = DEFINITION_BY_KEY["voice.pcm_buffer_seconds"]
        self.session.delete(self.session.get(AppSetting, definition.key))
        self.session.commit()
        with patch.dict(os.environ, {"TSBOT_VOICE_PCM_BUFFER_SECONDS": "12"}):
            initialize_runtime_settings(self.session)
            self.assertEqual(12, get_value(self.session, definition))
        with patch.dict(os.environ, {"TSBOT_VOICE_PCM_BUFFER_SECONDS": "3"}):
            initialize_runtime_settings(self.session)
            self.assertEqual(12, get_value(self.session, definition))
            self.assertEqual("12", json.loads(self.voice_file.read_text())["TSBOT_VOICE_PCM_BUFFER_SECONDS"])

    def test_pcm_buffer_invalid_environment_uses_safe_default(self) -> None:
        definition = DEFINITION_BY_KEY["voice.pcm_buffer_seconds"]
        for invalid in ("0", "31", "-1", "invalid", "1.5", "０"):
            self.session.delete(self.session.get(AppSetting, definition.key))
            self.session.commit()
            with self.subTest(value=invalid), patch.dict(os.environ, {"TSBOT_VOICE_PCM_BUFFER_SECONDS": invalid}):
                initialize_runtime_settings(self.session)
                self.assertEqual(5, get_value(self.session, definition))
                self.assertEqual("5", json.loads(self.voice_file.read_text())["TSBOT_VOICE_PCM_BUFFER_SECONDS"])

    def test_save_only_stages_voice_change_until_apply(self) -> None:
        before = self.voice_file.read_text(encoding="utf-8")

        effects = update_settings(
            self.session,
            {"voice.ts3_host": "staged.example.test"},
            apply=False,
        )

        self.assertIn("voice", effects)
        self.assertEqual(before, self.voice_file.read_text(encoding="utf-8"))
        self.assertTrue(settings_payload(self.session)["apply_pending"])

        applied_effects = update_settings(self.session, {}, apply=True)
        written = json.loads(self.voice_file.read_text(encoding="utf-8"))
        self.assertIn("voice", applied_effects)
        self.assertEqual("staged.example.test", written["TSBOT_TS3_HOST"])
        self.assertTrue(written["TSBOT_VOICE_CONFIG_REVISION"])
        self.assertFalse(settings_payload(self.session)["apply_pending"])

    def test_image_paths_are_managed_assets_instead_of_text_settings(self) -> None:
        payload = settings_payload(self.session)
        field_keys = {field["key"] for field in payload["fields"]}
        asset_keys = {asset["key"] for asset in payload["assets"]}
        self.assertNotIn("web.app_icon", field_keys)
        self.assertNotIn("voice.ts3_avatar_file", field_keys)
        self.assertNotIn("voice.ts3_avatar_dir", field_keys)
        self.assertEqual({"web-app-icon", "teamspeak-avatar"}, asset_keys)

    def test_related_voice_settings_share_navigation_groups(self) -> None:
        fields = {field["key"]: field for field in settings_payload(self.session)["fields"]}
        self.assertEqual("teamspeak", fields["voice.description_title"]["group"])
        self.assertEqual("teamspeak", fields["voice.description_intro"]["group"])
        self.assertEqual("backend", fields["voice.log_level"]["group"])
        self.assertEqual("backend", fields["voice.state_file"]["group"])

    def test_managed_asset_upload_uses_fixed_path_and_validates_signature(self) -> None:
        icon = ASSET_BY_KEY["web-app-icon"]
        avatar = ASSET_BY_KEY["teamspeak-avatar"]
        png = b"\x89PNG\r\n\x1a\n" + b"test-image"
        self.assertEqual("image/png", save_asset(icon, png))
        self.assertEqual(png, asset_path(icon).read_bytes())
        with self.assertRaises(ValueError):
            validate_image(avatar, b"not-an-image")
        with self.assertRaises(ValueError):
            validate_image(avatar, b"\x00\x00\x01\x00ico")
        self.assertTrue(delete_asset(icon))
        self.assertFalse(asset_path(icon).exists())

    def test_avatar_upload_forces_voice_config_revision(self) -> None:
        avatar = ASSET_BY_KEY["teamspeak-avatar"]
        save_asset(avatar, b"GIF89a" + b"avatar")
        write_voice_config(self.session, force_restart=True)
        first = json.loads(self.voice_file.read_text(encoding="utf-8"))
        write_voice_config(self.session, force_restart=True)
        second = json.loads(self.voice_file.read_text(encoding="utf-8"))
        self.assertEqual(str(asset_path(avatar)), first["TSBOT_TS3_AVATAR_FILE"])
        self.assertTrue(first["TSBOT_VOICE_CONFIG_REVISION"])
        self.assertNotEqual(first["TSBOT_VOICE_CONFIG_REVISION"], second["TSBOT_VOICE_CONFIG_REVISION"])


if __name__ == "__main__":
    unittest.main()
