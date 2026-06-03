# core/llm.py — 统一 LLM 调用，带 fallback
"""
优先级:
1. 用户在设置页指定的 llm_url（本地或远程）
2. 本地 Gemma 4 (127.0.0.1:8080)
3. 工蜂 API (fallback)
"""
import json
import urllib.request
import urllib.error
import os
from typing import Any, Optional

from core.logger import get_logger

logger = get_logger("llm")

# 工蜂 fallback 配置
GONGFENG_API_URL: str = "https://copilot.code.woa.com/server/openclaw/copilot-gateway/v1/chat/completions"
GONGFENG_API_KEY: str = os.environ.get("GF_TOKEN", "")
GONGFENG_USERNAME: str = os.environ.get("GF_USERNAME", "")
GONGFENG_DEVICE_ID: str = os.environ.get("GF_DEVICE_ID", "")
GONGFENG_MODEL: str = "deepseek-v4-pro"

LOCAL_URL: str = "http://127.0.0.1:8080/v1/chat/completions"


def _try_request(
    url: str,
    payload: dict[str, Any],
    api_key: str = "",
    extra_headers: Optional[dict[str, str]] = None,
    timeout: int = 600,
) -> Optional[dict[str, Any]]:
    """尝试调用一个 LLM endpoint，失败返回 None"""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra_headers:
        headers.update(extra_headers)

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError, TimeoutError) as e:
        logger.debug(f"LLM 请求失败: {url} - {type(e).__name__}: {e}")
        return None
    except Exception as e:
        logger.debug(f"LLM 请求异常: {url} - {type(e).__name__}: {e}")
        return None


def call_llm(messages: list, settings: dict, timeout: int = 600) -> str:
    """
    统一 LLM 调用入口，自动 fallback。
    
    Args:
        messages: OpenAI 格式的 messages 列表
        settings: 前端传来的设置 dict（llm_url, model, api_key, max_tokens, temperature）
        timeout: 超时秒数
    
    Returns:
        LLM 回复文本，全部失败则抛异常
    """
    model = settings.get("model", "gemma-4")
    max_tokens = settings.get("max_tokens", 4096)
    temperature = settings.get("temperature", 0.3)
    
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    
    # --- 尝试 1: 用户指定的地址 ---
    user_url = settings.get("llm_url", "").strip()
    user_key = settings.get("api_key", "").strip()
    
    if user_url:
        endpoint = f"{user_url.rstrip('/')}/v1/chat/completions"
        result = _try_request(endpoint, payload, api_key=user_key, timeout=timeout)
        if result:
            return result["choices"][0]["message"]["content"]
    
    # --- 尝试 2: 本地 Gemma 4 ---
    if not user_url or user_url.rstrip('/') != "http://127.0.0.1:8080":
        local_payload = {**payload, "model": "gemma-4"}
        result = _try_request(LOCAL_URL, local_payload, timeout=30)  # 本地快速超时
        if result:
            return result["choices"][0]["message"]["content"]
    
    # --- 尝试 3: 工蜂 API fallback ---
    gf_token = user_key or GONGFENG_API_KEY
    if gf_token:
        # 检测是否包含图片内容，自动选择模型
        has_images = any(
            isinstance(m.get("content"), list) and 
            any(c.get("type") == "image_url" for c in m["content"] if isinstance(c, dict))
            for m in messages if isinstance(m, dict)
        )
        gf_model = "auto-vision" if has_images else GONGFENG_MODEL
        gf_headers = {
            "OAUTH-TOKEN": gf_token,
            "X-Username": GONGFENG_USERNAME,
            "DEVICE-ID": GONGFENG_DEVICE_ID,
            "X-Model-Name": gf_model,
        }
        gf_payload = {**payload, "model": gf_model}
        result = _try_request(GONGFENG_API_URL, gf_payload, api_key=gf_token, extra_headers=gf_headers, timeout=timeout)
        if result:
            return result["choices"][0]["message"]["content"]
    
    raise ConnectionError("LLM 调用失败：本地模型无响应，工蜂 API 也不可用。请检查网络或设置 API Key。")
