"""分析模块 — 独立于下载，只管视频分析"""
import base64
import json
import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from core.llm import call_llm
from core.logger import get_logger
from core.task_store import TaskStore

logger = get_logger("analyze")

# 任务存储
tasks = TaskStore("analyze")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="az")

# 每次 LLM 调用最多发送的帧数（控制内存）
MAX_FRAMES_PER_CALL = 8

PROMPTS = {
    "summary": """你是视频内容分析助手。根据视频关键帧和字幕生成结构化摘要。
字幕: {transcript}
输出中文。包含: 1)片段摘要 2)关键要点 3)重要名词""",

    "visual": """你是视觉风格分析专家（游戏/影视方向）。分析视频关键帧的视觉特征。
字幕: {transcript}
输出中文。包含: 1)风格定义 2)色彩方案 3)构图手法 4)光影处理 5)材质特征 6)风格对标""",

    "tutorial": """你是教程分析助手。根据视频关键帧和字幕提取教程步骤。
字幕: {transcript}
输出中文。包含: 1)教程主题 2)操作步骤 3)工具参数 4)注意事项""",

    "creative": """你是广告/创意影片分析专家。分析视频片段的创意手法。
字幕: {transcript}
输出中文。包含: 1)叙事结构 2)视觉节奏 3)符号隐喻 4)目标受众 5)创意亮点""",
}


def start_analyze(video_path: str, settings: dict) -> str:
    """启动分析任务，返回 analyze_id"""
    analyze_id = str(uuid.uuid4())[:8]

    tasks.put(analyze_id, {
        "id": analyze_id,
        "video": video_path,
        "status": "analyzing",
        "progress": "准备中...",
        "slices_total": 0,
        "slices_done": 0,
        "result": "",
    })

    _executor.submit(_do_analyze, analyze_id, video_path, settings)
    logger.info(f"分析启动: {analyze_id} -> {video_path}")
    return analyze_id


def get_analyze_task(analyze_id: str) -> Optional[dict]:
    return tasks.get(analyze_id)


def get_all_analyze_tasks() -> list:
    return tasks.get_all()


def _do_analyze(analyze_id: str, video_path: str, settings: dict):
    """完整分析流水线：切片 -> 抽帧 -> LLM -> 汇总"""
    mode = settings.get("mode", "summary")
    frame_interval = settings.get("frame_interval", 30)

    frames_per_slice = 16
    slice_duration = frame_interval * frames_per_slice
    video = Path(video_path)

    # 如果传入的是目录，自动找里面的视频文件
    if video.is_dir():
        video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.ts')
        vids = [f for f in video.iterdir() if f.suffix.lower() in video_exts]
        if vids:
            video = vids[0]
        else:
            tasks.update(analyze_id, status="error", progress="目录中未找到视频文件")
            return

    if not video.exists():
        tasks.update(analyze_id, status="error", progress="视频文件不存在")
        return

    work_dir = video.parent / f"_analyze_{analyze_id}"
    work_dir.mkdir(exist_ok=True)

    try:
        # 获取视频时长
        duration = _get_duration(video)
        if not duration:
            duration = 600

        # 计算切片数
        num_slices = max(1, int(duration / slice_duration))
        if num_slices > 30:
            num_slices = 30

        tasks.update(analyze_id, slices_total=num_slices, progress=f"共 {num_slices} 个片段，开始分析...")

        # 逐片段分析
        slice_results = []

        for i in range(num_slices):
            start_time = i * slice_duration
            tasks.update(analyze_id, slices_done=i, progress=f"分析片段 {i+1}/{num_slices}...")

            # 抽帧
            frames_dir = work_dir / f"slice_{i:03d}"
            frames_dir.mkdir(exist_ok=True)

            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_time),
                "-t", str(slice_duration),
                "-i", str(video),
                "-vf", f"fps=1/{frame_interval}",
                "-frames:v", str(frames_per_slice),
                "-q:v", "5",  # 更高压缩率，减少内存占用
                str(frames_dir / "frame_%02d.jpg")
            ]
            subprocess.run(ffmpeg_cmd, capture_output=True, timeout=60)

            frames = sorted(frames_dir.glob("*.jpg"))
            if not frames:
                slice_results.append(f"### 片段 {i+1}\n(抽帧失败)\n")
                continue

            # 构建 LLM 请求（限制帧数防止内存爆炸）
            content = []
            for frame in frames[:MAX_FRAMES_PER_CALL]:
                raw = frame.read_bytes()
                img_data = base64.b64encode(raw).decode("utf-8")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}
                })
                del raw, img_data  # 显式释放

            prompt = PROMPTS.get(mode, PROMPTS["summary"]).format(
                transcript="(无字幕，仅根据画面分析)"
            )
            content.append({"type": "text", "text": prompt})

            # 调用 LLM
            try:
                messages = [{"role": "user", "content": content}]
                text = call_llm(messages, settings, timeout=600)
                slice_results.append(f"## 片段 {i+1} ({_format_time(start_time)} - {_format_time(start_time + slice_duration)})\n\n{text}\n")
            except Exception as e:
                slice_results.append(f"### 片段 {i+1}\n(LLM 调用失败: {str(e)[:100]})\n")
                logger.warning(f"分析片段 {i+1} LLM 失败: {analyze_id}", exc_info=True)

            del content  # 释放图像数据

        # 汇总
        tasks.update(analyze_id, progress="生成最终报告...")

        all_slices_text = "\n\n".join(slice_results)
        summary_prompt = f"""以下是一个视频的分段分析结果。请综合所有片段，生成一份完整、流畅的视频内容报告。

要求：
- 直接输出最终报告，不要提及"片段"、"切片"等技术细节
- 用流畅的中文写作
- 结构清晰，有重点

分段内容：
{all_slices_text[:8000]}"""

        try:
            messages = [{"role": "user", "content": summary_prompt}]
            final_report = call_llm(messages, settings, timeout=600)
        except Exception:
            final_report = all_slices_text

        tasks.update(
            analyze_id,
            status="done",
            progress="分析完成",
            slices_done=num_slices,
            result=final_report,
        )
        logger.info(f"分析完成: {analyze_id}")

    except Exception as e:
        tasks.update(analyze_id, status="error", progress=f"分析异常: {str(e)[:200]}")
        logger.error(f"分析异常: {analyze_id}", exc_info=True)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _get_duration(video_path: Path) -> Optional[float]:
    """获取视频时长"""
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
               "-show_format", str(video_path)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        info = json.loads(r.stdout)
        return float(info["format"]["duration"])
    except Exception:
        return None


def _format_time(seconds: float) -> str:
    """秒 -> HH:MM:SS"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
