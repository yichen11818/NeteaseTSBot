.PHONY: backend web voice

backend:
	backend/.venv/bin/uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

web:
	cd web && npm run dev

voice:
	@echo "voice-service build/run not wired yet"
