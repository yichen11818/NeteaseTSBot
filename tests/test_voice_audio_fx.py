import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.voice_client import VoiceClient


class VoiceAudioFxTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = VoiceClient()
        # Load the real generated protobuf types; no RPC is sent.
        self.client._get_stub()
        self.addAsyncCleanup(self.client.close)
        self.stub = SimpleNamespace(GetAudioFx=AsyncMock(), SetAudioFx=AsyncMock())
        self.client._stub = self.stub

    async def test_read_preserves_mono_normal_and_wide_values_after_serialization(self):
        pb2 = self.client._pb2
        for width in (0.0, 1.0, 2.5):
            with self.subTest(width=width):
                original = pb2.AudioFxResponse(width=width, pan=-0.5, bass_db=6.0)
                self.stub.GetAudioFx.return_value = pb2.AudioFxResponse.FromString(original.SerializeToString())
                result = await self.client.get_audio_fx()
                self.assertEqual(width, result.width)
                self.assertEqual(-0.5, result.pan)
                self.assertEqual(6.0, result.bass_db)

    async def test_explicit_mono_write_is_present_in_optional_proto_field(self):
        await self.client.set_audio_fx(width=0.0)
        request = self.stub.SetAudioFx.await_args.args[0]
        received = self.client._pb2.SetAudioFxRequest.FromString(request.SerializeToString())
        self.assertTrue(received.HasField("width"))
        self.assertEqual(0.0, received.width)
        self.assertFalse(received.HasField("pan"))

    async def test_missing_legacy_attribute_keeps_existing_default(self):
        self.stub.GetAudioFx.return_value = SimpleNamespace()
        self.assertEqual(1.0, (await self.client.get_audio_fx()).width)
