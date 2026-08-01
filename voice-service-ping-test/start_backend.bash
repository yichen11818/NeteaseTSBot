#!/bin/bash
cd /root/tsbot
source tsbot.env
export TSBOT_VOICE_GRPC_ADDR=127.0.0.1:9987          # 必须：当前 voice-service 实际监听 9987，不是 50051
export TSBOT_NETEASE_API_BASE=http://47.113.188.213:3000/   # 覆盖 tsbot.env 默认的 127.0.0.1:3000
exec /root/tsbot/backend/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8009
