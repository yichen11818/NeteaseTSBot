"""
Minimal smoke test for voice-service's gRPC control plane.

Connects to voice-service, runs:
  - Ping        (server version)
  - GetStatus   (current playback state)
  - GetAudioFx  (audio FX parameters)
  - SubscribeEvents (server-streaming events, 3-second sample)

The voice-service binary is currently launched with argument `127.0.0.1:9987`,
and that argument is also used as the gRPC bind address (see main.rs:2391),
so the control plane listens on 9987 — not the 50051 default documented in
CLAUDE.md. Override with $VOICE_GRPC_ADDR if needed.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Put our vendored generated stubs on sys.path.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "voice_service_pb"))

import grpc  # provided by backend/.venv

import voice_pb2 as pb
import voice_pb2_grpc as pb_grpc


DEFAULT_ADDR = "127.0.0.1:9987"
ADDR = os.environ.get("VOICE_GRPC_ADDR", DEFAULT_ADDR)


def hr(title: str) -> None:
    print(f"\n=== {title} ===")


def run_ping(stub: pb_grpc.VoiceServiceStub) -> None:
    hr("Ping")
    t0 = time.monotonic()
    resp = stub.Ping(pb.Empty(), timeout=5)
    dt = (time.monotonic() - t0) * 1000
    print(f"  version={resp.version!r}  ({dt:.1f} ms)")


def run_get_status(stub: pb_grpc.VoiceServiceStub) -> None:
    hr("GetStatus")
    t0 = time.monotonic()
    resp = stub.GetStatus(pb.Empty(), timeout=5)
    dt = (time.monotonic() - t0) * 1000
    print(f"  state={resp.state} title={resp.now_playing_title!r} "
          f"source_url={resp.now_playing_source_url!r} "
          f"volume={resp.volume_percent}%  ({dt:.1f} ms)")


def run_get_audio_fx(stub: pb_grpc.VoiceServiceStub) -> None:
    hr("GetAudioFx")
    resp = stub.GetAudioFx(pb.Empty(), timeout=5)
    print(f"  pan={resp.pan:.3f} width={resp.width:.3f} "
          f"swap_lr={resp.swap_lr} bass_db={resp.bass_db:.2f} "
          f"reverb_mix={resp.reverb_mix:.3f}")


def run_subscribe_events(stub: pb_grpc.VoiceServiceStub, seconds: float = 3.0) -> None:
    hr(f"SubscribeEvents (sampling {seconds:.0f}s)")
    req = pb.SubscribeRequest()
    deadline = time.monotonic() + seconds
    count = 0
    try:
        for ev in stub.SubscribeEvents(req, timeout=seconds + 2):
            remaining = max(0.0, deadline - time.monotonic())
            if remaining == 0:
                break
            # Pretty-print whatever payload the event carries.
            fields = []
            for desc, val in ev.ListFields():
                if desc.name == "raw" and val:
                    snippet = val[:120]
                    fields.append(f"{desc.name}=<{len(val)}B> {snippet!r}")
                elif desc.name == "client_joined":
                    fields.append(f"client_joined(name={val.name!r}, client_id={val.client_id})")
                elif desc.name == "client_left":
                    fields.append(f"client_left(name={val.name!r}, client_id={val.client_id})")
                else:
                    fields.append(f"{desc.name}={val!r}")
            print(f"  +{seconds - remaining:5.2f}s  " + " | ".join(fields))
            count += 1
    except grpc.RpcError as e:
        # DeadlineExceeded is expected when we cut the stream off.
        if e.code() != grpc.StatusCode.DEADLINE_EXCEEDED:
            raise
    print(f"  received {count} event(s)")


def main() -> int:
    print(f"voice-service gRPC endpoint: {ADDR}")
    with grpc.insecure_channel(ADDR) as channel:
        # Fail fast if the server is unreachable.
        try:
            grpc.channel_ready_future(channel).result(timeout=3)
        except grpc.FutureTimeoutError:
            print(f"ERROR: channel not ready within 3s — is voice-service running on {ADDR}?",
                  file=sys.stderr)
            return 2

        stub = pb_grpc.VoiceServiceStub(channel)
        run_ping(stub)
        run_get_status(stub)
        run_get_audio_fx(stub)
        run_subscribe_events(stub, seconds=3.0)

    print("\nALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())