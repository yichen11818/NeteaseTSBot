#!/usr/bin/env bash
# play.sh — search a song by Chinese/English keywords on Netease Cloud Music
#           and play it on the tsbot voice-service via the backend's HTTP API.
#
# Usage:
#   play.sh                          # default: 周深 大鱼
#   play.sh 周杰伦 晴天
#   play.sh -n                       # enqueue only, do not play_now
#   play.sh -l higher 周杰伦 晴天    # specify quality level (auto/standard/higher/...)
#   play.sh -h                       # help
#
# No web UI involved. Calls the running tsbot-backend at 127.0.0.1:8009.

set -euo pipefail

BACKEND="${TSBOT_BACKEND:-http://127.0.0.1:8009}"

usage() {
    sed -n '2,12p' "$0"
    exit 0
}

LEVEL="auto"
PLAY_NOW=true

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage ;;
        -n|--enqueue) PLAY_NOW=false; shift ;;
        -l|--level) LEVEL="$2"; shift 2 ;;
        --) shift; break ;;
        -*) echo "unknown flag: $1" >&2; exit 2 ;;
        *)  break ;;
    esac
done

if [ $# -eq 0 ]; then
    set -- "周深 大鱼"
fi

KEYWORDS="$*"
echo "==> search: $KEYWORDS"

# 1. Search via backend (backend -> NeteaseCloudMusicApi).
SEARCH_JSON=$(curl -sS -G \
    --data-urlencode "keywords=$KEYWORDS" \
    --data "limit=1" \
    --data "type=1" \
    "$BACKEND/search")

# 2. Parse the first hit into 4 NUL-separated fields. Read them in via
#    process substitution so the NUL bytes survive (command substitution
#    would strip them). One Python call prints all 4 fields; bash splits
#    them on NUL into an indexed array.
mapfile -d $'\0' -t FIELDS < <(python3 - "$SEARCH_JSON" <<'PY'
import json, sys
try:
    data = json.loads(sys.argv[1])
    songs = ((data.get("raw") or {}).get("result") or {}).get("songs") or []
    if not songs:
        sys.stdout.write("")
    else:
        s = songs[0]
        artists = " / ".join(a.get("name","") for a in s.get("artists") or [])
        out = [str(s.get("id","")), s.get("name","") or "", artists, str(s.get("duration") or 0)]
        sys.stdout.write("\0".join(out))
except Exception as e:
    sys.stdout.write("")
PY
)

SONG_ID="${FIELDS[0]:-}"
SONG_NAME="${FIELDS[1]:-}"
SONG_ARTIST="${FIELDS[2]:-}"
SONG_DURATION="${FIELDS[3]:-}"

if [ -z "$SONG_ID" ]; then
    echo "error: no songs found or search failed" >&2
    exit 1
fi

echo "    picked: id=$SONG_ID title=$SONG_NAME artist=$SONG_ARTIST duration_ms=$SONG_DURATION"

# 3. POST /queue/netease.
BODY=$(python3 - "$SONG_ID" "$SONG_NAME" "$SONG_ARTIST" "$SONG_DURATION" "$LEVEL" "$PLAY_NOW" <<'PY'
import json, sys
song_id, title, artist, duration_ms, level, play_now = sys.argv[1:]
print(json.dumps({
    "song_id": song_id,
    "title": title,
    "artist": artist,
    "duration_ms": int(duration_ms),
    "level": level,
    "play_now": play_now.lower() == "true",
}))
PY
)

echo "==> POST $BACKEND/queue/netease level=$LEVEL play_now=$PLAY_NOW"
RESP=$(curl -sS -X POST -H "Content-Type: application/json" \
    -d "$BODY" \
    "$BACKEND/queue/netease")

echo "    response: $RESP"

echo "$RESP" | python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
    if d.get('ok') is True:
        print(f\"    ok: queue_id={d.get('id')} trial={d.get('trial')}\")
    else:
        print('    ok=false; reason:', d.get('detail') or d, file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print('    bad response:', e, file=sys.stderr); sys.exit(1)
"

echo "OK"