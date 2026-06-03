"""转录模块 — 使用 whisper-cli (whisper.cpp) 实现音频转文字"""
import json
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from core.config import WHISPER_CLI, WHISPER_MODEL
from core.logger import get_logger
from core.task_store import TaskStore

logger = get_logger("transcribe")

# 任务存储
tasks = TaskStore("transcribe")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tr")


def start_transcribe(video_path: str, settings: dict) -> str:
    """启动转录任务，返回 transcribe_id"""
    transcribe_id = str(uuid.uuid4())[:8]

    tasks.put(transcribe_id, {
        "id": transcribe_id,
        "video": video_path,
        "status": "transcribing",
        "progress": "提取音频...",
        "result": "",
    })

    _executor.submit(_do_transcribe, transcribe_id, video_path, settings)
    logger.info(f"转录启动: {transcribe_id} -> {video_path}")
    return transcribe_id


def get_transcribe_task(transcribe_id: str) -> Optional[dict]:
    return tasks.get(transcribe_id)


def _do_transcribe(transcribe_id: str, video_path: str, settings: dict):
    """ffmpeg 提取音频 -> whisper-cli 转录"""
    video = Path(video_path)

    # 如果传入目录，找视频文件
    if video.is_dir():
        video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.ts')
        vids = [f for f in video.iterdir() if f.suffix.lower() in video_exts]
        if vids:
            video = vids[0]
        else:
            tasks.update(transcribe_id, status="error", progress="目录中未找到视频文件")
            return

    if not video.exists():
        tasks.update(transcribe_id, status="error", progress="视频文件不存在")
        return

    # 临时音频文件（whisper-cli 需要 16kHz mono WAV）
    audio_path = video.parent / f"_audio_{transcribe_id}.wav"

    try:
        # 1. 提取音频
        tasks.update(transcribe_id, progress="提取音频...")

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-vn",
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(audio_path)
        ]
        r = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=120)
        if r.returncode != 0 or not audio_path.exists():
            tasks.update(transcribe_id, status="error", progress="音频提取失败")
            logger.warning(f"音频提取失败: {transcribe_id}")
            return

        # 2. whisper-cli 转录
        tasks.update(transcribe_id, progress="Whisper 转录中（可能需要几分钟）...")

        model_path = settings.get("whisper_model_path", WHISPER_MODEL)

        whisper_cmd = [
            WHISPER_CLI,
            "-m", model_path,
            "-f", str(audio_path),
            "-l", "auto",
            "-oj",
            "--no-prints",
        ]
        proc = subprocess.run(whisper_cmd, capture_output=True, text=True, timeout=1200)

        if proc.returncode != 0:
            tasks.update(transcribe_id, status="error", progress=f"Whisper 转录失败: {proc.stderr[:200]}")
            logger.warning(f"Whisper 失败: {transcribe_id}, stderr={proc.stderr[:100]}")
            return

        # 3. 解析 JSON 输出
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            tasks.update(transcribe_id, status="error", progress="Whisper 输出解析失败")
            logger.warning(f"JSON 解析失败: {transcribe_id}")
            return

        # 提取文本和时间戳
        segments = result.get("transcription", [])
        full_text = " ".join(seg.get("text", "").strip() for seg in segments)

        timestamped = ""
        for seg in segments:
            start = seg.get("timestamps", {}).get("from", "00:00")
            text = seg.get("text", "").strip()
            if text:
                timestamped += f"[{start}] {text}\n"

        output = f"{full_text}\n\n---\n\n## 时间轴\n\n{timestamped}" if timestamped else full_text

        tasks.update(transcribe_id, status="done", progress="转录完成", result=output)
        logger.info(f"转录完成: {transcribe_id}")

    except subprocess.TimeoutExpired:
        tasks.update(transcribe_id, status="error", progress="转录超时（>20分钟）")
        logger.warning(f"转录超时: {transcribe_id}")
    except Exception as e:
        tasks.update(transcribe_id, status="error", progress=f"转录异常: {str(e)[:200]}")
        logger.error(f"转录异常: {transcribe_id}", exc_info=True)
    finally:
        # 清理临时音频
        if audio_path.exists():
            audio_path.unlink()
