# TSBot 部署和运行指南

TSBot 是一个基于 TeamSpeak 的音乐机器人，包含 Python 后端、Vue 前端和 Rust 语音服务。

## 系统要求

- **操作系统**: Linux（推荐 Ubuntu 20.04+）或 Windows 10/11（推荐 PowerShell 7+）
- **Python**: 3.8+
- **Node.js**: 16+
- **CMake**: 3.16+
- **Rust**: 1.70+（推荐，默认语音服务实现）
- **TeamSpeak 3 Client SDK**：仅旧版 C++ 语音服务路径需要；默认 Rust `voice-service` 不依赖它

## 快速开始

### 1. 克隆项目
```bash
git clone <repository-url>
cd tsbot
```

### 2. 环境配置
复制环境配置文件并修改：
```bash
cp tsbot.env.example tsbot.env
# 编辑 tsbot.env，至少设置用于加密敏感配置的 TSBOT_COOKIE_KEY
```

### 3. 安装依赖

#### 后端依赖 (Python)
```bash
# 创建虚拟环境
cd backend
python3 -m venv .venv
source .venv/bin/activate

# 安装 Python 依赖
pip install -r requirements.txt
```

#### 前端依赖 (Node.js)
```bash
# 安装前端依赖
cd web
npm install
cd ..
```

#### 语音服务依赖
```bash
# 安装 CMake 和构建工具
sudo apt update
sudo apt install cmake build-essential

# 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env


```

### 4. 构建项目
```bash
# 使用 Makefile 构建所有组件
make all

# 或者分别构建
make backend-setup  # 创建后端虚拟环境并安装依赖
make web-build      # 安装前端依赖并构建生产产物
make voice-build    # 构建语音服务
```

## 运行项目

### Linux

#### 方法一：前台启动（生产方式）
```bash
# 启动语音服务
./run-voicemake.sh

# 启动后端（新终端）
./run-backend.sh

# 启动前端生产预览（新终端）
./run-web.sh
```

以上脚本会自动读取项目根目录下的 `tsbot.env`。其中 `run-web.sh` 会先构建前端产物，再以 preview 方式监听 `TSBOT_WEB_PORT`（默认 `8080`）。

#### 方法二（远程推荐）：使用 nohup 一键启动/停止（不依赖 screen/yum）
```bash
# 第一次使用需要赋予执行权限
chmod +x ./nohup-start.sh ./nohup-stop.sh ./nohup-status.sh

# 停止（按端口兜底清理，避免重复进程）
./nohup-stop.sh

# 启动（会分别启动 voice/backend/web，并写日志到 logs/）
./nohup-start.sh

# 查看状态（端口 + 日志路径）
./nohup-status.sh
```

#### 方法三：本地开发启动
开 3 个终端分别运行：

```bash
./run-voicemake.sh
```

```bash
backend/.venv/bin/uvicorn backend.main:app --reload --reload-exclude "backend/_generated/*" --host 127.0.0.1 --port 8009
```

```bash
npm --prefix web run dev
```

本地开发默认访问 `http://127.0.0.1:5173`，并通过 `/api` 反向代理到 backend。

### Windows（PowerShell）

Windows 下建议先启动后端和前端；如需真正播放音频，再补齐语音服务依赖并启动 `voice-service`。

#### 1. 复制环境配置
```powershell
Copy-Item tsbot.env.example tsbot.env
# 编辑 tsbot.env，至少设置用于加密敏感配置的 TSBOT_COOKIE_KEY
```

#### 2. 安装后端依赖
```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

#### 3. 安装前端依赖
```powershell
npm.cmd --prefix web install
```

#### 4. 前台启动（生产方式）
分别打开两个 PowerShell 窗口执行：

```powershell
.\run-backend.ps1
```

```powershell
.\run-web.ps1
```

这两个脚本会自动读取项目根目录下的 `tsbot.env`。其中 `run-web.ps1` 会先构建前端产物，再以 preview 方式在 `TSBOT_WEB_PORT`（默认 `8080`）启动。

#### 5. 本地开发启动
分别打开两个 PowerShell 窗口执行：

```powershell
backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8009
```

```powershell
npm.cmd --prefix web run dev
```

#### 6. 启动语音服务
打开第三个 PowerShell 窗口执行：

```powershell
.\run-voicemake.ps1
```

`run-voicemake.ps1` 在 Windows 上默认使用 `MinGW-w64` 工具链构建 Rust 语音服务，额外需要：

- `Rust` / `cargo`
- `CMake`
- `MinGW-w64`（需提供 `gcc.exe`、`g++.exe`、`mingw32-make.exe`）
- `ffmpeg` 并加入 `PATH`

如工具未加入 `PATH`，也可以在 `tsbot.env` 中额外配置这些路径：

- `TSBOT_CARGO`
- `TSBOT_CMAKE`
- `TSBOT_MINGW_BIN`
- `TSBOT_FFMPEG`

如果暂时没有这些工具，后端和前端仍然可以正常启动，但播放控制相关接口会因为 gRPC 语音服务未启动而不可用。

## Docker 运行

此节是仓库默认部署网络的现行运维入口，配置核验日期：2026-11-14。核验范围为仓库 Compose、启动脚本及配置示例；未核验远程测试、生产或灾备主机，也未修改任何已运行容器。源码开发的三个进程默认通过本机回环地址通信；Docker 中的后端通过 `voice-service:50051` 访问语音服务。

项目根目录已提供：

- `docker-compose.yml`
- `docker-compose.prebuilt.yml`
- `Dockerfile.backend`
- `Dockerfile.voice-service`
- `Dockerfile.web`

### 1. 准备配置

```bash
cp tsbot.env.example tsbot.env
```

> 如果 `NeteaseCloudMusicApi` 跑在宿主机，请在容器启动后通过 Web 系统配置将地址设为 `http://host.docker.internal:3000/`。

### 2. 构建并启动

```bash
docker compose up -d --build
```

### 3. 查看运行状态

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f web
```

### 4. 停止并清理容器

```bash
docker compose down
```

默认端口映射：

- `8009:8009`（backend）
- `8080:8080`（web，Nginx 托管生产前端产物，并将 `/api/*` 反向代理到 backend）

语音服务的 gRPC 没有应用层认证，因此三个默认 Compose 文件均不发布其宿主机端口。容器内仍监听 `50051`，不影响后端播放控制。升级后重新执行所用 Compose 的 `up -d` 才会移除旧容器的端口映射；只更新文件不会改变正在运行的服务。

本地开发需要从宿主机调试容器内 gRPC 时，可显式加入调试配置（仅绑定 `127.0.0.1`）：

```bash
docker compose -f docker-compose.prebuilt.yml -f docker-compose.voice-debug.yml up -d
```

源码构建使用 `docker-compose.yml` 替换上面的首个文件；离线镜像使用 `docker-compose.portable.yml`。结束调试后不带调试文件重新执行 `up -d`。跨主机部署不属于默认拓扑；不要直接把未认证的 gRPC 发布到公网。

### 5. 使用预构建镜像（Docker Hub / GHCR）

如果你不想在本机构建，也可以直接使用仓库发布的预构建镜像。项目额外提供了 `docker-compose.prebuilt.yml`：

```bash
# Docker Hub（默认 latest）
docker compose -f docker-compose.prebuilt.yml up -d

# 固定版本，例如 v0.4.0
TSBOT_IMAGE_TAG=v0.4.0 docker compose -f docker-compose.prebuilt.yml up -d

# 改用 GHCR
TSBOT_IMAGE_REGISTRY=ghcr.io \
TSBOT_IMAGE_NAMESPACE=yumi118 \
docker compose -f docker-compose.prebuilt.yml up -d
```

补充说明：

- GitHub **Packages** 页面显示的是 GHCR 包；如果只推 Docker Hub，这里会是空的。
- 现在看到 `backend` / `web` / `voice-service` 三个镜像仓库是正常的，因为当前发布策略就是按三个服务分别构建。
- GitHub **Releases** 页面里的 `tar.gz` 与 `SHA256SUMS.txt` 是软件包归档，不是 Docker 镜像。
- 自 v1.0.0 起，Linux amd64 发布包包含完整的 Git 跟踪源码、Dockerfiles、`scripts/`、`servers.example.json` 与文档，以及 `bin/voice-service` 和 `web/dist/` 构建产物。解压后可使用下方的多服务器生成命令；多服务器 Compose 仍从包内源码构建镜像。原有启动脚本仍采用源码构建流程，若使用附带的 Voice 二进制，应在包根目录、加载原 `tsbot.env` 后显式运行 `./bin/voice-service 127.0.0.1:50051`。构建产物不包含个人环境文件、数据库或实例数据。

## 一个项目连接多个 TeamSpeak 服务器

配置核验日期：2026-11-17。多服务器模式使用一个 Web 入口，每台 TeamSpeak 服务器对应一组独立的 backend / voice 容器；三种镜像各构建一次，各组复用镜像。队列、历史、音量、频道、机器人身份、音乐账号、管理员账号和配置分别保存。网页顶部可以切换服务器；不同标签页可以同时管理不同服务器。切换网页不会停止任何服务器的播放。

这是 Docker Compose 的独立部署模式。原来的 Compose、`run-*.sh`、`run-*.ps1` 和 `nohup-*` 仍用于单服务器。以下步骤只配置本地源码及部署文件，不代表已修改远程测试、生产或灾备环境。

### 首次创建

需要 Python 3.10+（生成器只使用标准库）、Docker Engine 和 Docker Compose v2。在项目根目录执行；Windows 使用 `Copy-Item` 代替 `cp`：

```bash
cp servers.example.json servers.json
# 编辑 servers.json，为每台服务器设置稳定的 id 和显示名称 name
python scripts/multi_server.py --init-env
docker compose -f docker-compose.multi.json config --quiet
docker compose -f docker-compose.multi.json up -d --build
```

`servers.json` 只接受 `web_port` 和 `servers`。每个服务器条目只接受 `id`、`name`，不在这里存放地址、Cookie 或密码。`id` 使用小写字母、数字及单个连字符，以字母开头、字母或数字结尾；加上 `backend-` 后不能超过 DNS 标签的 63 字符限制。`id` 是数据目录与服务名的一部分，创建后保持稳定；更改展示名称只改 `name`。

生成器创建以下本地文件，均已加入 Git 和 Docker 构建上下文的忽略规则：

| 文件或目录 | 用途 |
| --- | --- |
| `docker-compose.multi.json` | Compose 可直接读取的 JSON 配置；固定项目名 `tsbot-multi` |
| `.multi-server/` | Nginx 网关配置及只包含 ID、名称的公开服务器清单 |
| `instances/<id>/tsbot.env` | 每台服务器的启动配置与独立随机加密密钥 |
| `instances/<id>/data/` | SQLite 数据库、上传资源及等级系统数据 |
| `instances/<id>/logs/` | 日志、初始管理员密码、身份及 Voice 配置/状态文件 |

`--init-env` 只创建缺少的环境文件，不覆盖现有密钥、数据库或配置。不加此选项时，缺少环境文件会明确报错。生成器不会删除被移出清单的服务器数据。

打开 `http://<部署主机>:8080`（端口可通过 `web_port` 修改），网页进入清单中的第一台服务器。也可以直接访问 `/s/home/search`、`/s/friends/search`。各服务器的 `admin` 初始密码位于 `instances/<id>/logs/initial-admin-password.txt`，分别登录并修改密码，然后在当前服务器的“系统配置”填写 TeamSpeak 地址、频道和音乐平台账号。

默认只有 Web 发布宿主机端口；backend 和 voice 仅连接该组的 Docker 网络，Web 网关接入所有组。后端分别使用 `voice-<id>:50051`，不发布 gRPC。每组的临时音频卷、数据目录及网络都独立。容器内数据库与共享配置路径由生成器固定，避免旧环境文件把两个实例指向同一数据位置。

生成的 backend、voice 和 Web 均包含健康检查、`restart: unless-stopped`，以及 `json-file` 日志轮转（每文件 10 MiB，最多 3 个）。健康检查分别验证 backend / voice 的本地 TCP 监听端口和 Web 首页；不代表 TeamSpeak 已连接或音乐源可用。健康状态不会自动触发容器重启，重启策略只处理进程退出。Web 与 backend 不以其他实例健康为启动条件：某组故障时仍可打开服务器选择页，正常组继续提供服务；故障组的 API 返回错误，恢复后由动态 DNS 重新连接。

配置核验：2026-11-19。生成器回归测试及 CI 网关独立启动检查覆盖配置和入口可用性；不代表已验证生产、灾备或真实 TeamSpeak 连接。已有部署需重新运行生成器并执行 `docker compose -f docker-compose.multi.json up -d` 才会应用这些策略，单服务器 Compose 和启动脚本不受影响。

登录 Cookie 同时按名称和 `/api/servers/<id>/` 路径隔离。API、头像上传、播放控制均走当前服务器；外部集成示例为 `/api/servers/home/external/status`，使用 home 自己配置的 Token。不存在的服务器返回错误，不会改为控制第一台服务器。名称清单为公开信息，不应把敏感内容写入 `name`。

浏览器里的本地收藏、搜索历史和主题仍是个人偏好，可以跨服务器使用；音乐账号 Cookie 缓存、“我喜欢的”缓存及音质偏好按服务器区分。此次不增加统一管理员账号或跨服务器同步播放。

### 增加、改名与停止服务器

增加服务器时编辑 `servers.json`，再次生成并启动；修改 `name` 也要重新生成。网关需要重建容器以加载新的路由：

```bash
python scripts/multi_server.py --init-env
docker compose -f docker-compose.multi.json up -d --build
docker compose -f docker-compose.multi.json up -d --force-recreate web
docker compose -f docker-compose.multi.json ps
docker compose -f docker-compose.multi.json logs --tail=100 backend-home voice-home
```

修改 TeamSpeak 地址、频道和音乐账号时直接使用对应服务器的 Web 设置页，不需要重新生成清单。后端的“Voice gRPC 地址”应保留为 `voice-<id>:50051`。

只停止一组可执行 `docker compose -f docker-compose.multi.json stop backend-friends voice-friends`。永久移出清单前先停止这组，再编辑清单、生成配置及重建 Web；旧容器可在确认归属后用 Compose 清理孤立服务。数据目录和音频卷不会由生成器清理。停止整个项目使用 `docker compose -f docker-compose.multi.json down`；备份应同时包含服务器清单、各自的环境文件、data 和 logs 中的身份/状态文件。

### 从已有单服务器部署迁入

先停止旧实例并备份其数据库、`tsbot.env`、上传资源、日志中的身份和 Voice 状态。将原来的环境文件复制到 `instances/home/tsbot.env`，原 `data/` 与 `logs/` 分别复制到 `instances/home/` 下；源码模式使用根目录数据库时，将它复制为 `instances/home/data/tsbot.db`。必须保留原 `TSBOT_COOKIE_KEY`，不要用新生成的密钥替换旧数据的密钥。

随后生成多服务器配置并启动。旧数据库中的设置优先于环境变量，因此首次进入 home 的 Web 设置后，要将保存的 Voice gRPC 地址改为 `voice-home:50051`，核对身份文件、播放状态等路径在容器中是否有效，并应用配置。其他服务器使用各自的新目录与新密钥。迁移前后不得让两组运行中的服务同时写同一数据库或身份文件。

本地原有单服务器如果占用 `8080`，应先停止它或修改多服务器的 `web_port`。外层反向代理应把整个站点交给多服务器 Web 网关，不再把 `/api` 单独转发到旧的 `8009`。

2026-11-17 本地验证覆盖生成器测试、前后端回归与构建，以及两个实际 FastAPI 进程经本机 Nginx 的队列、配置、登录/退出、Cookie 路径和 CSRF 隔离；Playwright 验证了服务器切换、登录和手机布局。本机 Nginx 为 1.21，验收时使用回环地址替换 Docker 上游并去掉新版动态 DNS 指令。本机没有 Docker；多服务器 Compose 配置及镜像对应的 Nginx 1.30.2 配置检查已在 [GitHub Actions](https://github.com/yichen11818/NeteaseTSBot/actions/runs/43911443404) 通过。尚未验收整套多服务器容器启动或真实 TeamSpeak 播放，配置检查通过不代表这些运行链路已经验证。

## 启动配置与 Web 系统配置

编辑 `tsbot.env` 文件：

```env
# 后端服务配置
TSBOT_HOST=127.0.0.1
TSBOT_PORT=8009
TSBOT_VOICE_GRPC_ADDR=127.0.0.1:50051
TSBOT_COOKIE_KEY=change_me_to_a_random_string
TSBOT_VOICE_CONFIG_FILE=./logs/voice-service.json
TSBOT_INITIAL_PASSWORD_FILE=./logs/initial-admin-password.txt

# 前端生产服务配置（run-web.sh / nohup-start.sh 使用）
TSBOT_WEB_HOST=127.0.0.1
TSBOT_WEB_PORT=8080
# TSBOT_WEB_API_PROXY_TARGET=http://127.0.0.1:8009
# TSBOT_WEB_ALLOWED_HOSTS=dev.example.com,.example.com

# 前端开发服务配置（npm run dev 使用）
VITE_DEV_HOST=127.0.0.1
VITE_DEV_PORT=5173

# 前端 API Base（推荐默认 /api，由 dev / preview / Docker 反向代理到 backend）
VITE_API_BASE=/api
# VITE_WEB_PUBLIC_URL=https://music.example.com
# 数据库配置 (可选)
DATABASE_URL=sqlite:///./tsbot.db
```

说明：

- 首次启动后，从后端日志或 `logs/initial-admin-password.txt` 取得 `admin` 的初始密码。
- 第一次登录会强制更换密码，成功后初始密码文件自动删除。
- TeamSpeak / TS6、网易云 API、缓存、日志、外部 Token、界面名称都在 Web 的“系统配置”中维护。
- 界面图标和 TeamSpeak 机器人头像在 Web 设置页直接上传，固定保存在数据库目录旁的 `uploads/` 中；不再填写服务器图片路径。
- “保存配置”只将表单持久化到数据库；“应用配置”才会更新运行服务。应用 TeamSpeak 或 Voice 改动后，voice-service 会优雅断开并自动用新配置重启，Web 在新进程返回后提示“已重启成功”。
- “TeamSpeak 配置”包含连接、频道、身份和客户端简介；“Voice 服务”包含后端到 Voice 的连接与 Voice 运行参数。
- 旧部署的 `TSBOT_TS3_*` 等变量会在数据库缺少对应值时导入一次，迁移后可从环境文件删除。
- QQ 音乐能力由后端内建提供，不需要额外部署独立的 QQ 音乐 API 服务。
- 网易云、QQ 音乐和 B 站授权统一位于“系统配置 → 音乐会员登录”；管理员 Cookie 写入数据库并使用 `TSBOT_COOKIE_KEY` 加密存储。
- 忘记密码可在服务器本地执行 `.venv/bin/python -m backend.admin_cli reset-password`。

## 音乐源支持

### 网易云音乐

- 依赖外部 `NeteaseCloudMusicApi` 服务。
- 需要在 Web 系统配置中填写该服务地址。

### QQ 音乐

- 搜索、歌单、歌词等能力由后端直接提供。
- 播放链接、用户歌单等登录态能力建议在 Web 控制台中扫码登录 QQ 音乐。
- 管理员平台授权接口使用 Web 登录会话保护，不再使用长期 `x-admin-token`。

## 访问应用

启动成功后，访问：
- **前端界面（生产脚本 / Docker）**: http://127.0.0.1:8080 (可通过 `TSBOT_WEB_PORT` 修改；Docker Compose 默认也使用 `8080`)
- **前端界面（本地开发）**: http://127.0.0.1:5173 (可通过 `VITE_DEV_PORT` 修改)
- **后端 API**: http://127.0.0.1:8009 (可通过 `TSBOT_PORT` 环境变量修改端口)
- **API 文档**: http://127.0.0.1:8009/docs

## 故障排除

### 常见问题

1. **Python 依赖安装失败**
   ```bash
   # 更新 pip
   pip install --upgrade pip
   
   # 安装系统依赖
   sudo apt install python3-dev python3-pip
   ```

2. **Node.js 依赖安装失败**
   ```bash
   # 清理缓存
   npm cache clean --force
   rm -rf web/node_modules web/package-lock.json
   cd web && npm install
   ```

3. **语音服务构建失败**
   ```bash
   # 安装缺失的依赖
   sudo apt install libssl-dev pkg-config
   
   # 重新构建
   cargo clean --manifest-path voice-service/Cargo.toml
   make voice-build
   ```

4. **TeamSpeak 连接失败**
   - 检查 TeamSpeak 服务器地址、端口、频道配置和密码
   - 默认 Rust `voice-service` 不需要 TS3 Client SDK；只有旧版 C++ 路径才依赖它
   - 检查防火墙设置

### 日志查看
```bash
# 查看后端日志
tail -f logs/backend.log

# 查看语音服务日志
tail -f logs/voice.log
```

## 开发模式

### 热重载开发
```bash
# 后端热重载
source backend/.venv/bin/activate
uvicorn backend.main:app --reload

# 前端热重载
cd web && npm run dev
```

### 代码生成
```bash
# 重新生成 gRPC 代码
python backend/grpc_codegen.py
```

## 生产部署

### 使用 systemd 服务
当前仓库**未内置** `systemd` service 模板。若你需要以 systemd 托管，请自行创建 service，并分别调用：

- `run-voicemake.sh`
- `run-backend.sh`
- `run-web.sh`

如果只是单机或轻量部署，优先使用上面的 `nohup-start.sh` / `nohup-stop.sh` / `nohup-status.sh`。

### 使用 Nginx 反向代理
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
    }
    
    location /api {
        proxy_pass http://127.0.0.1:8009;
    }
}
```

## 更多信息

- 查看 `TODO` 文件了解开发计划
- 查看 `LICENSE` 文件了解许可证信息
- 遇到问题请提交 Issue

## 语音预缓冲

解码后的 PCM 只保存在有界通道内，每个 20 ms 播放周期消费一帧；通道满时阻塞读取，背压经管道传回 FFmpeg，不丢弃音频帧。Linux 缓冲为 50 帧（约 1 秒、192 KB PCM），Windows 为 200 帧（约 4 秒、768 KB PCM），另有单帧和 FFmpeg 内部缓冲。容量定义位于 `voice-service/src/pcm_buffer.rs`，不限制歌曲时长。短于预缓冲目标的音频在 EOF 时照常排空。相关 Rust 单元测试由 PR 检查运行。
