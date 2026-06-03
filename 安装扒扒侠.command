#!/bin/bash
# ============================================================
# 扒扒侠 一键安装 (双击此文件即可)
# 安装完成后在 ~/Applications 中找到「扒扒侠」
# ============================================================
set -e

VERSION=$(cat "$(dirname "$0")/VERSION" 2>/dev/null || echo "1.1.0")
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/vgrab-web"
APP_NAME="扒扒侠"
APP_DIR="$HOME/Applications/${APP_NAME}.app"

# 颜色
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

# ============================================================
# 函数定义
# ============================================================

install_webview_app() {
    python3 -m pip install --quiet --break-system-packages pywebview 2>/dev/null || \
    python3 -m pip install --quiet pywebview 2>/dev/null || true

    rm -rf "$APP_DIR"
    mkdir -p "$APP_DIR/Contents/MacOS"
    mkdir -p "$APP_DIR/Contents/Resources"

    cat > "$APP_DIR/Contents/MacOS/launch" << WEBEOF
#!/bin/bash
if [[ -f /opt/homebrew/bin/brew ]]; then
    eval "\\\$(/opt/homebrew/bin/brew shellenv)"
elif [[ -f /usr/local/bin/brew ]]; then
    eval "\\\$(/usr/local/bin/brew shellenv)"
fi
export PATH="/opt/homebrew/bin:/usr/local/bin:\\\$PATH"
pkill -f "python3.*native.py" 2>/dev/null
pkill -f "python3.*app.py.*9999" 2>/dev/null
sleep 0.3
cd "$INSTALL_DIR"
exec python3 native.py
WEBEOF
    chmod +x "$APP_DIR/Contents/MacOS/launch"

    cat > "$APP_DIR/Contents/Info.plist" << PLIST2
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>com.vgrab.babaxia</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleExecutable</key>
    <string>launch</string>
    <key>CFBundleIconFile</key>
    <string>vgrab</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST2

    if [[ -f "$INSTALL_DIR/static/vgrab.icns" ]]; then
        cp "$INSTALL_DIR/static/vgrab.icns" "$APP_DIR/Contents/Resources/vgrab.icns"
    fi
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_DIR" 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} Web 版 App 已安装"
}

# ============================================================
# 主流程
# ============================================================

clear
echo ""
echo -e "${BOLD}🦐 ${APP_NAME} v${VERSION} 安装程序${NC}"
echo "============================================"
echo ""

# --- 检测 macOS ---
if [[ "$(uname)" != "Darwin" ]]; then
    echo -e "${RED}❌ 仅支持 macOS${NC}"
    read -p "按回车退出..."
    exit 1
fi

# --- [1/5] Xcode Command Line Tools ---
echo -e "${BLUE}[1/5]${NC} 检查 Xcode 命令行工具..."
if ! xcode-select -p &>/dev/null; then
    echo "  安装 Xcode 命令行工具（弹窗后点击「安装」）..."
    xcode-select --install
    echo ""
    echo -e "${BOLD}⚠️  请等待安装完成后，重新双击此文件。${NC}"
    echo ""
    read -p "按回车退出..."
    exit 0
fi
echo -e "  ${GREEN}✓${NC} 已安装"

# --- [2/5] Homebrew + 依赖 ---
echo -e "${BLUE}[2/5]${NC} 安装系统依赖..."

if ! command -v brew &>/dev/null; then
    echo "  安装 Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# 确保 brew 在 PATH 中
if [[ -f /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -f /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
fi

brew install ffmpeg yt-dlp 2>/dev/null || brew upgrade ffmpeg yt-dlp 2>/dev/null || true
echo -e "  ${GREEN}✓${NC} ffmpeg, yt-dlp 就绪"

# --- [3/5] Python 依赖 ---
echo -e "${BLUE}[3/5]${NC} 安装 Python 依赖..."
python3 -m pip install --quiet --break-system-packages flask yt-dlp 2>/dev/null || \
python3 -m pip install --quiet flask yt-dlp 2>/dev/null || true
echo -e "  ${GREEN}✓${NC} Python 包就绪"

# --- [4/5] 部署代码 ---
echo -e "${BLUE}[4/5]${NC} 部署项目代码..."

if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
    if [[ -d "$INSTALL_DIR" ]]; then
        echo "  更新 $INSTALL_DIR..."
        rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='_logs' --exclude='.git' \
            "$SCRIPT_DIR/" "$INSTALL_DIR/"
    else
        echo "  复制到 $INSTALL_DIR..."
        rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='_logs' --exclude='.git' \
            "$SCRIPT_DIR/" "$INSTALL_DIR/"
    fi
else
    echo "  已在目标目录"
fi
echo -e "  ${GREEN}✓${NC} 代码就绪"

# --- [5/5] 构建 App ---
echo -e "${BLUE}[5/5]${NC} 构建原生 App..."

mkdir -p "$HOME/Applications"
SWIFT_DIR="$INSTALL_DIR/native-app/BaBaXia"
BUILD_OK=false

if [[ -f "$SWIFT_DIR/Package.swift" ]] && command -v swift &>/dev/null; then
    echo "  编译 Swift App (首次约 1-2 分钟)..."
    cd "$SWIFT_DIR"

    if swift build -c release 2>&1 | tail -5; then
        BINARY="$(swift build -c release --show-bin-path)/BaBaXia"

        if [[ -f "$BINARY" ]]; then
            rm -rf "$APP_DIR"
            mkdir -p "$APP_DIR/Contents/MacOS"
            mkdir -p "$APP_DIR/Contents/Resources"

            # 复制编译产物
            cp "$BINARY" "$APP_DIR/Contents/MacOS/${APP_NAME}"

            # 启动脚本：先起后端再起 UI
            cat > "$APP_DIR/Contents/MacOS/launch" << 'LAUNCHER'
#!/bin/bash
DIR="$(dirname "$0")"

# PATH
if [[ -f /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -f /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
fi
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# 启动 Python 后端
BACKEND="$HOME/vgrab-web"
if [[ -f "$BACKEND/app.py" ]]; then
    pkill -f "python3.*app.py.*9999" 2>/dev/null || true
    sleep 0.3
    cd "$BACKEND"
    python3 app.py --port 9999 &>/dev/null &
fi

# 等后端就绪
for i in $(seq 1 30); do
    curl -s http://127.0.0.1:9999/api/status >/dev/null 2>&1 && break
    sleep 0.3
done

# 启动原生界面
exec "$DIR/扒扒侠"
LAUNCHER
            chmod +x "$APP_DIR/Contents/MacOS/launch"

            # Info.plist
            cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>com.vgrab.babaxia</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleExecutable</key>
    <string>launch</string>
    <key>CFBundleIconFile</key>
    <string>vgrab</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

            # 图标
            if [[ -f "$INSTALL_DIR/static/vgrab.icns" ]]; then
                cp "$INSTALL_DIR/static/vgrab.icns" "$APP_DIR/Contents/Resources/vgrab.icns"
            fi

            /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_DIR" 2>/dev/null || true
            BUILD_OK=true
            echo -e "  ${GREEN}✓${NC} Swift 原生版已安装"
        fi
    fi
fi

# 如果 Swift 编译失败，回退到 pywebview 版
if [[ "$BUILD_OK" == "false" ]]; then
    echo "  Swift 编译失败或不可用，使用 Web 版..."
    install_webview_app
fi

# --- 完成 ---
echo ""
echo "============================================"
echo -e "${GREEN}${BOLD}🎉 安装完成！${NC}"
echo ""
echo -e "  📱 App:     ${BOLD}~/Applications/${APP_NAME}.app${NC}"
echo -e "  📂 后端:    ~/vgrab-web"
echo -e "  📋 版本:    v${VERSION}"
echo ""
echo "  💡 首次设置（在 App 设置页）:"
echo "    LLM 地址: http://<局域网LLM主机>:8080"
echo "    代理:     socks5://127.0.0.1:7890 (如需翻墙)"
echo ""
echo -e "  ${BOLD}现在打开 ${APP_NAME}？ [Y/n]${NC}"
read -r answer
if [[ "$answer" != "n" && "$answer" != "N" ]]; then
    open "$APP_DIR"
fi
