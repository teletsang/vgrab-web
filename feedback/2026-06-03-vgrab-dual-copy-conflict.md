# vgrab MCP 双副本冲突反馈报告

- **日期**: 2026-06-03 15:56
- **执行人**: 走地虾（OpenClaw 主会话）
- **背景**: 上一份报告 [`2026-06-03-vgrab-mcp-install-report.md`](./2026-06-03-vgrab-mcp-install-report.md) 提的两个改进点（stderr 透出 + 代理预检），老板已在 commit `6bee682` 修复。今次按预期重测时发现新代码**没生效**。本报告记录根因，**不修代码**，请老板拍板。
- **重要**：本次仅排查，未重启任何进程、未改任何文件、未动任何配置。

---

## 1. 现象

- 拉了 `eb5a766..6bee682`，本地 `downloader.py` ✅ 已是新代码（`_check_proxy`、`MAX_TAIL`、「代理不可达」提示均在）。
- mcporter 中 `vgrab` 注册路径 ✅ 指向知识库版：`/Users/mbp2026/.openclaw/workspace/openclaw-knowledge-vault/scripts/vgrab-web/mcp_server.py`。
- 重测同一 URL（`youtube.com/watch?v=mWBVkX1Shvw` + `socks5://127.0.0.1:7890`）。
- 期望：返回「代理不可达: socks5://127.0.0.1:7890 (connection refused)」（预检直接拦截，不会真的拉 yt-dlp）。
- 实际：仍返回 `下载失败 (exit 1)`，没有 stderr detail，也没有代理预检消息。

## 2. 根因 — 双副本冲突

| 维度 | 副本 A（install.sh 安装的） | 副本 B（知识库 git） |
|---|---|---|
| 路径 | `~/vgrab-web/` | `openclaw-knowledge-vault/scripts/vgrab-web/` |
| 是否 git 仓 | ❌ 否（install.sh 用 `mv` 落盘，无 `.git`） | ✅ 是 |
| 同步方式 | 无法 `git pull`，只能重跑 install.sh | `git pull` |
| 当前是否带新代码 | ❌ 否 | ✅ 是 |
| 入口 | 桌面 App「扒扒侠」(`~/Applications/扒扒侠.app/.../MacOS/vgrab`)，启动 `native.py` | `mcp_server.py` 自动 spawn `app.py` |

**关键事实**：

```
ps -p 15137 → STARTED Tue Jun 2 18:38:43 2026, command: python native.py
lsof -iTCP:9999 → PID 15137
```

桌面 App 自 6/2 18:38 一直在跑，**占着 9999 端口**。

`mcp_server.py:_ensure_backend()` 的逻辑是：

```python
try:
    _get("/api/status")   # 端口能通就直接返回 True
    return True
except ...:
    pass
# 否则才去 spawn app.py
```

→ 端口已通 → 直接复用 → **知识库版 app.py 永远没机会启动** → 新代码永远不生效。

## 3. install.sh 的设计缺陷（根因之根）

读 `scripts/vgrab-web/install.sh`，第 38–43 行：

```bash
INSTALL_DIR="$HOME/vgrab-web"
if [[ -d "$INSTALL_DIR/.git" ]]; then
    cd "$INSTALL_DIR" && git pull --rebase
elif [[ -d "$INSTALL_DIR" ]]; then
    echo "📂 目录已存在，跳过克隆"
else
    git clone --depth 1 ... /tmp/_vgrab_clone
    mv /tmp/_vgrab_clone/scripts/vgrab-web "$INSTALL_DIR"  # ← 这里
    rm -rf /tmp/_vgrab_clone
fi
```

`mv` 出来的目录**没有 `.git`** → 下次再跑 install.sh 走的是「目录已存在，跳过克隆」分支 → **永远停留在第一次安装的版本**，即使后续 `git pull` 了知识库也不会更新。

这就是「副本 A 永远旧」的结构性原因。

## 4. 给老板的方向选项（不擅自做）

### 🥇 方案 1：知识库版作为唯一源（推荐）

- 桌面 App 启动脚本 `~/Applications/扒扒侠.app/Contents/MacOS/vgrab` 中的 `cd $INSTALL_DIR` 改成 `cd <知识库路径>/scripts/vgrab-web`
- 或把 `~/vgrab-web` 整体替换成软链：`ln -s <知识库路径>/scripts/vgrab-web ~/vgrab-web`
- 同时改 `install.sh`：检测 `INSTALL_DIR` 是 `mv` 出来的旧目录时（无 .git），打印警告并 `exit 1`，引导用户手动迁移
- **优点**：单一权威源，`git pull` 即生效，不会再有"我改了 commit 没生效"的困惑
- **副作用**：桌面 App 之后跑的就是知识库版的 `native.py`，路径耦合到 `~/.openclaw/workspace/...`

### 🥈 方案 2：install.sh 改用 git clone

- `INSTALL_DIR` 直接 `git clone` 整仓 + sparse-checkout 只取 `scripts/vgrab-web/`
- 启动脚本前置 `git pull --quiet` 自动同步
- **优点**：保留双副本，但副本 A 可自更新
- **缺点**：每次启动多一次网络 IO；首次安装多 ~50MB（vault/raw 图片那一大坨）；要处理 `git pull` 失败时的降级

### 🥉 方案 3：mcp_server.py 不复用旧后端

- `_ensure_backend()` 增加版本握手：`/api/version` 不匹配就 kill 旧的、起新的
- **优点**：只动 MCP 一处，install/桌面 App 都不用改
- **缺点**：会把老板正在用的桌面 App 杀掉，体验糟糕

## 5. 当前可立即做的零改动验证（仅供参考，不擅自执行）

如果老板想**先确认 commit `6bee682` 的代码本身真的有效**（不解决双副本，只验代码）：

```
pkill -f "native.py"      # 临时停桌面 App
mcporter call vgrab.vgrab_status   # 让 mcp_server 拉起知识库版 app.py
mcporter call vgrab.vgrab_download url=... proxy=...  # 应看到「代理不可达: ...」
```

桌面 App 重新双击启动后会回到旧版，**结构问题不解决**，但能秒级验代码逻辑。

需要我做吗？等老板指示。

---
_Source: `scripts/vgrab-web/feedback/2026-06-03-vgrab-dual-copy-conflict.md`_
