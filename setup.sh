#!/usr/bin/env bash
# setup.sh - 新机器一键检测环境、补全依赖并准备运行 NetEaseTSBot
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERR]${NC} $*"; }

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PKG_INSTALL="sudo apt update && sudo apt install -y"
    PYTHON_CMD="python3"
    VENV_CMD="python3 -m venv"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    PKG_INSTALL="brew install"
    PYTHON_CMD="python3"
    VENV_CMD="python3 -m venv"
else
    err "Unsupported OS: $OSTYPE"
    exit 1
fi

# 1) Rust / Cargo
if ! command -v cargo &>/dev/null; then
    log "Installing Rust (via rustup)..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    # shellcheck source=/dev/null
    source "$HOME/.cargo/env"
else
    log "Rust/Cargo already installed: $(cargo --version)"
fi

# 2) Python3 & venv
if ! command -v "$PYTHON_CMD" &>/dev/null; then
    log "Installing Python3..."
    $PKG_INSTALL python3 python3-pip python3-venv
else
    log "Python3 already installed: $($PYTHON_CMD --version)"
fi

# 3) Node.js
if ! command -v node &>/dev/null; then
    log "Installing Node.js (via nvm)..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
    # shellcheck source=/dev/null
    export NVM_DIR="$HOME/.nvm"
    # shellcheck source=/dev/null
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    nvm install --lts
    nvm use --lts
    nvm alias default node
else
    log "Node.js already installed: $(node --version)"
fi

# 4) System packages (cmake, ffmpeg, build-essential)
log "Ensuring system packages (cmake, ffmpeg, build-essential)..."
$PKG_INSTALL cmake build-essential ffmpeg

# 5) Prepare backend venv
if [[ ! -d "backend/.venv" ]]; then
    log "Creating backend venv..."
    $VENV_CMD backend/.venv
fi
log "Installing backend Python dependencies..."
backend/.venv/bin/pip install -r backend/requirements.txt

# 6) Install frontend deps
if [[ ! -d "web/node_modules" ]]; then
    log "Installing frontend npm dependencies..."
    cd web && npm install && cd ..
else
    log "Frontend node_modules already present."
fi

# 7) Build voice-service
log "Building voice-service (cargo build)..."
cd voice-service && PATH="$HOME/.cargo/bin:$PATH" cargo build && cd ..

# 8) Check tsbot.env
ENV_FILE="tsbot.env"
if [[ ! -f "$ENV_FILE" ]]; then
    warn "$ENV_FILE not found, copying from example..."
    cp tsbot.env.example "$ENV_FILE"
    warn "Please edit $ENV_FILE and fill in your TS3 server, NetEase cookies, etc."
else
    log "$ENV_FILE exists."
    # Quick sanity check for required fields
    MISSING=()
    while read -r line; do
        if [[ $line =~ ^export[[:space:]]+TSBOT_TS3_HOST= ]]; then
            if [[ $line =~ \"your_teamspeak_server_ip\" ]] || [[ $line =~ \"\" ]]; then
                MISSING+=("TSBOT_TS3_HOST")
            fi
        fi
        if [[ $line =~ ^export[[:space:]]+NETEASE_ADMIN_COOKIE= ]]; then
            if [[ $line =~ \"your_admin_cookie_here\" ]] || [[ $line =~ \"\" ]]; then
                MISSING+=("NETEASE_ADMIN_COOKIE")
            fi
        fi
    done < <(grep -E '^export (TSBOT_TS3_HOST|NETEASE_ADMIN_COOKIE)=' "$ENV_FILE" || true)
    if [[ ${#MISSING[@]} -gt 0 ]]; then
        warn "Please fill in these fields in $ENV_FILE: ${MISSING[*]}"
    fi
fi

# 9) Ensure logs dir
mkdir -p logs

log "=== Setup complete ==="
log "Next steps:"
log "  1) Edit $ENV_FILE with your TS3 and NetEase settings"
log "  2) Start services:"
log "     ./run-voicemake.sh   # (in one terminal)"
log "     ./run-backend.sh     # (in another terminal)"
log "     ./run-web.sh         # (in another terminal)"
log "  Or use nohup scripts:"
log "     ./nohup-start.sh"
log "     ./nohup-status.sh"
log "     ./nohup-stop.sh"
log "Happy botting!"
