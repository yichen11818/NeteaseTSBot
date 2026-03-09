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
# 编辑 tsbot.env 文件，配置你的 TeamSpeak 服务器、音乐源和 cookie 信息
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
make voice-build  # 构建语音服务
make backend-setup  # 设置后端
make web-build  # 构建前端
```

## 运行项目

### Linux

#### 方法一：使用脚本（推荐）
```bash
# 启动语音服务
./run-voicemake.sh

# 启动后端（新终端）
./run-backend.sh

# 启动前端（新终端）
./run-web.sh
```

以上脚本会自动读取项目根目录下的 `tsbot.env`。

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

#### 方法三：手动启动

#### 1. 启动语音服务
```bash
# 设置环境变量并启动
TSBOT_TS3_HOST=your_teamspeak_host \
TSBOT_TS3_PORT=9987 \
TSBOT_TS3_NICKNAME=tsbot \
TSBOT_TS3_CHANNEL_ID=2 \
make voice-run
```

#### 2. 启动后端
```bash
# 激活虚拟环境
source .venv/bin/activate

# 启动后端服务
TSBOT_HOST=127.0.0.1 \
TSBOT_PORT=8009 \
TSBOT_VOICE_GRPC_ADDR=127.0.0.1:50051 \
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8009
```

#### 3. 启动前端
```bash
# 开发模式
npm --prefix web run dev

# 或者构建生产版本
npm --prefix web run build
npm --prefix web run preview
```

### Windows（PowerShell）

Windows 下建议先启动后端和前端；如需真正播放音频，再补齐语音服务依赖并启动 `voice-service`。

#### 1. 复制环境配置
```powershell
Copy-Item tsbot.env.example tsbot.env
# 编辑 tsbot.env，填写 TeamSpeak、cookie、音乐源等配置
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

#### 4. 启动后端与前端
分别打开两个 PowerShell 窗口执行：

```powershell
.\run-backend.ps1
```

```powershell
.\run-web.ps1
```

这两个脚本会自动读取项目根目录下的 `tsbot.env`。

#### 5. 启动语音服务
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

项目根目录已提供：

- `docker-compose.yml`
- `Dockerfile.backend`
- `Dockerfile.voice-service`
- `Dockerfile.web`

### 1. 准备配置

```bash
cp tsbot.env.example tsbot.env
```

> 如果 `NeteaseCloudMusicApi` 跑在宿主机，请将 `TSBOT_NETEASE_API_BASE` 配置为 `http://host.docker.internal:3000/`。

### 2. 构建并启动

```bash
docker compose up -d --build
```

### 3. 查看运行状态

```bash
docker compose ps
docker compose logs -f
```

### 4. 停止并清理容器

```bash
docker compose down
```

默认端口映射：

- `50051:50051`（voice-service gRPC）
- `8009:8009`（backend）
- `5173:5173`（web）

## 环境变量配置

编辑 `tsbot.env` 文件：

```env
# TeamSpeak 服务器配置（变量名 `TSBOT_TS3_*` 为兼容历史保留，也用于 TS6 主客户端连接）
TSBOT_TS3_HOST=your_teamspeak_server_ip
TSBOT_TS3_PORT=9987
TSBOT_TS3_NICKNAME=tsbot
TSBOT_TS3_CHANNEL_ID=2
TSBOT_TS3_IDENTITY_FILE=./logs/identity.json
# TSBOT_TS3_CHANNEL_PATH=/Music
# TSBOT_TS3_SERVER_PASSWORD=
# TSBOT_TS3_CHANNEL_PASSWORD=

# 后端服务配置
TSBOT_HOST=127.0.0.1
TSBOT_PORT=8009
TSBOT_VOICE_GRPC_ADDR=127.0.0.1:50051
TSBOT_COOKIE_KEY=change_me_to_a_random_string

# 前端服务配置
VITE_DEV_HOST=127.0.0.1
VITE_DEV_PORT=5173

# 日志配置
TSBOT_LOG_LEVEL=INFO
VITE_LOG_LEVEL=INFO

# 数据库配置 (可选)
DATABASE_URL=sqlite:///./tsbot.db

# 网易云音乐配置（仅使用网易云能力时需要）
TSBOT_NETEASE_API_BASE=http://127.0.0.1:3000/
```

说明：

- `voice-service` 主客户端连接已支持 TS6；配置项仍沿用 `TSBOT_TS3_*` 命名。
- QQ 音乐能力由后端内建提供，不需要额外部署独立的 QQ 音乐 API 服务。
- QQ 音乐与网易云的管理员 cookie 都通过 Web 控制台或 admin API 写入数据库，并使用 `TSBOT_COOKIE_KEY` 加密存储。
- 可选的 `TSBOT_TS3_SERVERQUERY_*` 仍是旧式 ServerQuery fallback，不是 TS6 的 HTTP(S) Query。

## 音乐源支持

### 网易云音乐

- 依赖外部 `NeteaseCloudMusicApi` 服务。
- 需要将该服务地址配置到 `TSBOT_NETEASE_API_BASE`。

### QQ 音乐

- 搜索、歌单、歌词等能力由后端直接提供。
- 播放链接、用户歌单等登录态能力建议在 Web 控制台中扫码登录 QQ 音乐。
- 如启用了 `TSBOT_ADMIN_TOKEN`，调用 `/admin/qqmusic/*` 接口时需带 `x-admin-token` 请求头。

## 访问应用

启动成功后，访问：
- **前端界面**: http://127.0.0.1:5173 (可通过 VITE_DEV_PORT 环境变量修改端口)
- **后端API**: http://127.0.0.1:8009 (可通过 TSBOT_PORT 环境变量修改端口)
- **API文档**: http://127.0.0.1:8009/docs

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
   make clean
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
tail -f logs/voice-service.log
```

## 开发模式

### 热重载开发
```bash
# 后端热重载
source .venv/bin/activate
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
```bash
# 复制服务文件
sudo cp scripts/tsbot-*.service /etc/systemd/system/

# 启用服务
sudo systemctl enable tsbot-backend
sudo systemctl enable tsbot-voice
sudo systemctl enable tsbot-web

# 启动服务
sudo systemctl start tsbot-backend
sudo systemctl start tsbot-voice
sudo systemctl start tsbot-web
```

### 使用 Nginx 反向代理
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5173;
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
