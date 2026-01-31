#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

mkdir -p logs

if [[ -f "$ROOT_DIR/tsbot.env" ]]; then
  # shellcheck disable=SC1090
  source "$ROOT_DIR/tsbot.env"
fi

port_pid() {
  local port="$1"
  ss -ltnp "sport = :${port}" 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | head -n1
}

start_one() {
  local name="$1"
  local port="$2"
  local log_file="$3"
  local cmd="$4"

  local pid
  pid="$(port_pid "$port" || true)"
  if [[ -n "${pid}" ]]; then
    echo "[skip] ${name} already listening on :${port} (pid=${pid})"
    return 0
  fi

  echo "[start] ${name}"
  nohup bash -lc "cd '$ROOT_DIR' && if [[ -f '$ROOT_DIR/tsbot.env' ]]; then source '$ROOT_DIR/tsbot.env'; fi; exec ${cmd}" >>"$log_file" 2>&1 &
  echo $! >"$ROOT_DIR/logs/${name}.pid"
}

# Ports are fixed by current code/config:
# - voice-service listens on 127.0.0.1:50051 (Makefile voice-run)
# - backend listens on ${TSBOT_HOST:-127.0.0.1}:${TSBOT_PORT:-8009}
# - web dev server from Vite config (typically 8080 or 5173)

start_one "voice" 50051 "$ROOT_DIR/logs/voice.log" "bash ./run-voicemake.sh"

# backend port from env or default
BACKEND_PORT="${TSBOT_PORT:-8009}"
start_one "backend" "$BACKEND_PORT" "$ROOT_DIR/logs/backend.log" "./run-backend.sh"

# web: get port from env or default
WEB_PORT="${VITE_DEV_PORT:-5173}"
start_one "web" "$WEB_PORT" "$ROOT_DIR/logs/web.log" "./run-web.sh"

echo ""
"$ROOT_DIR/nohup-status.sh" || true
