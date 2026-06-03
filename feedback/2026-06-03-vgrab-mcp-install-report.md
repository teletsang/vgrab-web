# vgrab MCP Server 安装与首测反馈报告

- **日期**: 2026-06-03
- **执行人**: 走地虾（OpenClaw 主会话）
- **任务**: 从远端 `openclaw-knowledge-vault/scripts/vgrab-web/mcp_server.py` 安装 MCP，并做一次端到端验证
- **结论**: ✅ 安装成功，链路通；⚠️ 发现 1 个后端错误传递的可优化点

---

## 1. 安装结果

| 项 | 值 |
|---|---|
| 来源 commit | `06a461c feat(vgrab-web): 添加 MCP Server，Agent 装完即用` |
| 文件路径 | `/Users/mbp2026/.openclaw/workspace/openclaw-knowledge-vault/scripts/vgrab-web/mcp_server.py` |
| 注册位置 | `~/.mcporter/mcporter.json`（旧配置已自动备份为 `mcporter.json.bak.YYYYMMDD_HHMMSS`） |
| 注册方式 | stdio command：`python3 mcp_server.py` |
| 后端 | `app.py --port 9999`，由 `mcp_server.py` 在首次调用时自动 spawn |
| 后端版本 | v1.1.0 |
| 下载目录 | `~/Downloads/vgrab-web` |
| 依赖 | `deps_ok: true` |

`mcporter.json` 中新增的条目：

```json
"vgrab": {
  "command": "python3",
  "args": ["/Users/mbp2026/.openclaw/workspace/openclaw-knowledge-vault/scripts/vgrab-web/mcp_server.py"],
  "description": "vgrab 视频下载/转录/分析/录制 (mcp_server.py from openclaw-knowledge-vault)"
}
```

## 2. 暴露的 MCP 工具

通过 `mcporter list vgrab --schema` 验证，5 个工具全部正确加载：

| Tool | 入参 | 说明 |
|---|---|---|
| `vgrab_download` | `url` (必), `audio_only?`, `proxy?`, `output_dir?` | 下载视频/音频，1000+ 平台 |
| `vgrab_transcribe` | `video_path` (必) | Whisper 转录字幕 |
| `vgrab_analyze` | `video_path` (必), `mode?`(summary/visual/tutorial/creative) | LLM 视频内容分析 |
| `vgrab_record` | `stream_url` (必), `title?`, `max_minutes?` | 录直播流 |
| `vgrab_status` | — | 后端健康检查 |

## 3. 端到端验证

### 3.1 状态检查 — ✅ 通过

```
mcporter call vgrab.vgrab_status
→ {"status":"online","version":"1.1.0","download_dir":".../Downloads/vgrab-web","deps_ok":true}
```

确认 stdio MCP → app.py 自动拉起 → HTTP 9999 → 返回 JSON 整条链路正常。

### 3.2 下载测试 — ⚠️ 因代理未启动失败（非 vgrab 问题）

测试 URL：`https://www.youtube.com/watch?v=mWBVkX1Shvw`，代理 `socks5://127.0.0.1:7890`。

vgrab 返回：

```json
{"status": "error", "message": "下载失败 (exit 1)"}
```

后端 `/api/tasks` 也只记录 `progress: "下载失败 (exit 1)"`。

**进一步排查**：直接命令行跑 `yt-dlp --proxy socks5://127.0.0.1:7890`，得到真正的根因：

```
ERROR: [youtube] mWBVkX1Shvw: Unable to download API page:
  [Errno 61] Connection refused
```

`lsof -iTCP:7890 -sTCP:LISTEN` 无返回 → 7890 端口空，本机当时没开 Clash/Surge/V2Ray，与 vgrab 本身无关。

## 4. 发现的改进点（给 vgrab-web）

### 🔴 错误信息丢失，定位代价高

- **现象**：yt-dlp 子进程退出码 ≠ 0 时，vgrab 只返回 `"下载失败 (exit 1)"`，**stderr 完全被吞**。Agent / 用户拿不到根因，只能再去命令行手跑一次 yt-dlp 才能定位。
- **建议修法**（按改动量排序）：
  1. **最低成本**：把 yt-dlp 子进程的 `stderr` 末尾 N 行（如 30 行）跟 exit code 一起塞进 task progress / API response，比如 `下载失败 (exit 1): ERROR: ... Connection refused`
  2. **进阶**：识别常见错误模式打 tag —— `proxy_unreachable` / `geo_blocked` / `private_video` / `404` / `network_timeout`，前端/Agent 可以基于 tag 给出针对性提示
  3. **最佳**：保留每个任务最近一次完整 stderr 到 `~/Downloads/vgrab-web/.logs/<task_id>.log`，前端展示「查看完整日志」入口

### 🟡 代理可达性预检

- 当前 `proxy` 参数仅透传给 yt-dlp。建议在 download 入口加一个 ~200ms 的 TCP `connect()` 预检，代理不通直接返回 `proxy_unreachable: 127.0.0.1:7890 connection refused`，省一次 yt-dlp 启动 + 慢失败时间。

### 🟢 README 增加 MCP 安装小节

- 当前 `mcp_server.py` 文件头注释写得清楚，但 `README.md` 完全没提 MCP。建议补一段 30 行内的「Agent / MCP 集成」章节，给出 mcporter / Claude Desktop / Cursor 各自的配置示例。

## 5. 后续待办

- [ ] 老板开代理后，重跑一次 YouTube 下载（同一 URL `mWBVkX1Shvw`）确认完整下载链路
- [ ] 再用一个不需要代理的源（B 站 / 抖音）跑一次，覆盖国内 fallback 路径（特别是 `features/download/extractors/douyin.py` 那条 iesdouyin 兜底逻辑）
- [ ] 如老板同意「改进点」中的改法，可在 `openclaw-knowledge-vault/scripts/vgrab-web/` 内提一个小 PR：把 stderr tail 塞进 task progress —— 改动估计 < 30 行

---
_Source: `scripts/vgrab-web/feedback/2026-06-03-vgrab-mcp-install-report.md`_
