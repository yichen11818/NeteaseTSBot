from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VoiceStatus:
    state: str
    now_playing_title: str
    now_playing_source_url: str
    volume_percent: int


class VoiceClient:
    def __init__(self) -> None:
        self._available = False

    async def ping(self) -> str:
        raise RuntimeError("voice-service grpc client not wired yet; generate python stubs from proto/voice.proto")

    async def play(self, source_url: str, title: str, requested_by: str) -> None:
        raise RuntimeError("voice-service grpc client not wired yet; generate python stubs from proto/voice.proto")

    async def pause(self) -> None:
        raise RuntimeError("voice-service grpc client not wired yet; generate python stubs from proto/voice.proto")

    async def resume(self) -> None:
        raise RuntimeError("voice-service grpc client not wired yet; generate python stubs from proto/voice.proto")

    async def stop(self) -> None:
        raise RuntimeError("voice-service grpc client not wired yet; generate python stubs from proto/voice.proto")

    async def skip(self) -> None:
        raise RuntimeError("voice-service grpc client not wired yet; generate python stubs from proto/voice.proto")

    async def set_volume(self, volume_percent: int) -> None:
        raise RuntimeError("voice-service grpc client not wired yet; generate python stubs from proto/voice.proto")

    async def get_status(self) -> VoiceStatus:
        raise RuntimeError("voice-service grpc client not wired yet; generate python stubs from proto/voice.proto")
