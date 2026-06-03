"""下载模块 — 独立于分析，只管下载"""
import os
import re
import subprocess
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import DOWNLOAD_DIR, MAX_CONCURRENT_DOWNLOADS
from core.logger import get_logger
from core.task_store import TaskStore

logger = get_logger("download")

# 任务存储（线程安全、自动清理）
tasks = TaskStore("download")

# 线程池（限制最大并发下载数）
_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS, thread_name_prefix="dl")


def check_deps() -> list:
    missing = []
    if not shutil.which("yt-dlp"):
        missing.append("yt-dlp")
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    return missing


def create_task(url: str, options: dict) -> str:
    task_id = str(uuid.uuid4())[:8]
    tasks.put(task_id, {
        "id": task_id,
        "url": url,
        "title": url,
        "status": "queued",
        "progress": "排队中...",
        "percent": 0,
        "files": [],
        "created_at": datetime.now().isoformat(),
    })
    _executor.submit(_do_download, task_id, url, options)
    logger.info(f"任务创建: {task_id} -> {url[:80]}")
    return task_id


def get_task(task_id: str) -> Optional[dict]:
    return tasks.get(task_id)


def get_all_tasks() -> list:
    return tasks.get_all()


def _do_download(task_id: str, url: str, options: dict):
    tasks.update(task_id, status="downloading", progress="开始下载...")

    custom_dir = options.get("output_dir")
    if custom_dir:
        output_dir = Path(custom_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = DOWNLOAD_DIR / task_id
    output_dir.mkdir(parents=True, exist_ok=True)

    proxy = options.get("proxy")
    audio_only = options.get("audio_only", False)
    subs = options.get("subs", False)
    format_id = options.get("format", "bestvideo+bestaudio/best")

    # 代理预检：快速判断代理是否可达
    if proxy and not _check_proxy(proxy):
        tasks.update(task_id, status="error",
                     progress=f"代理不可达: {proxy} (connection refused)",
                     error_code="proxy_unreachable",
                     hints=[
                         "检查代理 App 是否启动（Clash/Surge/V2Ray 等菜单栏图标）",
                         f"确认代理监听端口与参数一致: {proxy}",
                         "或去掉 proxy 参数，直连下载（B站/抖音/小红书等国内源不需要代理）",
                     ])
        logger.warning(f"代理预检失败: {task_id}, proxy={proxy}")
        return

    cmd = ["yt-dlp"]
    cmd += ["-o", str(output_dir / "%(title)s.%(ext)s")]
    cmd += ["--newline"]

    if audio_only:
        cmd += ["-x", "--audio-format", "mp3"]
    else:
        cmd += ["-f", format_id, "--merge-output-format", "mp4"]

    if subs:
        cmd += ["--write-auto-sub", "--sub-lang", "zh-Hans,en,ja", "--embed-subs"]
    if proxy:
        cmd += ["--proxy", proxy]

    # Cookie 策略：直接读 Chrome（需要「完全磁盘访问」权限）
    cmd += ["--cookies-from-browser", "chrome"]

    cmd += ["--no-playlist", "--concurrent-fragments", "8", "--retries", "5",
            "--no-overwrites", url]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)

        # 保留最后 N 行输出，用于失败时提供错误详情
        last_lines: list = []
        MAX_TAIL = 20

        for line in proc.stdout:
            line = line.strip()
            if line:
                tasks.update(task_id, progress=line)
                match = re.search(r'(\d+\.?\d*)%', line)
                if match:
                    tasks.update(task_id, percent=float(match.group(1)))
                # 保留尾部用于错误诊断
                last_lines.append(line)
                if len(last_lines) > MAX_TAIL:
                    last_lines.pop(0)

        proc.wait()

        if proc.returncode == 0:
            files = list(output_dir.iterdir())
            files = [f for f in files if not f.name.startswith('.')]
            tasks.update(
                task_id,
                status="done",
                progress="下载完成",
                percent=100,
                files=[{"name": f.name, "size": f.stat().st_size, "path": str(f)} for f in files],
            )
            logger.info(f"下载完成: {task_id}")
        else:
            # 提取错误信息（ERROR 行优先，否则取最后几行）
            error_lines = [l for l in last_lines if "ERROR" in l.upper()]
            error_detail = error_lines[-1] if error_lines else (last_lines[-1] if last_lines else "未知错误")
            # 截断过长的错误信息
            error_detail = error_detail[:300]

            # 识别错误类型，生成可执行的恢复建议
            error_code, hints = _classify_error(error_detail, proxy)

            # 尝试 ffmpeg 流录制
            stream_patterns = ['.m3u8', '.mpd', 'rtmp://', 'rtsp://']
            if any(p in url.lower() for p in stream_patterns):
                tasks.update(task_id, progress="yt-dlp 失败，切换 ffmpeg...")
                _try_ffmpeg(task_id, url, output_dir, proxy)
            else:
                tasks.update(task_id, status="error",
                             progress=f"下载失败 (exit {proc.returncode}): {error_detail}",
                             error_code=error_code,
                             hints=hints)
                logger.warning(f"下载失败: {task_id}, code={error_code}, detail={error_detail}")

    except Exception as e:
        tasks.update(task_id, status="error", progress=f"异常: {str(e)[:200]}")
        logger.error(f"下载异常: {task_id}", exc_info=True)


def _try_ffmpeg(task_id: str, url: str, output_dir: Path, proxy: Optional[str]):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"stream_{timestamp}.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-headers", f"Referer: {url}\r\nUser-Agent: Mozilla/5.0\r\n",
        "-i", url, "-c", "copy", "-t", "7200",
        str(output_file)
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=7200)
        if proc.returncode == 0 and output_file.exists() and output_file.stat().st_size > 0:
            tasks.update(
                task_id,
                status="done",
                progress="流录制完成",
                percent=100,
                files=[{"name": output_file.name, "size": output_file.stat().st_size, "path": str(output_file)}],
            )
            logger.info(f"ffmpeg 流录制完成: {task_id}")
        else:
            tasks.update(task_id, status="error", progress="ffmpeg 流录制也失败了")
            logger.warning(f"ffmpeg 流录制失败: {task_id}")
    except Exception as e:
        tasks.update(task_id, status="error", progress=f"ffmpeg 异常: {str(e)[:200]}")
        logger.error(f"ffmpeg 异常: {task_id}", exc_info=True)


def _check_proxy(proxy: str) -> bool:
    """快速 TCP 预检代理是否可达（<500ms）"""
    import socket
    import re as _re
    # 解析 socks5://host:port 或 http://host:port
    m = _re.search(r'://([^:/]+):(\d+)', proxy)
    if not m:
        return True  # 格式不标准，不拦截，让 yt-dlp 自己报错
    host, port = m.group(1), int(m.group(2))
    try:
        sock = socket.create_connection((host, port), timeout=0.5)
        sock.close()
        return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


def _classify_error(error_detail: str, proxy: Optional[str] = None) -> tuple:
    """根据错误内容分类，返回 (error_code, hints)"""
    err = error_detail.lower()

    if "connection refused" in err or "proxy" in err and "refused" in err:
        return "proxy_unreachable", [
            "检查代理 App 是否启动（Clash/Surge/V2Ray）",
            f"确认代理端口正确: {proxy or '未指定'}",
            "或去掉 proxy 参数直连下载",
        ]
    elif "not available" in err and "country" in err:
        return "geo_blocked", [
            "该视频有地区限制",
            "尝试切换代理节点到目标国家/地区",
            "或使用其他 IP 池",
        ]
    elif "private video" in err or "login required" in err or "sign in" in err:
        return "private_video", [
            "该视频需要登录才能观看",
            "确保 Chrome 已登录该平台账号（yt-dlp 会读取 Chrome cookie）",
            "或手动提供 cookie 文件",
        ]
    elif "video unavailable" in err or "not exist" in err or "404" in err:
        return "video_not_found", [
            "视频不存在或已被删除",
            "检查 URL 是否正确",
            "该视频可能已被原作者下架",
        ]
    elif "timed out" in err or "timeout" in err:
        return "network_timeout", [
            "网络连接超时",
            "检查网络连接是否正常",
            "如果是 YouTube 等海外站点，确认代理可用",
            "或稍后重试",
        ]
    elif "requested format" in err or "format" in err and "not available" in err:
        return "format_unavailable", [
            "请求的视频格式不可用",
            "尝试去掉 format 参数使用默认格式 (bestvideo+bestaudio)",
            "或使用 --audio 仅下载音频",
        ]
    elif "unsupported url" in err or "no suitable" in err:
        return "unknown_extractor", [
            "该网站可能不被 yt-dlp 支持",
            "尝试用浏览器开发者工具抓取直接视频流 URL",
            "如果是 m3u8/rtmp 流，vgrab 会自动尝试 ffmpeg 录制",
        ]
    else:
        return "download_failed", [
            "下载失败，请查看详细错误信息",
            "尝试重试，或换一个视频格式",
            "如持续失败，可能是 yt-dlp 版本过旧，运行: brew upgrade yt-dlp",
        ]
