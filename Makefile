 .PHONY: backend web voice voice-build voice-run voice-gdb voice-test-server

backend:
	backend/.venv/bin/uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

web:
	cd web && npm run dev

voice:
	cd voice-service && $$HOME/.cargo/bin/cargo build

voice-build: voice

voice-run:
	TSBOT_TS3_IDENTITY_FILE="$${TSBOT_TS3_IDENTITY_FILE:-$(CURDIR)/logs/identity.json}" \
	cd voice-service && $$HOME/.cargo/bin/cargo run -- 127.0.0.1:50051

voice-gdb:
	cd voice-service && $$HOME/.cargo/bin/cargo build
	TSBOT_TS3_IDENTITY_FILE="$${TSBOT_TS3_IDENTITY_FILE:-$(CURDIR)/logs/identity.json}" \
	gdb --args voice-service/target/debug/voice-service 127.0.0.1:50051

voice-test-server:
	TSBOT_TS3_IDENTITY_FILE="$${TSBOT_TS3_IDENTITY_FILE:-$(CURDIR)/logs/identity.json}" \
	cd voice-service && $$HOME/.cargo/bin/cargo run -- 127.0.0.1:50051
