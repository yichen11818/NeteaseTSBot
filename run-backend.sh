#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$(pwd)/tsbot.env" ]]; then
  source "$(pwd)/tsbot.env"
fi

HOST="${TSBOT_HOST:-127.0.0.1}"
PORT="${TSBOT_PORT:-8009}"

HOST="${HOST//$'\r'/}"
HOST="${HOST#http://}"
HOST="${HOST#https://}"
HOST="${HOST%%/*}"
HOST="${HOST%%:*}"

PORT="${PORT//$'\r'/}"
PORT="${PORT#:}"

exec "$(pwd)/backend/.venv/bin/uvicorn" backend.main:app --reload --reload-exclude "backend/_generated/*" --host "$HOST" --port "$PORT"
