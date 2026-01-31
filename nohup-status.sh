#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "ports:"
ss -ltnp | grep -E ':(50051|8009|8080|5173)\b' || true

echo ""
echo "logs:"
echo "  tail -f $ROOT_DIR/logs/voice.log"
echo "  tail -f $ROOT_DIR/logs/backend.log"
echo "  tail -f $ROOT_DIR/logs/web.log"
