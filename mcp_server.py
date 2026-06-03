#!/usr/bin/env python3
"""
vgrab MCP Server — 让任何 AI Agent 自动获得视频下载/转录/分析能力

安装后 Agent 会自动看到以下工具:
  - vgrab_download: 下载视频
  - vgrab_transcribe: 转录音频/视频为文字
  - vgrab_analyze: AI 分析视频内容
  - vgrab_record: 录制直播流
  - vgrab_status: 检查服务状态
"""
import json
import sys
import time
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = "http://127.0.0.1:9999"
VGRAB_DIR = Path(__file__).parent


# ============================================================
# HTTP helpers
# ============================================================

def _get(path):
    url = BASE_URL + path
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(path, data):
    url = BASE_URL + path
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ensure_backend():
    """确保后端在运行，如果没运行则自动启动"""
    try:
        _get("/api/status")
        return True
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        pass

    # 自动启动后端
    app_py = VGRAB_DIR / "app.py"
    if not app_py.exists():
        return False

    subprocess.Popen(
        [sys.executable, str(app_py), "--port", "9999"],
        cwd=str(VGRAB_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 等待启动
    for _ in range(20):
        time.sleep(0.5)
        try:
            _get("/api/status")
            return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            pass
    return False


def _wait_task(poll_path, active_statuses=None, interval=2, timeout=1200):
    """轮询等待任务完成"""
    if active_statuses is None:
        active_statuses = ["queued", "downloading", "analyzing", "transcribing", "recording", "organizing", "stopping"]

    start = time.time()
    while time.time() - start < timeout:
        data = _get(poll_path)
        status = data.get("status", "")
        if status not in active_statuses:
            return data
        time.sleep(interval)

    return {"status": "error", "progress": "超时"}


# ============================================================
# Tool implementations
# ============================================================

def tool_download(url, audio_only=False, proxy=None, output_dir=None):
    """下载视频/音频"""
    if not _ensure_backend():
        return {"error": "vgrab 后端启动失败"}

    options = {}
    if audio_only:
        options["audio_only"] = True
    if proxy:
        options["proxy"] = proxy
    if output_dir:
        options["output_dir"] = output_dir

    result = _post("/api/download", {"url": url, "options": options})
    if "error" in result:
        return result

    task_id = result["task_id"]
    data = _wait_task(f"/api/task/{task_id}")

    if data.get("status") == "done":
        files = data.get("files", [])
        return {
            "status": "success",
            "title": data.get("title", ""),
            "files": [{"name": f["name"], "path": f.get("path", ""), "size": f.get("size", 0)} for f in files]
        }
    else:
        return {"status": "error", "message": data.get("progress", "下载失败")}


def tool_transcribe(video_path):
    """转录视频/音频为文字"""
    if not _ensure_backend():
        return {"error": "vgrab 后端启动失败"}

    result = _post("/api/transcribe", {"video_path": video_path, "settings": {}})
    if "error" in result:
        return result

    data = _wait_task(f"/api/transcribe/{result['transcribe_id']}",
                      active_statuses=["transcribing"], interval=3)

    if data.get("status") == "done":
        return {"status": "success", "text": data.get("result", "")}
    else:
        return {"status": "error", "message": data.get("progress", "转录失败")}


def tool_analyze(video_path, mode="summary"):
    """AI 分析视频内容"""
    if not _ensure_backend():
        return {"error": "vgrab 后端启动失败"}

    settings = {"mode": mode}
    result = _post("/api/analyze", {"video_path": video_path, "settings": settings})
    if "error" in result:
        return result

    data = _wait_task(f"/api/analyze/{result['analyze_id']}",
                      active_statuses=["analyzing"], interval=3)

    if data.get("status") == "done":
        return {"status": "success", "analysis": data.get("result", "")}
    else:
        return {"status": "error", "message": data.get("progress", "分析失败")}


def tool_record(stream_url, title="直播录制", max_minutes=0):
    """录制直播流"""
    if not _ensure_backend():
        return {"error": "vgrab 后端启动失败"}

    settings = {"title": title}
    if max_minutes > 0:
        settings["max_duration"] = max_minutes * 60

    result = _post("/api/record", {"url": stream_url, "settings": settings})
    if "error" in result:
        return result

    data = _wait_task(f"/api/record/{result['live_id']}",
                      active_statuses=["recording", "stopping"], interval=5)

    if data.get("status") == "done":
        return {"status": "success", "file_path": data.get("file_path", ""), "file_size": data.get("file_size", 0)}
    else:
        return {"status": "error", "message": data.get("progress", "录制失败")}


def tool_status():
    """检查 vgrab 服务状态"""
    if not _ensure_backend():
        return {"status": "offline", "message": "后端未运行且无法自动启动"}
    data = _get("/api/status")
    return {
        "status": "online",
        "version": data.get("version", "unknown"),
        "download_dir": data.get("download_dir", ""),
        "deps_ok": data.get("ok", False),
        "missing_deps": data.get("missing_deps", []),
    }


# ============================================================
# MCP Protocol (JSON-RPC over stdio)
# ============================================================

TOOLS = [
    {
        "name": "vgrab_download",
        "description": "下载视频或音频。支持 YouTube、B站、抖音、Twitter/X 等 1000+ 平台。返回下载文件的路径。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "视频链接 (http/https)"},
                "audio_only": {"type": "boolean", "description": "仅下载音频 (MP3)", "default": False},
                "proxy": {"type": "string", "description": "代理地址，如 socks5://127.0.0.1:7890"},
                "output_dir": {"type": "string", "description": "指定输出目录"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "vgrab_transcribe",
        "description": "将视频/音频转录为文字（使用 Whisper）。返回完整转录文本和时间轴。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_path": {"type": "string", "description": "视频或音频文件的绝对路径"},
            },
            "required": ["video_path"],
        },
    },
    {
        "name": "vgrab_analyze",
        "description": "AI 分析视频内容。提取关键帧并用 LLM 生成分析报告。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_path": {"type": "string", "description": "视频文件的绝对路径"},
                "mode": {
                    "type": "string",
                    "description": "分析模式",
                    "enum": ["summary", "visual", "tutorial", "creative"],
                    "default": "summary",
                },
            },
            "required": ["video_path"],
        },
    },
    {
        "name": "vgrab_record",
        "description": "录制直播流。支持 HLS/RTMP/FLV 等流格式。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stream_url": {"type": "string", "description": "直播流地址"},
                "title": {"type": "string", "description": "录制标题", "default": "直播录制"},
                "max_minutes": {"type": "integer", "description": "最大录制时长(分钟)，0=不限制", "default": 0},
            },
            "required": ["stream_url"],
        },
    },
    {
        "name": "vgrab_status",
        "description": "检查 vgrab 视频工具的运行状态、版本和可用性。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def handle_request(request):
    """处理 MCP JSON-RPC 请求"""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "vgrab",
                    "version": "1.1.0",
                },
            },
        }

    elif method == "notifications/initialized":
        return None  # 通知，不回复

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            if tool_name == "vgrab_download":
                result = tool_download(
                    url=arguments["url"],
                    audio_only=arguments.get("audio_only", False),
                    proxy=arguments.get("proxy"),
                    output_dir=arguments.get("output_dir"),
                )
            elif tool_name == "vgrab_transcribe":
                result = tool_transcribe(video_path=arguments["video_path"])
            elif tool_name == "vgrab_analyze":
                result = tool_analyze(
                    video_path=arguments["video_path"],
                    mode=arguments.get("mode", "summary"),
                )
            elif tool_name == "vgrab_record":
                result = tool_record(
                    stream_url=arguments["stream_url"],
                    title=arguments.get("title", "直播录制"),
                    max_minutes=arguments.get("max_minutes", 0),
                )
            elif tool_name == "vgrab_status":
                result = tool_status()
            else:
                result = {"error": f"未知工具: {tool_name}"}

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
                },
            }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(e)}, ensure_ascii=False)}],
                    "isError": True,
                },
            }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def main():
    """MCP stdio 主循环"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)

        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
