"""
AI-Girlfriend-Agent — 模型/API 配置
复用原 职小猪 的 OpenAI 兼容客户端
"""
from openai import OpenAI
from dotenv import load_dotenv
import os
import subprocess
import tempfile

load_dotenv()

# OpenAI 兼容客户端（用于 LLM 对话）
api_key = os.getenv("API_KEY")
if not api_key:
    raise RuntimeError(
        "未找到 API_KEY 环境变量。请在 .env 文件或系统环境变量中设置 API_KEY"
    )
client = OpenAI(
    api_key=api_key,
    base_url=os.getenv("BASE_URL", "https://api.siliconflow.cn/v1"),
)
MODEL = os.getenv("MODEL", "deepseek-ai/DeepSeek-V4-Flash")

# 工具定义 — 可根据需要扩展
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索获取最新信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"],
            },
        },
    },
]


def _load_win_env():
    """从 Windows User 环境变量读取关键配置并注入当前进程"""
    import subprocess as _sp

    def _read(key):
        try:
            r = _sp.run(
                ["powershell", "-NoProfile", "-Command",
                 '[Environment]::GetEnvironmentVariable("{}","User")'.format(key)],
                capture_output=True, text=True, timeout=5
            )
            return r.stdout.strip() or None
        except Exception:
            return None

    import os as _os
    for key in [
        "MIMO_API_KEY", "API_KEY", "MIMO_TTS_ENDPOINT", "MIMO_ENDPOINT",
        "BASE_URL", "MIMO_TTS_MODEL", "MIMO_CLONE_REF_DIR",
        "TTS_ENGINE", "TTS_VOICE",
    ]:
        if not _os.environ.get(key):
            val = _read(key)
            if val:
                _os.environ[key] = val


# 启动时从 Windows 系统环境变量注入
_load_win_env()


# Text-to-Speech (TTS) 配置
# 可通过环境变量覆盖（优先顺序：环境变量 > 这里的默认值）
# 也会自动从 Windows 系统环境变量回退读取
TTS_CONFIG = {
    # 可选值：web_speech_api, pyttsx3, edge_tts, coqui_tts, local_model, mimo
    # 自动检测：有 MIMO_API_KEY 时默认 mimo，否则 edge_tts（免费无需 API Key）
    "ENGINE": os.getenv("TTS_ENGINE") or ("mimo" if os.getenv("MIMO_API_KEY") else "edge_tts"),
    # 语音/音色标识（不同后端含义不同）
    "VOICE": os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoNeural"),
    # 采样率（Hz）
    "SAMPLE_RATE": int(os.getenv("TTS_SAMPLE_RATE", "22050")),
    # 本地模型路径（若使用本地模型或 Coqui 等）
    "MODEL_PATH": os.getenv("TTS_MODEL_PATH", ""),
    # 声码器 checkpoint 路径（例如 HiFi-GAN）
    "VOCODER_CHECKPOINT": os.getenv("TTS_VOCODER_CHECKPOINT", ""),
}

# 小米 Mimo / 云端 TTS 相关（可选）
TTS_CONFIG.update({
    "MIMO_ENDPOINT": os.getenv("MIMO_TTS_ENDPOINT", ""),
    "MIMO_API_KEY": os.getenv("MIMO_API_KEY", ""),
})