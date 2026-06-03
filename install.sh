#!/bin/bash
# vgrab-web macOS 一键安装
# 装完双击 ~/Applications/vgrab-web.app 即可使用
# 用法: curl -fsSL <url> | bash
set -e

echo ""
echo "🦐 vgrab-web 一键安装"
echo "====================="
echo ""

# --- [1] Homebrew ---
if ! command -v brew &>/dev/null; then
    echo "📦 安装 Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    [[ -f /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# --- [2] 依赖 ---
echo "📦 安装依赖..."
brew install yt-dlp ffmpeg python3 2>/dev/null || brew upgrade yt-dlp ffmpeg 2>/dev/null || true

echo "📦 安装 Python 包..."
python3 -m pip install --quiet --break-system-packages flask pywebview yt-dlp 2>/dev/null || \
python3 -m pip install --quiet flask pywebview yt-dlp 2>/dev/null || true

# --- [3] 拉代码 ---
INSTALL_DIR="$HOME/vgrab-web"
REPO_URL="https://github.com/teletsang/vgrab-web.git"

if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "📂 更新代码..."
    cd "$INSTALL_DIR" && git pull --rebase 2>/dev/null || true
elif [[ -d "$INSTALL_DIR" ]]; then
    # 旧版 install 没有 .git，迁移为 git 仓库
    echo "📂 升级为 git 仓库（旧安装迁移）..."
    mv "$INSTALL_DIR" "$INSTALL_DIR.old"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
    echo "  旧版备份在 ~/vgrab-web.old（可删除）"
else
    echo "📂 下载 vgrab-web..."
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

# --- [4] 打包 macOS App ---
echo "🎨 创建 App..."
APP_DIR="$HOME/Applications/扒扒侠.app"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Info.plist
cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>扒扒侠</string>
    <key>CFBundleDisplayName</key>
    <string>扒扒侠</string>
    <key>CFBundleIdentifier</key>
    <string>com.vgrab.web</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>vgrab</string>
    <key>CFBundleIconFile</key>
    <string>vgrab</string>
    <key>LSArchitecturePriority</key>
    <array>
        <string>arm64</string>
        <string>x86_64</string>
    </array>
</dict>
</plist>
PLIST

# 启动脚本 (强制原生窗口)
cat > "$APP_DIR/Contents/MacOS/vgrab" << EOF
#!/bin/bash
# Intel + Apple Silicon 兼容
if [[ -f /opt/homebrew/bin/brew ]]; then
    eval "\$(/opt/homebrew/bin/brew shellenv)"
elif [[ -f /usr/local/bin/brew ]]; then
    eval "\$(/usr/local/bin/brew shellenv)"
fi
export PATH="/opt/homebrew/bin:/usr/local/bin:\$(brew --prefix python3 2>/dev/null)/bin:\$PATH"
pkill -f "python3.*native.py" 2>/dev/null
pkill -f "python3.*app.py.*9999" 2>/dev/null
sleep 0.3
cd "$INSTALL_DIR"
exec python3 native.py
EOF
chmod +x "$APP_DIR/Contents/MacOS/vgrab"

# 图标
if [[ -f "$INSTALL_DIR/static/vgrab.icns" ]]; then
    cp "$INSTALL_DIR/static/vgrab.icns" "$APP_DIR/Contents/Resources/vgrab.icns"
fi

# 刷新图标缓存
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_DIR" 2>/dev/null || true
killall Finder 2>/dev/null || true

echo ""
echo "=== 🎉 安装完成 ==="
echo ""
echo "  📱 App 位置: ~/Applications/vgrab-web.app"
echo "  双击启动即可！"
echo ""
echo "  首次使用设置:"
echo "    LLM 地址: http://TELEZENG-MC4.local:8080"
echo "    API Key:  (问老板要)"
echo "    代理:     socks5://127.0.0.1:7890 (如果要下YouTube)"
echo ""
