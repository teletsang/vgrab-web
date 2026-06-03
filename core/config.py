# 配置
import os
import shutil
from pathlib import Path

PORT = int(os.environ.get("VGRAB_PORT", 9999))
HOST = os.environ.get("VGRAB_HOST", "0.0.0.0")
DOWNLOAD_DIR = Path(os.environ.get("VGRAB_DOWNLOAD_DIR", "~/Downloads/vgrab-web")).expanduser()
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 文件浏览允许的根目录（安全白名单）
ALLOWED_ROOTS = [DOWNLOAD_DIR, Path.home() / "Downloads", Path.home() / "Movies"]
_extra_roots = os.environ.get("VGRAB_BROWSE_ROOTS", "")
if _extra_roots:
    ALLOWED_ROOTS.extend(Path(p.strip()).expanduser().resolve() for p in _extra_roots.split(",") if p.strip())

# Whisper 配置
WHISPER_CLI = os.environ.get("VGRAB_WHISPER_CLI", shutil.which("whisper-cli") or "/usr/local/bin/whisper-cli")
WHISPER_MODEL = os.environ.get(
    "VGRAB_WHISPER_MODEL",
    str(Path.home() / ".cache/whisper-cpp/ggml-large-v3-turbo.bin")
)

# LLM 配置
LOCAL_LLM_URL = os.environ.get("VGRAB_LOCAL_LLM", "http://127.0.0.1:8080/v1/chat/completions")
LOCAL_LLM_TIMEOUT = int(os.environ.get("VGRAB_LOCAL_LLM_TIMEOUT", 30))

# 限制
MAX_CONCURRENT_DOWNLOADS = int(os.environ.get("VGRAB_MAX_DOWNLOADS", 5))
TASK_TTL_SECONDS = int(os.environ.get("VGRAB_TASK_TTL", 7200))
