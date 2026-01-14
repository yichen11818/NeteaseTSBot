#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$(pwd)/tsbot.env" ]]; then
  source "$(pwd)/tsbot.env"
fi

cd "$(pwd)/web"
exec npm run dev
