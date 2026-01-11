#!/usr/bin/env bash
set -euo pipefail

cd "$(pwd)/web"
exec npm run dev
