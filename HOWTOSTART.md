# TSBot 部署和运行指南

TSBot 是一个基于 TS3 的音乐机器人，包含 Python 后端、Vue 前端和 C++/Rust 语音服务。

## 系统要求

- **操作系统**: Linux (推荐 Ubuntu 20.04+)
- **Python**: 3.8+
- **Node.js**: 16+
- **CMake**: 3.16+
- **Rust**: 1.70+ (可选，用于 Rust 语音服务)
- **TeamSpeak 3 Client SDK**

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
# 编辑 tsbot.env 文件，配置你的 TS3 服务器信息
```

### 3. 安装依赖

#### 后端依赖 (Python)
```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装 Python 依赖
pip install -r backend/requirements.txt
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

# 如果使用 Rust 版本
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

### 方法一：使用脚本 (推荐)
```bash
# 启动语音服务
./run-voicemake.sh

# 启动后端 (新终端)
./run-backend.sh

# 启动前端 (新终端)
./run-web.sh
```

### 方法一（远程推荐）：使用 nohup 一键启动/停止（不依赖 screen/yum）
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

### 方法二：手动启动

#### 1. 启动语音服务
```bash
# 设置环境变量并启动
TSBOT_TS3_HOST=your_ts3_host \
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

## 环境变量配置

编辑 `tsbot.env` 文件：

```env
# TS3 服务器配置
TSBOT_TS3_HOST=your_teamspeak_server_ip
TSBOT_TS3_PORT=9987
TSBOT_TS3_NICKNAME=tsbot
TSBOT_TS3_CHANNEL_ID=2

# 后端服务配置
TSBOT_HOST=127.0.0.1
TSBOT_PORT=8009
TSBOT_VOICE_GRPC_ADDR=127.0.0.1:50051

# 前端服务配置
VITE_DEV_HOST=127.0.0.1
VITE_DEV_PORT=5173

# 日志配置
TSBOT_LOG_LEVEL=INFO
VITE_LOG_LEVEL=INFO

# 数据库配置 (可选)
DATABASE_URL=sqlite:///./tsbot.db

# 网易云音乐配置
NETEASE_ADMIN_COOKIE=your_admin_cookie_here
```

## 访问应用

启动成功后，访问：
- **前端界面**: http://127.0.0.1:8080 (可通过 VITE_DEV_PORT 环境变量修改端口)
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

4. **TS3 连接失败**
   - 检查 TS3 服务器地址和端口
   - 确认 TS3 Client SDK 已正确安装
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