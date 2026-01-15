#!/usr/bin/env bash
# 统一日志输出脚本
# 用于将多个组件的日志合并输出，带统一格式

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS_DIR="$ROOT_DIR/logs"

# 创建日志目录
mkdir -p "$LOGS_DIR"

# 统一日志格式函数
format_log() {
    local component="$1"
    local color="$2"
    
    while IFS= read -r line; do
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        if [[ -t 1 ]]; then
            # 终端输出带颜色
            echo -e "\033[${color}m[${timestamp}] [INFO] [${component}]\033[0m ${line}"
        else
            # 文件输出不带颜色
            echo "[${timestamp}] [INFO] [${component}] ${line}"
        fi
    done
}

# 颜色定义
COLOR_VOICE="36"    # 青色
COLOR_BACKEND="32"  # 绿色  
COLOR_WEB="33"      # 黄色

# 启动统一日志监控
echo "Starting unified logger..."
echo "Logs will be saved to: $LOGS_DIR/unified.log"
echo "Press Ctrl+C to stop"
echo ""

# 使用 tail -f 监控各组件日志文件，并格式化输出
{
    if [[ -f "$LOGS_DIR/voice.log" ]]; then
        tail -f "$LOGS_DIR/voice.log" | format_log "voice" "$COLOR_VOICE" &
    fi
    
    if [[ -f "$LOGS_DIR/backend.log" ]]; then
        tail -f "$LOGS_DIR/backend.log" | format_log "backend" "$COLOR_BACKEND" &
    fi
    
    if [[ -f "$LOGS_DIR/web.log" ]]; then
        tail -f "$LOGS_DIR/web.log" | format_log "web" "$COLOR_WEB" &
    fi
    
    # 等待所有后台进程
    wait
} | tee "$LOGS_DIR/unified.log"
