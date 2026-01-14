from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import importlib
from collections.abc import AsyncIterator

import grpc

from .config import settings
from .grpc_codegen import ensure_voice_stubs


@dataclass
class VoiceStatus:
    state: str
    now_playing_title: str
    now_playing_source_url: str
    volume_percent: int


class VoiceClient:
    def __init__(self) -> None:
        self._channel: grpc.aio.Channel | None = None
        self._stub = None
        self._pb2 = None
        self._pb2_grpc = None

    def _get_stub(self):
        if self._stub is not None:
            return self._stub

        ensure_voice_stubs()

        out_dir = Path(__file__).resolve().parent / "_generated"
        if str(out_dir) not in sys.path:
            sys.path.insert(0, str(out_dir))

        self._pb2_grpc = importlib.import_module("voice_pb2_grpc")
        self._pb2 = importlib.import_module("voice_pb2")

        self._channel = grpc.aio.insecure_channel(settings.voice_grpc_addr)
        self._stub = self._pb2_grpc.VoiceServiceStub(self._channel)
        return self._stub

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None
            self._pb2 = None
            self._pb2_grpc = None

    async def ping(self) -> str:
        stub = self._get_stub()
        assert self._pb2 is not None
        resp = await stub.Ping(self._pb2.Empty())
        return resp.version

    async def play(self, source_url: str, title: str, requested_by: str, notice: str = "") -> None:
        stub = self._get_stub()
        assert self._pb2 is not None
        await stub.Play(
            self._pb2.PlayRequest(source_url=source_url, title=title, requested_by=requested_by, notice=notice)
        )

    async def pause(self) -> None:
        stub = self._get_stub()
        assert self._pb2 is not None
        await stub.Pause(self._pb2.Empty())

    async def resume(self) -> None:
        stub = self._get_stub()
        assert self._pb2 is not None
        await stub.Resume(self._pb2.Empty())

    async def stop(self) -> None:
        stub = self._get_stub()
        assert self._pb2 is not None
        await stub.Stop(self._pb2.Empty())

    async def skip(self) -> None:
        stub = self._get_stub()
        assert self._pb2 is not None
        await stub.Skip(self._pb2.Empty())

    async def send_notice(self, message: str) -> None:
        stub = self._get_stub()
        assert self._pb2 is not None
        await stub.SendNotice(self._pb2.NoticeRequest(message=message))

    async def set_volume(self, volume_percent: int) -> None:
        stub = self._get_stub()
        assert self._pb2 is not None
        await stub.SetVolume(self._pb2.SetVolumeRequest(volume_percent=volume_percent))

    async def get_status(self) -> VoiceStatus:
        stub = self._get_stub()
        assert self._pb2 is not None
        resp = await stub.GetStatus(self._pb2.Empty())
        return VoiceStatus(
            state=resp.State.Name(resp.state),
            now_playing_title=resp.now_playing_title,
            now_playing_source_url=resp.now_playing_source_url,
            volume_percent=resp.volume_percent,
        )

    async def subscribe_events(
        self,
        *,
        include_chat: bool = True,
        include_playback: bool = False,
        include_log: bool = False,
    ) -> AsyncIterator[object]:
        stub = self._get_stub()
        assert self._pb2 is not None
        req = self._pb2.SubscribeRequest(
            include_chat=include_chat,
            include_playback=include_playback,
            include_log=include_log,
        )
        async for ev in stub.SubscribeEvents(req):
            yield ev
