TSBOT_TS3_HOST=47.113.188.213 \
TSBOT_TS3_PORT=9987 \
TSBOT_TS3_NICKNAME=tsbot \
TSBOT_TS3_CHANNEL_ID=2 \
make voice-run


TSBOT_HOST=127.0.0.1 \
TSBOT_PORT=8009 \
TSBOT_VOICE_GRPC_ADDR=127.0.0.1:50051 \
./.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8009


npm --prefix web run dev