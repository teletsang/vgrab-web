"""直播录制模块 — 独立于下载/转录/分析，只管拉流录制"""
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from core.config import DOWNLOAD_DIR
from core.logger import get_logger
from core.task_store import TaskStore

logger = get_logger("record")

# 任务存储
tasks = TaskStore("record")
# proc 对象单独存储（不可序列化）
_procs: dict = {}
_procs_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="rec")


def start_record(stream_url: str, settings: dict) -> str:
    """启动直播录制，返回 live_id"""
    live_id = str(uuid.uuid4())[:8]

    output_dir = DOWNLOAD_DIR / live_id
    output_dir.mkdir(parents=True, exist_ok=True)

    title = settings.get("title", "直播录制")
    filename = f"{title}.mp4"
    output_path = output_dir / filename

    tasks.put(live_id, {
        "id": live_id,
        "url": stream_url,
        "title": title,
        "status": "recording",
        "progress": "连接中...",
        "start_time": time.time(),
        "duration": 0,
        "file_path": str(output_path),
        "file_size": 0,
    })

    _executor.submit(_do_record, live_id, stream_url, str(output_path), settings)
    logger.info(f"录制启动: {live_id} -> {stream_url[:80]}")
    return live_id


def stop_record(live_id: str) -> bool:
    """停止录制"""
    with _procs_lock:
        proc = _procs.get(live_id)
    if proc and proc.poll() is None:
        proc.terminate()
        tasks.update(live_id, status="stopping", progress="正在停止...")
        logger.info(f"录制停止: {live_id}")
        return True
    return False


def get_live_task(live_id: str) -> Optional[dict]:
    return tasks.get(live_id)


def get_all_live_tasks() -> list:
    return tasks.get_all()


def _do_record(live_id: str, stream_url: str, output_path: str, settings: dict):
    """ffmpeg 拉流录制"""
    cmd = [
        "ffmpeg", "-y",
        "-headers", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36\r\n",
        "-i", stream_url,
        "-c", "copy",
        "-movflags", "+faststart",
        output_path
    ]

    max_duration = settings.get("max_duration")
    if max_duration:
        cmd.insert(-1, "-t")
        cmd.insert(-1, str(max_duration))

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        with _procs_lock:
            _procs[live_id] = proc
        tasks.update(live_id, progress="录制中...")

        # 获取 start_time
        raw = tasks.get_raw(live_id)
        start_time = raw["start_time"] if raw else time.time()

        # 监控录制状态
        while proc.poll() is None:
            time.sleep(2)
            out_file = Path(output_path)
            if out_file.exists():
                size = out_file.stat().st_size
                elapsed = time.time() - start_time
                tasks.update(
                    live_id,
                    file_size=size,
                    duration=elapsed,
                    progress=f"录制中 | {_format_size(size)} | {_format_time(elapsed)}",
                )

        # 录制结束
        out_file = Path(output_path)
        if out_file.exists() and out_file.stat().st_size > 0:
            elapsed = time.time() - start_time
            tasks.update(
                live_id,
                status="done",
                progress="录制完成",
                duration=elapsed,
                file_size=out_file.stat().st_size,
            )
            logger.info(f"录制完成: {live_id}, 时长 {_format_time(elapsed)}")
        else:
            stderr = proc.stderr.read().decode("utf-8", errors="ignore")[-300:]
            tasks.update(live_id, status="error", progress=f"录制失败: {stderr[-150:]}")
            logger.warning(f"录制失败: {live_id}")

    except Exception as e:
        tasks.update(live_id, status="error", progress=f"录制异常: {str(e)[:200]}")
        logger.error(f"录制异常: {live_id}", exc_info=True)
    finally:
        with _procs_lock:
            _procs.pop(live_id, None)


def _format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1048576:
        return f"{size/1024:.1f} KB"
    if size < 1073741824:
        return f"{size/1048576:.1f} MB"
    return f"{size/1073741824:.2f} GB"
