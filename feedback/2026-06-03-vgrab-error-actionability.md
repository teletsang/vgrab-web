# vgrab 错误信息可读但不可执行 — UX 反馈

- **日期**: 2026-06-03 17:12
- **执行人**: 走地虾（OpenClaw 主会话）
- **背景**: 双副本冲突解决（[`2026-06-03-vgrab-dual-copy-conflict.md`](./2026-06-03-vgrab-dual-copy-conflict.md)）+ 一行装命令上线后，老板让我抓 `https://www.youtube.com/watch?v=mWBVkX1Shvw`。
- **结论**: ✅ vgrab 行为符合预期；⚠️ 但「错误信息够清楚 ≠ 用户/Agent 知道怎么办」，本报告提一个**轻量的恢复 Hint 设计**。
- **重要**：本次仅排查 + 写报告，未改代码、未改进程、未改配置。

---

## 1. 现象

执行：

```
mcporter call vgrab.vgrab_download \
  url=https://www.youtube.com/watch?v=mWBVkX1Shvw \
  proxy=socks5://127.0.0.1:7890
```

返回：

```json
{"status": "error", "message": "代理不可达: socks5://127.0.0.1:7890 (connection refused)"}
```

→ 老板上一次修复（commit `6bee682`）的代理预检完美生效，错误信息一行说清。

但 Agent 卡在这步，**只能反过来问老板**「代理 App 是不是没开？端口是不是变了？」—— **错误信息可读，但不可执行**。

## 2. 根因（不是 bug，是 UX 缺口）

vgrab 在两个层级提供错误：

- **L1：原始错误**——「代理不可达 / 连接被拒」 ← 已经做得很好
- **L2：恢复指引**——「下一步怎么办」← **目前缺失**

对人类用户：可能能猜到去开 Clash。
对 LLM Agent：没有 hint 就只能瞎猜，最终回退成"问用户"，体验断层。

## 3. 建议改进 — 错误响应增加 `hint` / `next_actions` 字段

### 3.1 数据结构（后端 → MCP 透传）

当前：

```json
{"status": "error", "message": "代理不可达: socks5://127.0.0.1:7890 (connection refused)"}
```

建议扩展（**完全向后兼容**，老 client 仍只读 `message`）：

```json
{
  "status": "error",
  "error_code": "proxy_unreachable",
  "message": "代理不可达: socks5://127.0.0.1:7890 (connection refused)",
  "hints": [
    "检查 Clash / Surge / V2Ray 是否启动（菜单栏图标）",
    "确认监听端口与 proxy 参数一致（默认 7890）",
    "或换不需代理的链接：B站 / 抖音 / 小红书 / 微博"
  ],
  "fallback": {
    "recommended": "retry_without_proxy",
    "applicable_when": "url 域名不在 GFW 名单内"
  }
}
```

### 3.2 错误码字典（建议）

| `error_code` | 触发条件 | 推荐 hints |
|---|---|---|
| `proxy_unreachable` | 代理预检失败 | 检查代理 App / 端口 / 改用直连源 |
| `geo_blocked` | yt-dlp 报 "not available in your country" | 切代理节点 / 换 IP 池 |
| `private_video` | 403/Login required | 提供 cookie 文件 |
| `video_not_found` | 404 / video unavailable | 检查 URL，可能已删 |
| `network_timeout` | 超时 | 重试 / 换网络 |
| `format_unavailable` | 指定 format 不存在 | 列出可用 format / 用 `bestvideo+bestaudio` |
| `unknown_extractor` | 不在 yt-dlp 1000+ 站内 | 提示用 ffmpeg 直录 / 浏览器手抓 |

错误码识别可以放在 `_do_download` 失败分支里做正则匹配（`stderr` 里关键词），改动在 30 行内。

### 3.3 实现位置

`scripts/features/download/downloader.py` 已有 `error_detail` 提取逻辑（commit `6bee682`），在那个 if 分支下加：

```python
err_lower = error_detail.lower()
if "connection refused" in err_lower and "proxy" in (cmd_str := " ".join(cmd)).lower():
    error_code = "proxy_unreachable"
    hints = [...]
elif "private video" in err_lower or "login required" in err_lower:
    error_code = "private_video"
    hints = [...]
# ...
tasks.update(task_id, status="error",
             progress=f"...",
             error_code=error_code,  # 新增
             hints=hints)             # 新增
```

`/api/tasks` 和 MCP 返回结构里把 `error_code` / `hints` 一起带出来。

### 3.4 MCP tool description 同步

`mcp_server.py` 里 `vgrab_download` 的 description 末尾加一句：

```
失败时返回的 error_code 和 hints 字段可指导后续操作。
常见 error_code: proxy_unreachable / geo_blocked / private_video / video_not_found / network_timeout
```

→ Agent 在 schema 阶段就知道遇到错误该往哪看。

## 4. 其他想到但优先级更低的点

- 🟡 **代理预检结果缓存**：同一 proxy 在 30s 内连续调用，预检结果可复用，省掉重复 TCP 握手（高频调用场景）
- 🟡 **`vgrab_status` 可选返回当前可用代理列表**：扫一下 7890/1087/1080，告诉 Agent 哪个口在听 → 启动阶段 Agent 就能挑代理而不是猜
- 🟢 **README 加一段「Agent 错误处理范式」**：演示拿到 error 后怎么 graceful retry / fallback

## 5. 本次 YouTube 任务的处理建议

老板已经 acknowledge「报告吧」，所以我**没有继续骚扰要代理端口或换链接**。
当代理就绪后，重发命令完整链路应该一把过：

```
mcporter call vgrab.vgrab_download \
  url=https://www.youtube.com/watch?v=mWBVkX1Shvw \
  proxy=socks5://127.0.0.1:<实际端口>
```

---

## TL;DR

> vgrab 的错误**够清楚了**，但**对 Agent 不够友好**——只说"哪儿坏了"，没说"该怎么办"。
> 加 4 字段（`error_code` / `hints` / 可选 `fallback` / tool description 提示），就能让 Agent 自己处理常见错误，不用每次都反过来问人。
> 改动估计 < 50 行，向后兼容。

---
_Source: `feedback/2026-06-03-vgrab-error-actionability.md` (repo: github.com/teletsang/vgrab-web)_
