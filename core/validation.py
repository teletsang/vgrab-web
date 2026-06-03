"""请求校验与限流"""
import re
import time
from collections import defaultdict

# URL 格式校验
URL_PATTERN = re.compile(
    r'^https?://'
    r'[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]+'
    r'$'
)

MAX_URL_LENGTH = 2048
MAX_TRANSCRIPT_LENGTH = 100_000  # ~100KB
MAX_PATH_LENGTH = 1024


def validate_download_request(data: dict) -> tuple:
    """校验下载请求。返回 (ok, error_message)"""
    if not data:
        return False, "请求体不能为空"
    url = data.get("url", "")
    if not url or not url.strip():
        return False, "URL 不能为空"
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        return False, f"URL 过长（最大 {MAX_URL_LENGTH} 字符）"
    if not URL_PATTERN.match(url):
        return False, "URL 格式无效，需以 http:// 或 https:// 开头"
    return True, ""


def validate_path_input(path: str) -> tuple:
    """校验文件系统路径"""
    if not path:
        return False, "路径不能为空"
    if len(path) > MAX_PATH_LENGTH:
        return False, "路径过长"
    if '\x00' in path:
        return False, "路径包含非法字符"
    return True, ""


def validate_organize_request(data: dict) -> tuple:
    """校验笔记整理请求"""
    if not data:
        return False, "请求体不能为空"
    transcript = data.get("transcript", "")
    if not transcript or not transcript.strip():
        return False, "转录文本不能为空"
    if len(transcript) > MAX_TRANSCRIPT_LENGTH:
        return False, f"文本过长（最大 {MAX_TRANSCRIPT_LENGTH // 1000}KB）"
    return True, ""


class SimpleRateLimiter:
    """简单内存级限流器（单进程使用）"""

    def __init__(self, max_per_minute: int = 30):
        self._max = max_per_minute
        self._requests: dict = defaultdict(list)

    def allow(self, key: str = "global") -> bool:
        now = time.time()
        window = self._requests[key]
        # 清理 60 秒前的记录
        self._requests[key] = [t for t in window if now - t < 60]
        if len(self._requests[key]) >= self._max:
            return False
        self._requests[key].append(now)
        return True


rate_limiter = SimpleRateLimiter(max_per_minute=30)
