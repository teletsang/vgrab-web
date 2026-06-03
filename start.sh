#!/bin/bash
# vgrab-web 一键启动（自动安装所有依赖）
# 任意设备运行此脚本即可

set -e

echo "🦐 vgrab-web 启动中..."

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "❌ 需要 Python 3.8+，请先安装"
    exit 1
fi

# 检查并安装 pip 依赖
echo "📦 检查 Python 依赖..."
python3 -m pip install --quiet --upgrade flask yt-dlp pywebview 2>/dev/null || \
python3 -m pip install --quiet --upgrade --user flask yt-dlp pywebview

# 检查并安装 ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo "📦 安装 ffmpeg..."
    if command -v brew &>/dev/null; then
        brew install ffmpeg
    elif command -v apt-get &>/dev/null; then
        sudo apt-get install -y ffmpeg
    elif command -v winget &>/dev/null; then
        winget install ffmpeg
    else
        echo "⚠️ 请手动安装 ffmpeg: https://ffmpeg.org/download.html"
    fi
fi

echo "✅ 依赖就绪，启动服务..."

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 启动（有 pywebview 就原生窗口，没有就浏览器）
if python3 -c "import webview" 2>/dev/null; then
    python3 native.py
else
    python3 app.py --port 9999 &
    sleep 2
    open "http://127.0.0.1:9999" 2>/dev/null || \
    xdg-open "http://127.0.0.1:9999" 2>/dev/null || \
    echo "🌐 打开浏览器访问: http://127.0.0.1:9999"
    wait
fi
