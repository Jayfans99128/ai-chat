"""Bridge Edge TTS audio to a local RVC Python API service."""

import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class RVCServiceError(RuntimeError):
    """Raised when the configured local RVC conversion service cannot be used."""


def _rvc_convert_url() -> str:
    service_url = os.getenv("RVC_API_URL", "http://127.0.0.1:5050").rstrip("/")
    parsed = urlsplit(service_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RVCServiceError(
            "RVC_API_URL must point to a local HTTP service such as "
            "http://127.0.0.1:5050"
        )
    return f"{service_url}/convert"


def synthesize_with_rvc(text: str, emotion: str = None) -> bytes:
    """Synthesize a base voice, then convert it with the local RVC service."""
    from .tts import TTSEngine

    convert_url = _rvc_convert_url()
    source_path = TTSEngine(
        engine="edge_tts",
        voice="zh-CN-XiaoxiaoNeural",
    ).synthesize(text, emotion=emotion)
    if not source_path:
        raise RuntimeError("基础语音合成没有生成音频")

    try:
        with open(source_path, "rb") as source_file:
            request_body = json.dumps({
                "audio_data": base64.b64encode(source_file.read()).decode("ascii"),
            }).encode("utf-8")
    finally:
        Path(source_path).unlink(missing_ok=True)

    request = Request(
        convert_url,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=300) as response:
            content_type = response.headers.get("Content-Type", "")
            audio = response.read()
    except HTTPError as exc:
        details = exc.read(1000).decode("utf-8", errors="replace").strip()
        raise RVCServiceError(
            f"本地 RVC 服务返回 HTTP {exc.code}"
            + (f": {details}" if details else "")
        ) from exc
    except URLError as exc:
        raise RVCServiceError(
            "无法连接本地 RVC 服务；请先启动 RVC API 服务。"
        ) from exc

    if not content_type.lower().startswith("audio/") or not audio:
        raise RVCServiceError(
            "本地 RVC 服务没有返回有效音频；请确认已加载 Ayaka_RVC 模型。"
        )
    return audio
