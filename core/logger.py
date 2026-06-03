"""统一日志模块"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config import DOWNLOAD_DIR

LOG_DIR = DOWNLOAD_DIR / "_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    """创建模块级 logger，同时输出到 console 和文件"""
    logger = logging.getLogger(f"vgrab.{name}")
    if logger.handlers:
        return logger  # 已配置，避免重复添加 handler

    logger.setLevel(logging.DEBUG)

    # Console handler (INFO+)
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(ch)

    # File handler (DEBUG+, 5MB rotating, 3 backups)
    fh = RotatingFileHandler(
        LOG_DIR / "vgrab.log", maxBytes=5 * 1024 * 1024, backupCount=3,
        encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
    ))
    logger.addHandler(fh)

    return logger
