#!/usr/bin/env bash
set -euo pipefail

# 处理信号，确保子进程也能正确退出
cleanup() {
    echo "Shutting down voice service..."
    if [[ -n "${VOICE_PID:-}" ]]; then
        kill -TERM "$VOICE_PID" 2>/dev/null || true
        wait "$VOICE_PID" 2>/dev/null || true
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

if [[ -f "$(pwd)/tsbot.env" ]]; then
  source "$(pwd)/tsbot.env"
fi

echo "Starting voice service..."
echo "Use Ctrl+C to stop gracefully"

# 启动语音服务并获取PID
TSBOT_TS3_HOST=${TSBOT_TS3_HOST:-47.113.188.213} \
TSBOT_TS3_PORT=${TSBOT_TS3_PORT:-9987} \
TSBOT_TS3_NICKNAME=${TSBOT_TS3_NICKNAME:-tsbot} \
TSBOT_TS3_CHANNEL_ID=${TSBOT_TS3_CHANNEL_ID:-2} \
make voice-run &

VOICE_PID=$!

# 等待子进程结束
wait "$VOICE_PID"