#!/usr/bin/env bash
# 统一日志查看器
# 实时查看所有组件的日志输出

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS_DIR="$ROOT_DIR/logs"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 显示帮助信息
show_help() {
    echo "TSBot 统一日志查看器"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help     显示此帮助信息"
    echo "  -f, --follow   实时跟踪日志 (默认)"
    echo "  -t, --tail N   显示最后 N 行日志 (默认: 50)"
    echo "  -c, --component COMP  只显示指定组件的日志 (voice|backend|web|all)"
    echo "  --no-color     禁用颜色输出"
    echo ""
    echo "示例:"
    echo "  $0                    # 实时查看所有组件日志"
    echo "  $0 -c backend         # 只查看后端日志"
    echo "  $0 -t 100             # 显示最后100行日志"
}

# 默认参数
FOLLOW=true
TAIL_LINES=50
COMPONENT="all"
USE_COLOR=true

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -t|--tail)
            TAIL_LINES="$2"
            shift 2
            ;;
        -c|--component)
            COMPONENT="$2"
            shift 2
            ;;
        --no-color)
            USE_COLOR=false
            shift
            ;;
        *)
            echo "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
done

# 格式化日志行
format_log_line() {
    local component="$1"
    local line="$2"
    local color=""
    
    if [[ "$USE_COLOR" == "true" ]]; then
        case "$component" in
            "voice") color="$CYAN" ;;
            "backend") color="$GREEN" ;;
            "web") color="$YELLOW" ;;
            *) color="$NC" ;;
        esac
    fi
    
    # 如果日志行已经包含组件标识，直接输出
    if [[ "$line" =~ \[.*\].*\[.*\].*\[.*\] ]]; then
        echo -e "${color}${line}${NC}"
    else
        # 否则添加统一格式
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo -e "${color}[${timestamp}] [INFO] [${component}] ${line}${NC}"
    fi
}

# 检查日志目录
if [[ ! -d "$LOGS_DIR" ]]; then
    echo "日志目录不存在: $LOGS_DIR"
    echo "请先启动 TSBot 服务"
    exit 1
fi

echo "TSBot 统一日志查看器"
echo "日志目录: $LOGS_DIR"
echo "组件: $COMPONENT"
echo "显示行数: $TAIL_LINES"
echo "实时跟踪: $FOLLOW"
echo ""
echo "按 Ctrl+C 退出"
echo "----------------------------------------"

# 构建 tail 命令参数
TAIL_CMD="tail"
if [[ "$FOLLOW" == "true" ]]; then
    TAIL_CMD="$TAIL_CMD -f"
fi
TAIL_CMD="$TAIL_CMD -n $TAIL_LINES"

# 根据组件选择显示日志
case "$COMPONENT" in
    "voice")
        if [[ -f "$LOGS_DIR/voice.log" ]]; then
            $TAIL_CMD "$LOGS_DIR/voice.log" | while IFS= read -r line; do
                format_log_line "voice" "$line"
            done
        else
            echo "语音服务日志文件不存在: $LOGS_DIR/voice.log"
        fi
        ;;
    "backend")
        if [[ -f "$LOGS_DIR/backend.log" ]]; then
            $TAIL_CMD "$LOGS_DIR/backend.log" | while IFS= read -r line; do
                format_log_line "backend" "$line"
            done
        else
            echo "后端服务日志文件不存在: $LOGS_DIR/backend.log"
        fi
        ;;
    "web")
        if [[ -f "$LOGS_DIR/web.log" ]]; then
            $TAIL_CMD "$LOGS_DIR/web.log" | while IFS= read -r line; do
                format_log_line "web" "$line"
            done
        else
            echo "前端服务日志文件不存在: $LOGS_DIR/web.log"
        fi
        ;;
    "all"|*)
        # 合并所有日志文件
        LOG_FILES=()
        [[ -f "$LOGS_DIR/voice.log" ]] && LOG_FILES+=("$LOGS_DIR/voice.log")
        [[ -f "$LOGS_DIR/backend.log" ]] && LOG_FILES+=("$LOGS_DIR/backend.log")
        [[ -f "$LOGS_DIR/web.log" ]] && LOG_FILES+=("$LOGS_DIR/web.log")
        
        if [[ ${#LOG_FILES[@]} -eq 0 ]]; then
            echo "没有找到任何日志文件"
            exit 1
        fi
        
        if [[ "$FOLLOW" == "true" ]]; then
            # 实时跟踪多个文件
            tail -f -n "$TAIL_LINES" "${LOG_FILES[@]}" | while IFS= read -r line; do
                # 从 tail -f 的输出中提取文件名和内容
                if [[ "$line" =~ ^==\>.*voice\.log.*\<== ]]; then
                    continue
                elif [[ "$line" =~ ^==\>.*backend\.log.*\<== ]]; then
                    continue
                elif [[ "$line" =~ ^==\>.*web\.log.*\<== ]]; then
                    continue
                else
                    # 根据当前处理的文件判断组件类型
                    # 这里简化处理，实际可以通过更复杂的逻辑判断
                    format_log_line "mixed" "$line"
                fi
            done
        else
            # 显示历史日志
            for log_file in "${LOG_FILES[@]}"; do
                component=$(basename "$log_file" .log)
                echo -e "${PURPLE}=== $component ===${NC}"
                tail -n "$TAIL_LINES" "$log_file" | while IFS= read -r line; do
                    format_log_line "$component" "$line"
                done
                echo ""
            done
        fi
        ;;
esac
