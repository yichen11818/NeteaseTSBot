#!/bin/bash

# ============================================
# random_play.sh
# 随机遍历 old_music.txt 全部歌曲，逐首调用 play.sh -n 执行
# 用法：
#   ./random_play.sh          # 随机遍历全部一次
#   ./random_play.sh -l       # 无限循环随机遍历
#   ./random_play.sh -c 2     # 随机遍历 2 轮
# ============================================

MUSIC_FILE="jam_style.txt"
PLAY_SCRIPT="./play.sh"

# ---------- 参数解析 ----------
LOOP=1
while getopts "lc:h" opt; do
    case $opt in
        l) LOOP=0 ;;          # 0 = 无限循环
        c) LOOP="$OPTARG" ;;   # 指定轮数
        h)
            echo "用法: $0 [-l | -c 轮数]"
            echo "  -l      无限循环随机播放"
            echo "  -c N    随机播放 N 轮"
            echo "  (无参数) 随机播放 1 轮"
            exit 0
            ;;
        *) echo "未知参数: $opt"; exit 1 ;;
    esac
done

# ---------- 前置检查 ----------
if [ ! -f "$MUSIC_FILE" ]; then
    echo "❌ 找不到歌单文件: $MUSIC_FILE"
    exit 1
fi

if [ ! -x "$PLAY_SCRIPT" ]; then
    echo "⚠️  $PLAY_SCRIPT 不可执行，仍尝试调用..."
fi

# ---------- 读取歌单（整行保留，不拆空格）----------
mapfile -t ALL_SONGS < <(grep -v '^[[:space:]]*$' "$MUSIC_FILE")
TOTAL=${#ALL_SONGS[@]}

if [ "$TOTAL" -eq 0 ]; then
    echo "❌ 歌单为空: $MUSIC_FILE"
    exit 1
fi

echo "🎵 歌单共 $TOTAL 首"
echo "========================================"

# ---------- 核心：随机遍历播放 ----------
round=0
while true; do
    round=$((round + 1))

    # 有限轮数模式：轮数用完则退出
    if [ "$LOOP" -gt 0 ] 2>/dev/null; then
        if [ "$round" -gt "$LOOP" ]; then
            break
        fi
    fi

    echo ""
    echo "🔀 第 $round 轮 · 开始随机遍历 $TOTAL 首..."
    echo "----------------------------------------"

    # 生成随机排列的索引序列（保持每行的完整性）
    indices=$(seq 0 $((TOTAL - 1)) | shuf)

    idx=0
    for i in $indices; do
        idx=$((idx + 1))
        song="${ALL_SONGS[$i]}"
        echo ""
        echo "▶️  [$idx/$TOTAL] $song"
        "$PLAY_SCRIPT" -n "$song"
        rc=$?
        if [ $rc -eq 0 ]; then
            echo "✅ 完成"
        else
            echo "⚠️  退出码: $rc"
        fi
    done

    echo ""
    echo "----------------------------------------"
    echo "🏁 第 $round 轮 · 全部 $TOTAL 首播放完毕"

    # 无限循环时稍作间隔
    if [ "$LOOP" -eq 0 ] 2>/dev/null; then
        echo "⏳ 3 秒后开始下一轮..."
        sleep 3
    fi
done

echo ""
echo "🎶 全部播放结束"

