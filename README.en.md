# TSBot (NeteaseTSBot)

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Linux-informational)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Node](https://img.shields.io/badge/node-16%2B-brightgreen)
![Rust](https://img.shields.io/badge/rust-1.70%2B-orange)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115.6-009688?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-42b883?logo=vue.js&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)
[![中文 README](https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87-red)](README.md)

TSBot is a TeamSpeak 3 based music bot that provides:

- **TS3 voice playback** (connects to TS3 and plays audio via `voice-service`)
- **Queue and playback control** (pause/resume/next/previous, volume, shuffle/repeat, etc.)
- **Netease music search/playlists/likes/lyrics** (via external `NeteaseCloudMusicApi`)
- **Web console** (Vue 3 frontend for search/queue/lyrics/settings)

![Preview](docs/1.png)
![Preview](docs/2.png)
![Preview](docs/3.png)
![Preview](docs/4.png)
![Preview](docs/5.png)

## Why TSBot (Pain Points and Goals)

This project aims to solve the "dependency hell" and maintainability issues of older setups.

A common old stack looked like this:

- `TS3AudioBot`
- `NeteaseCloudMusicApi`
- `TS3AudioBot-NetEaseCloudmusic-plugin`

In practice, this stack often suffers from:

- **Heavy coupling**: the three pieces are tightly bound by versions, interfaces, and runtime assumptions, making deployment and troubleshooting expensive.
- **Hard API replacement/updates**: Netease-related APIs change frequently, and replacing/upgrading API logic can cascade into bot core or plugin code.
- **Critical plugin disappearance**: if `TS3AudioBot-NetEaseCloudmusic-plugin` becomes unavailable, the whole chain breaks and can no longer be maintained.

TSBot redraws those boundaries:

- **Voice and business logic are decoupled**: `voice-service` only handles "connect to TS3 + play audio", exposing a stable gRPC control surface.
- **Netease is a replaceable dependency**: backend talks to external `NeteaseCloudMusicApi` through `TSBOT_NETEASE_API_BASE`; future replacements/upgrades are largely isolated in backend adapters.
- **Maintainable and evolvable architecture**: frontend/backend/voice-service can iterate independently, reducing single-point breakage.

The project has 3 components:

- **backend/**: Python/FastAPI backend (queue/search/Netease integration/voice control)
- **voice-service/**: Rust voice service (TS3 connection + audio playback, exposes gRPC to backend)
- **web/**: Vue 3 + Vite frontend (web console/player UI)

More docs:

- `HOWTOSTART.md` (deployment/run guide)
- `LOGGING.md` (unified logging system)
- `web/README.md` (frontend details)

## System Requirements

- **Linux** (Ubuntu 20.04+ recommended)
- **Python**: 3.8+
- **Node.js**: 16+
- **Rust**: 1.70+ (for `voice-service`)

Netease capability dependency (required for search/playlists/song URL/lyrics):

- **NeteaseCloudMusicApi** (self-hosted HTTP service)

## Architecture Overview

```text
   [web (Vue3)]  <--HTTP-->  [backend (FastAPI)]  <--gRPC-->  [voice-service (Rust)]  -->  TeamSpeak 3
                                 |
                                 | HTTP
                                 v
                        [NeteaseCloudMusicApi]
```

## Netease Support (`NeteaseCloudMusicApi`)

This project does **not** directly call Netease official APIs. Instead, it forwards through your own `NeteaseCloudMusicApi` deployment.

- **NPM**: https://www.npmjs.com/package/NeteaseCloudMusicApi
- **Docs**: https://neteasecloudmusicapi.js.org/#/

After deployment, set `TSBOT_NETEASE_API_BASE` to the service URL (for example, `http://127.0.0.1:3000/`).

Common deployment options (choose one, exact args follow upstream docs):

```bash
# Option A: start directly with npx
npx NeteaseCloudMusicApi@latest

# Option B: use Docker (common image: binaryify/neteasecloudmusicapi)
# docker run -d --name ncm-api -p 3000:3000 binaryify/neteasecloudmusicapi
```

It is recommended to deploy this service where **backend can reach it** (same host `127.0.0.1:3000` or an internal network address).

## Quick Start (Recommended)

### 1) Configure Environment Variables

Copy the template and edit:

```bash
cp tsbot.env.example tsbot.env
```

At minimum, set:

- `TSBOT_TS3_HOST` / `TSBOT_TS3_PORT` / `TSBOT_TS3_CHANNEL_ID` (TS3 connection settings)
- `TSBOT_NETEASE_API_BASE` (your NeteaseCloudMusicApi URL, for example `http://127.0.0.1:3000/`)
- `TSBOT_COOKIE_KEY` (used to encrypt stored admin cookie; use your own random string)

Optional:

- `TSBOT_ADMIN_TOKEN`: enable backend admin endpoint protection (request header `x-admin-token`)
- `VITE_DEV_HOST` / `VITE_DEV_PORT`: frontend dev server bind host/port
- `VITE_API_BASE`: frontend backend base URL (default `http://127.0.0.1:8009`)

### 2) Install Dependencies

Backend (Python):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

Frontend (Node):

```bash
cd web
npm install
cd ..
```

Voice service (Rust):

```bash
# Install Rust if not installed
# https://rustup.rs/

# Build voice-service
make voice-build
```

### 3) One-Command Startup (`nohup`, recommended for remote servers)

```bash
chmod +x ./nohup-start.sh ./nohup-stop.sh ./nohup-status.sh

# Start (launches voice/backend/web and writes logs to logs/)
./nohup-start.sh

# Check status (ports + log paths)
./nohup-status.sh

# Stop
./nohup-stop.sh
```

### 4) Local Development Startup (foreground)

Run in 3 terminals:

```bash
./run-voicemake.sh
```

```bash
./run-backend.sh
```

```bash
./run-web.sh
```

## Default Ports

- **voice-service gRPC**: `127.0.0.1:50051`
- **backend**: `127.0.0.1:8009` (`TSBOT_PORT`)
- **web (Vite dev)**: `127.0.0.1:5173` (`VITE_DEV_PORT`; `tsbot.env.example` uses 8080 as an example, your `tsbot.env` wins)

Backend OpenAPI docs:

- `http://127.0.0.1:8009/docs`

## Netease Cookie (Admin)

Backend encrypts and stores the "admin Netease cookie" in database (`tsbot.db`) for:

- getting more stable song URLs (avoid anonymous restrictions on some endpoints)
- accessing features requiring login state (playlists, likes, etc.)

Setup APIs (if admin token is enabled, include header `x-admin-token: <TSBOT_ADMIN_TOKEN>`):

- `POST /admin/cookie`: store cookie
- `GET /admin/status`: check if cookie exists
- `GET /admin/account`: verify cookie validity

The frontend also provides a setup UI (see `web/README.md`).

## Logging

Logs are written to `logs/` by default:

- `logs/backend.log`
- `logs/voice.log`
- `logs/web.log`

See `LOGGING.md` for details (`scripts/log-viewer.sh` / `scripts/unified-logger.sh`).

## Project Structure

```text
.
├── backend/         # FastAPI backend
├── web/             # Vue3 frontend
├── voice-service/   # Rust voice service (gRPC + TS3)
├── proto/           # gRPC proto definitions
├── data/            # runtime data/config (e.g. config.json)
├── logs/            # runtime logs (created by startup scripts)
├── HOWTOSTART.md
├── LOGGING.md
└── tsbot.env.example
```

## FAQ

- **Is the web port 5173 or 8080?**
  - Vite default is `5173` (see `web/vite.config.ts`)
  - `tsbot.env.example` uses `8080` as an example
  - `nohup-start.sh` / `run-web.sh` both read root `tsbot.env`; your exported `VITE_DEV_PORT` is final

- **Frontend request errors / cannot reach backend?**
  - Default backend is `http://127.0.0.1:8009`
  - If you changed backend host/port, set `VITE_API_BASE` in `web/.env` or `tsbot.env`

- **Backend cannot reach voice-service?**
  - Check `TSBOT_VOICE_GRPC_ADDR` is `127.0.0.1:50051`
  - Ensure `make voice-run` or `run-voicemake.sh` is running

## License

See `LICENSE`.
