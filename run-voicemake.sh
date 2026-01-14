#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$(pwd)/tsbot.env" ]]; then
  source "$(pwd)/tsbot.env"
fi

TSBOT_TS3_HOST=${TSBOT_TS3_HOST:-47.113.188.213} \
TSBOT_TS3_PORT=${TSBOT_TS3_PORT:-9987} \
TSBOT_TS3_NICKNAME=${TSBOT_TS3_NICKNAME:-tsbot} \
TSBOT_TS3_CHANNEL_ID=${TSBOT_TS3_CHANNEL_ID:-2} \
make voice-run