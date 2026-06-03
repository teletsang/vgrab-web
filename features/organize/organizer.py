"""笔记整理模块 — 把转录的口语文本整理成结构化知识笔记"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from core.llm import call_llm
from core.logger import get_logger
from core.task_store import TaskStore

logger = get_logger("organize")

# 任务存储
tasks = TaskStore("organize")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="org")

ORGANIZE_PROMPT = """你是知识整理专家。以下是一段视频/直播的语音转录文本（口语化），请整理成结构化的知识笔记。

要求：
1. 去除口语化表达（嗯、啊、对吧、然后呢等）
2. 提取核心知识点，按逻辑分类
3. 用清晰的标题和层级组织
4. 保留关键数据、名词、结论
5. 如果有操作步骤，按顺序列出
6. 输出中文 Markdown 格式

转录文本：
{transcript}"""


def start_organize(transcript: str, settings: dict) -> str:
    """启动笔记整理，返回 note_id"""
    note_id = str(uuid.uuid4())[:8]

    tasks.put(note_id, {
        "id": note_id,
        "status": "organizing",
        "progress": "LLM 整理中...",
        "result": "",
    })

    _executor.submit(_do_organize, note_id, transcript, settings)
    logger.info(f"整理启动: {note_id}")
    return note_id


def get_note_task(note_id: str) -> Optional[dict]:
    return tasks.get(note_id)


def _do_organize(note_id: str, transcript: str, settings: dict):
    """调用 LLM 整理转录文本"""
    # 截断过长的转录（避免超出 context）
    max_input = 12000
    if len(transcript) > max_input:
        transcript = transcript[:max_input] + "\n\n...(后续内容省略)"

    prompt = ORGANIZE_PROMPT.format(transcript=transcript)

    try:
        messages = [{"role": "user", "content": prompt}]
        note_text = call_llm(messages, settings, timeout=600)

        tasks.update(note_id, status="done", progress="整理完成", result=note_text)
        logger.info(f"整理完成: {note_id}")

    except Exception as e:
        tasks.update(note_id, status="error", progress=f"整理失败: {str(e)[:200]}")
        logger.error(f"整理失败: {note_id}", exc_info=True)
