.PHONY: backend web voice voice-run voice-test-server

backend:
	backend/.venv/bin/uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

web:
	cd web && npm run dev

voice:
	cd voice-service && PATH="$$HOME/.cargo/bin:$$PATH" cargo build

voice-run:
	cd voice-service && PATH="$$HOME/.cargo/bin:$$PATH" cargo run -- 127.0.0.1:50051

voice-test-server:
	cd voice-service && PATH="$$HOME/.cargo/bin:$$PATH" TSBOT_TS3_HOST=47.113.188.213 TSBOT_TS3_PORT=9987 TSBOT_TS3_NICKNAME=tsbot cargo run -- 127.0.0.1:50051
