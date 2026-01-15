# TSBot 统一日志系统

TSBot 实现了跨三个组件的统一日志系统，提供一致的日志格式和集中化的日志管理。

## 日志格式

所有组件都使用统一的日志格式：
```
[YYYY-MM-DD HH:MM:SS] [LEVEL] [COMPONENT] MESSAGE
```

示例：
```
[2026-01-15 17:20:30] [INFO] [backend] Server started on 127.0.0.1:8009
[2026-01-15 17:20:31] [INFO] [voice] TS3 connected successfully
[2026-01-15 17:20:32] [INFO] [web] Application initialized
```

## 组件配置

### 后端服务 (Python)
- **日志模块**: `backend/logger.py`
- **配置**: 通过环境变量 `TSBOT_LOG_LEVEL` 和 `TSBOT_LOG_FILE`
- **输出**: 控制台 + 文件 (`logs/backend.log`)

### 语音服务 (Rust)
- **日志模块**: `voice-service/src/logger.rs`
- **配置**: 通过环境变量 `TSBOT_LOG_LEVEL`
- **输出**: 控制台 + 文件 (`logs/voice.log`)

### 前端服务 (Vue)
- **日志模块**: `web/src/utils/logger.ts`
- **配置**: 通过环境变量 `VITE_LOG_LEVEL` 或本地存储
- **输出**: 浏览器控制台 + 文件 (`logs/web.log`)

## 环境变量配置

在 `tsbot.env` 文件中配置日志级别：

```bash
# 日志配置
TSBOT_LOG_LEVEL=INFO          # 后端和语音服务日志级别
TSBOT_LOG_FILE=logs/backend.log  # 后端日志文件路径
VITE_LOG_LEVEL=INFO           # 前端日志级别
```

支持的日志级别：
- `DEBUG`: 详细调试信息
- `INFO`: 一般信息 (默认)
- `WARN`: 警告信息
- `ERROR`: 错误信息

## 日志查看工具

### 1. 统一日志查看器
```bash
# 实时查看所有组件日志
./scripts/log-viewer.sh

# 只查看特定组件
./scripts/log-viewer.sh -c backend
./scripts/log-viewer.sh -c voice
./scripts/log-viewer.sh -c web

# 查看最后100行日志
./scripts/log-viewer.sh -t 100

# 禁用颜色输出
./scripts/log-viewer.sh --no-color
```

### 2. 统一日志合并器
```bash
# 启动统一日志监控 (将所有日志合并到 logs/unified.log)
./scripts/unified-logger.sh
```

### 3. 直接查看日志文件
```bash
# 查看各组件日志
tail -f logs/backend.log
tail -f logs/voice.log
tail -f logs/web.log

# 查看合并日志
tail -f logs/unified.log
```

## 日志文件位置

```
logs/
├── backend.log     # 后端服务日志
├── voice.log       # 语音服务日志
├── web.log         # 前端服务日志
└── unified.log     # 合并的统一日志
```

## 使用示例

### 在代码中使用日志

**后端 (Python)**:
```python
from .logger import logger

logger.info("用户请求播放音乐")
logger.error("连接 TS3 服务器失败")
logger.debug("处理搜索请求", extra={"query": "周杰伦"})
```

**语音服务 (Rust)**:
```rust
use tracing::{info, error, debug};

info!("开始播放音频");
error!("音频编码失败: {}", err);
debug!("接收到音频数据包");
```

**前端 (TypeScript)**:
```typescript
import { logger } from '@/utils/logger'

logger.info('用户点击播放按钮')
logger.error('API 请求失败', error)
logger.debug('组件状态更新', { state: newState })
```

## 生产环境建议

1. **日志级别**: 生产环境建议使用 `INFO` 或 `WARN`
2. **日志轮转**: 配置 logrotate 定期清理日志文件
3. **监控**: 使用 `scripts/log-viewer.sh` 监控关键错误
4. **存储**: 确保 `logs/` 目录有足够的磁盘空间

## 故障排除

### 日志文件不存在
确保 `logs/` 目录存在且有写入权限：
```bash
mkdir -p logs
chmod 755 logs
```

### 日志级别不生效
检查环境变量是否正确设置：
```bash
echo $TSBOT_LOG_LEVEL
source tsbot.env
```

### 权限问题
确保日志文件有写入权限：
```bash
chmod 644 logs/*.log
```
