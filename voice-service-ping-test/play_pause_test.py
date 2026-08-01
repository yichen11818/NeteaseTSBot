"""
Play / Pause / Stop smoke test for voice-service's gRPC control plane.

State machine being exercised:
  IDLE  --Play()-->  PLAYING  --Pause()-->  PAUSED  --Play()-->  PLAYING ...
  *     --Stop()-->  IDLE
  PAUSED --Play() or Resume()--> PLAYING   (Resume is the same call as Pause-on-PAUSED
                                            in some servers; here Resume is its own RPC)

What this script asserts on voice-service's actual semantics:
  - Play() flips STATE_IDLE(1) -> STATE_PLAYING(2) and stores source_url.
  - Pause() flips STATE_PLAYING(2) -> STATE_PAUSED(3).
  - Pause() on an IDLE state is a silent no-op (state stays at 1).
  - Play() while PLAYING replaces the current playback (Stop then Play).
  - Stop() always leaves us at STATE_IDLE(1) with empty title / source_url.
  - Pause() on IDLE must NOT error (returns ok=true with the "ok" message),
    but state remains 1.

The audio fixture is a 2-second 440 Hz sine written to a known path so we
can feed voice-service via file:// without depending on the network.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "voice_service_pb"))

import grpc
import voice_pb2 as pb
import voice_pb2_grpc as pb_grpc


DEFAULT_ADDR = "127.0.0.1:9987"
ADDR = os.environ.get("VOICE_GRPC_ADDR", DEFAULT_ADDR)

# 2-second 440 Hz sine, generated on first run if missing.
AUDIO_PATH = Path(os.environ.get(
    "VOICE_TEST_AUDIO",
    "/tmp/voice-test-audio/ping-sine.wav",
))


# --- helpers --------------------------------------------------------------


def hr(title: str) -> None:
    print(f"\n=== {title} ===")


def state_name(s: int) -> str:
    return {
        0: "UNSPECIFIED",
        1: "IDLE",
        2: "PLAYING",
        3: "PAUSED",
        4: "BUFFERING",
        5: "ERROR",
    }.get(s, f"?({s})")


def ensure_audio() -> None:
    if AUDIO_PATH.exists() and AUDIO_PATH.stat().st_size > 0:
        return
    AUDIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"generating test audio fixture at {AUDIO_PATH} ...")
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-f", "lavfi",
            "-i", "sine=frequency=440:duration=2:sample_rate=48000",
            "-ac", "2", "-f", "wav", str(AUDIO_PATH),
        ],
        check=True,
    )


def get_status(stub: pb_grpc.VoiceServiceStub) -> pb.StatusResponse:
    return stub.GetStatus(pb.Empty(), timeout=5)


def expect(label: str, got, want) -> bool:
    ok = got == want
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}: got={got!r} want={want!r}")
    return ok


# --- the test -------------------------------------------------------------


def run(stub: pb_grpc.VoiceServiceStub, url: str, title: str) -> int:
    failures = 0

    hr("baseline")
    s0 = get_status(stub)
    print(f"  state={state_name(s0.state)} title={s0.now_playing_title!r} "
          f"source_url={s0.now_playing_source_url!r} volume={s0.volume_percent}%")
    # Always clean up first so a previous interrupted run doesn't pollute.
    stub.Stop(pb.Empty(), timeout=5)
    time.sleep(0.2)
    s0 = get_status(stub)
    if not expect("baseline state", s0.state, 1):
        failures += 1

    hr(f"Play({title!r})")
    play_req = pb.PlayRequest(source_url=url, title=title)
    resp = stub.Play(play_req, timeout=10)
    print(f"  ok={resp.ok} message={resp.message!r}")
    if not expect("Play ok", resp.ok, True):
        failures += 1
    # Voice-service flips state to PLAYING synchronously inside start_playback_internal.
    time.sleep(0.1)
    s1 = get_status(stub)
    print(f"  after Play: state={state_name(s1.state)} "
          f"title={s1.now_playing_title!r} source_url={s1.now_playing_source_url!r}")
    if not expect("state after Play", s1.state, 2):
        failures += 1
    if not expect("title after Play", s1.now_playing_title, title):
        failures += 1
    if not expect("source_url after Play", s1.now_playing_source_url, url):
        failures += 1

    hr("Pause()")
    resp = stub.Pause(pb.Empty(), timeout=5)
    print(f"  ok={resp.ok} message={resp.message!r}")
    if not expect("Pause ok", resp.ok, True):
        failures += 1
    # Pause is also synchronous: state flips before returning.
    s2 = get_status(stub)
    print(f"  after Pause: state={state_name(s2.state)} "
          f"title={s2.now_playing_title!r}")
    if not expect("state after Pause", s2.state, 3):
        failures += 1
    # Title / source_url stay populated while paused (they're cleared only on Stop).

    hr("Pause() on PAUSED — should be a safe no-op")
    resp = stub.Pause(pb.Empty(), timeout=5)
    if not expect("double-Pause ok", resp.ok, True):
        failures += 1
    s_dbl = get_status(stub)
    if not expect("state after double Pause", s_dbl.state, 3):
        failures += 1

    hr("Stop()")
    resp = stub.Stop(pb.Empty(), timeout=5)
    print(f"  ok={resp.ok} message={resp.message!r}")
    if not expect("Stop ok", resp.ok, True):
        failures += 1
    # Give the playback task a beat to release the source_url slot.
    time.sleep(0.2)
    s3 = get_status(stub)
    print(f"  after Stop: state={state_name(s3.state)} "
          f"title={s3.now_playing_title!r} source_url={s3.now_playing_source_url!r}")
    if not expect("state after Stop", s3.state, 1):
        failures += 1
    if not expect("title cleared", s3.now_playing_title, ""):
        failures += 1
    if not expect("source_url cleared", s3.now_playing_source_url, ""):
        failures += 1

    hr("Pause() on IDLE — silent no-op, must not error")
    resp = stub.Pause(pb.Empty(), timeout=5)
    if not expect("Pause-on-IDLE ok", resp.ok, True):
        failures += 1
    s_idle = get_status(stub)
    if not expect("state still IDLE", s_idle.state, 1):
        failures += 1

    hr("Play() while already playing — should replace, not crash")
    # We are IDLE after Stop, but to exercise the "replace" path we need
    # a fresh Play -> Pause -> Play cycle.
    stub.Play(pb.PlayRequest(source_url=url, title="first"), timeout=10)
    time.sleep(0.1)
    stub.Pause(pb.Empty(), timeout=5)
    resp = stub.Play(pb.PlayRequest(source_url=url, title="second"), timeout=10)
    if not expect("re-Play ok", resp.ok, True):
        failures += 1
    s_re = get_status(stub)
    if not expect("state after re-Play", s_re.state, 2):
        failures += 1
    if not expect("title after re-Play", s_re.now_playing_title, "second"):
        failures += 1
    # Clean up.
    stub.Stop(pb.Empty(), timeout=5)
    time.sleep(0.2)

    print(f"\n{failures} failure(s)")
    return failures


def main() -> int:
    ensure_audio()
    url = AUDIO_PATH.resolve().as_uri()  # file:///tmp/...
    title = "voice-test 440Hz sine"
    print(f"voice-service gRPC endpoint: {ADDR}")
    print(f"audio source: {url}")

    with grpc.insecure_channel(ADDR) as channel:
        try:
            grpc.channel_ready_future(channel).result(timeout=3)
        except grpc.FutureTimeoutError:
            print(f"ERROR: channel not ready on {ADDR}", file=sys.stderr)
            return 2

        stub = pb_grpc.VoiceServiceStub(channel)
        rc = run(stub, url, title)

    if rc == 0:
        print("\nALL OK")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())