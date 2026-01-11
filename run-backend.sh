#!/usr/bin/env bash
set -euo pipefail

HOST="${TSBOT_HOST:-127.0.0.1}"
PORT="${TSBOT_PORT:-8000}"

exec "$(pwd)/backend/.venv/bin/uvicorn" backend.main:app --reload --host "$HOST" --port "$PORT"
