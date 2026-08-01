"""
End-to-end Netease Cloud playback, no web UI involved.

Pipeline (all from this script):

  NeteaseCloudMusicApi (public mirror, default 47.113.188.213:3000)
       GET /search?keywords=...         -> pick first song
       GET /song/url/v1?id=...&level=standard
                                       -> returns an mp3 URL + freeTrialInfo
                                          (30-second preview if no MUSIC_U)
  tsclientlib VoiceService gRPC (default 127.0.0.1:9987)
       Play(source_url=<mp3>, title=<title>, notice=...)

Why this bypasses the tsbot-backend: backend's /queue/netease hard-requires
an admin cookie before it will even call song_url_v1 (main.py:3087).
song_url_v1 itself works fine without a cookie -- it returns a 128 kbps
trial URL on its own (verified: /search and /song/url/v1 both 200 from
the public mirror without any cookie).

Without a cookie:
  * Many songs return code=200 + a 128 kbps URL with `freeTrialInfo`
    (first 30 seconds preview, then ffmpeg will just see EOF).
  * Some songs return 200 with no url (and no `freeTrialInfo`) for
    truly DRM-locked tracks; the script will detect that and report it.

With a MUSIC_U cookie set in env NETEASE_COOKIE, the script passes it
through and you get full-length higher-bitrate URLs.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "voice_service_pb"))

import grpc
import voice_pb2 as pb
import voice_pb2_grpc as pb_grpc


NETEASE_API_BASE = os.environ.get(
    "NETEASE_API_BASE", "http://47.113.188.213:3000/"
).rstrip("/")
VOICE_GRPC_ADDR = os.environ.get("VOICE_GRPC_ADDR", "127.0.0.1:9987")
NETEASE_COOKIE = os.environ.get("NETEASE_COOKIE", "")


def _http_get(path: str, params: dict, cookie: str | None = None, timeout: float = 15.0) -> dict:
    qs = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None}, doseq=True
    )
    headers = {"User-Agent": "tsbot-cli/1.0"}
    if cookie:
        headers["Cookie"] = cookie
    url = f"{NETEASE_API_BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def search_first(keywords: str) -> dict:
    data = _http_get(
        "/search",
        {
            "keywords": keywords,
            "limit": 1,
            "offset": 0,
            "type": 1,  # 1 = songs
        },
    )
    songs = ((data.get("result") or {}).get("songs") or [])
    if not songs:
        raise SystemExit(f"no songs found for {keywords!r}")
    return songs[0]


def resolve_url(song_id: str, level: str = "standard") -> tuple[str | None, dict]:
    """Return (mp3_url, raw_response_data). mp3_url is None if gated."""
    data = _http_get(
        "/song/url/v1",
        {
            "id": song_id,
            "level": level,
            "timestamp": int(time.time() * 1000),
        },
        cookie=NETEASE_COOKIE or None,
    )
    items = data.get("data") or []
    if not items:
        return None, data
    item = items[0]
    url = item.get("url")
    return url, item


def main(argv: list[str]) -> int:
    keywords = " ".join(argv).strip() or "周深 大鱼"

    print(f"==> search keywords={keywords!r} via {NETEASE_API_BASE}")
    song = search_first(keywords)
    song_id = str(song["id"])
    title = str(song.get("name") or song_id)
    artists = " / ".join(a.get("name", "") for a in song.get("artists") or [])
    duration_ms = int(song.get("duration") or 0)
    print(
        f"    picked: id={song_id} title={title!r} artists={artists!r} "
        f"duration_ms={duration_ms} fee={song.get('fee')}"
    )

    print(f"==> resolve mp3 URL via /song/url/v1 (level=standard, cookie={'yes' if NETEASE_COOKIE else 'NO'})")
    url, info = resolve_url(song_id, level="standard")
    if not url:
        print(f"    no url returned: {json.dumps(info)[:400]}")
        raise SystemExit("netease API refused to give an mp3 URL for this song")

    br = info.get("br")
    trial = info.get("freeTrialInfo") or {}
    print(f"    url len={len(url)} br={br} type={info.get('type')} "
          f"size={info.get('size')} freeTrial={trial if trial else 'no'}")

    # Connect voice-service gRPC.
    print(f"==> connect voice-service gRPC at {VOICE_GRPC_ADDR}")
    with grpc.insecure_channel(VOICE_GRPC_ADDR) as ch:
        try:
            grpc.channel_ready_future(ch).result(timeout=3)
        except grpc.FutureTimeoutError:
            raise SystemExit(f"voice-service not READY at {VOICE_GRPC_ADDR}")
        stub = pb_grpc.VoiceServiceStub(ch)

        # Pre-state.
        pre = stub.GetStatus(pb.Empty(), timeout=5)
        print(f"    pre-state: state={pre.state} title={pre.now_playing_title!r}")

        # Fire Play.
        notice = ""
        if trial:
            notice = "30-second preview"
        print(f"==> Play(title={title!r}, source_url=<{url[:80]}...>, notice={notice!r})")
        resp = stub.Play(
            pb.PlayRequest(
                source_url=url,
                title=title,
                notice=notice,
            ),
            timeout=15,
        )
        print(f"    Play ok={resp.ok} message={resp.message!r}")
        if not resp.ok:
            raise SystemExit(f"Play refused: {resp.message}")

        # Wait for state transition.
        deadline = time.monotonic() + 6.0
        final = None
        while time.monotonic() < deadline:
            s = stub.GetStatus(pb.Empty(), timeout=5)
            if s.state == 2:  # PLAYING
                final = s
                break
            time.sleep(0.4)
        if final is None:
            raise SystemExit("voice never transitioned to PLAYING within 6 s")
        print(
            f"==> post-state: state={final.state} title={final.now_playing_title!r} "
            f"source_url={final.now_playing_source_url[:80]}..."
        )

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))