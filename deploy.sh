#!/bin/bash
# vgrab-web 一键部署脚本
# 在任何 macOS (Apple Silicon) 设备上运行即可

set -e

echo "=== vgrab-web 部署 ==="

# 检测系统
if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ 目前仅支持 macOS"
    exit 1
fi

# 依赖检查 & 安装
echo ""
echo "[1/4] 检查依赖..."

# Homebrew
if ! command -v brew &>/dev/null; then
    echo "  安装 Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo "  安装 ffmpeg..."
    brew install ffmpeg
fi

# yt-dlp
if ! command -v yt-dlp &>/dev/null; then
    echo "  安装 yt-dlp..."
    brew install yt-dlp
fi

# Python 包
echo ""
echo "[2/4] 安装 Python 依赖..."
/usr/bin/python3 -m pip install --user --quiet flask pywebview yt-dlp mlx-whisper 2>/dev/null || {
    # 如果 --user 失败，试 pip3
    pip3 install flask pywebview yt-dlp mlx-whisper
}

# 定位代码目录
echo ""
echo "[3/4] 定位代码..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -f "$SCRIPT_DIR/app.py" ]]; then
    # 可能从别的地方运行的
    echo "  请在 vgrab-web 目录下运行此脚本"
    echo "  或者: cd /path/to/openclaw-knowledge-vault/scripts/vgrab-web && ./deploy.sh"
    exit 1
fi

# 创建 .app bundle
echo ""
echo "[4/4] 创建 macOS App..."
APP_DIR="$HOME/Applications/vgrab-web.app"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>vgrab-web</string>
    <key>CFBundleDisplayName</key>
    <string>vgrab-web</string>
    <key>CFBundleIdentifier</key>
    <string>com.vgrab.web</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>vgrab-web</string>
    <key>CFBundleIconFile</key>
    <string>vgrab</string>
    <key>LSArchitecturePriority</key>
    <array>
        <string>arm64</string>
    </array>
</dict>
</plist>
PLIST

cat > "$APP_DIR/Contents/MacOS/vgrab-web" << EOF
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:\$HOME/Library/Python/3.9/bin:\$PATH"
pkill -f "python3.*native.py" 2>/dev/null
pkill -f "python3.*app.py.*9999" 2>/dev/null
sleep 0.3
cd "$SCRIPT_DIR"
exec /usr/bin/python3 native.py
EOF
chmod +x "$APP_DIR/Contents/MacOS/vgrab-web"

# 复制图标
cp "$SCRIPT_DIR/static/vgrab.icns" "$APP_DIR/Contents/Resources/vgrab.icns" 2>/dev/null || true

echo ""
echo "=== 部署完成 ==="
echo ""
echo "  App 位置: ~/Applications/vgrab-web.app"
echo "  双击启动或: open ~/Applications/vgrab-web.app"
echo ""
echo "  注意事项:"
echo "  - YouTube 下载需给 Python 「完全磁盘访问」权限"
echo "    系统设置 → 隐私与安全 → 完全磁盘访问 → 添加 /usr/bin/python3"
echo "  - Whisper 首次运行会下载模型 (~1.5GB)"
echo "  - 分析功能需要本地 LLM (默认 http://127.0.0.1:8080)"
echo ""
