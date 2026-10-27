"""
AI-Girlfriend-Agent — 语音合成 (TTS)

将 AI 回复文本转为语音播放。
当前为占位实现，后续可接入：
- 本地: Edge TTS / Coqui TTS
- API: 火山引擎 TTS / 讯飞 / Azure
"""

import logging
import json
import os
import subprocess  # 用于回退读取 Windows 系统环境变量
import tempfile
from pathlib import Path
import asyncio
import base64  # 用于音频 DataURL 编码
from typing import Optional

logger = logging.getLogger("tts")


_AUDIO_MIME = {
    '.wav': 'audio/wav',
    '.mp3': 'audio/mpeg',
    '.m4a': 'audio/mp4',
    '.aac': 'audio/aac',
    '.ogg': 'audio/ogg',
    '.flac': 'audio/flac',
}

# MiMo API 只支持 wav / mp3 格式
_MIMO_SUPPORTED_EXTS = ('.wav', '.mp3')

# ── 情绪标记映射 ──────────────────────────────────────
# LLM 回复中可能包含 *happy*、*sad* 等情绪标记
# 需要解析这些标记，用于指导 TTS 语调
EMOTION_MARKERS = {
    "happy": ["happy", "开心", "高兴", "兴奋", "excited", "喜悦"],
    "sad": ["sad", "难过", "伤心", "悲伤", "depressed", "沮丧"],
    "angry": ["angry", "生气", "愤怒", "mad", "恼怒"],
    "gentle": ["gentle", "温柔", "轻声", "soft", "柔和"],
    "shy": ["shy", "害羞", "羞涩", "embarrassed", "腼腆"],
    "normal": ["normal", "平静", "自然", "淡定"],
}

# ── 情绪到语音参数映射 ──────────────────────────────
# 根据情绪类型调整 MiMo TTS 参数
EMOTION_VOICE_PARAMS = {
    "happy": {
        "emotion_strength": 0.55,
        "pitch": 1,
        "speed": 1.03,
        "description": "开心、兴奋的语调",
    },
    "sad": {
        "emotion_strength": 0.55,
        "pitch": -2,
        "speed": 0.9,
        "description": "悲伤、痛苦、想哭的语调",
    },
    "angry": {
        "emotion_strength": 0.55,
        "pitch": 1,
        "speed": 1.0,
        "description": "生气、有力的语调",
    },
    "gentle": {
        "emotion_strength": 0.45,
        "pitch": 0,
        "speed": 0.95,
        "description": "温柔、轻柔的语调",
    },
    "shy": {
        "emotion_strength": 0.35,
        "pitch": 0,
        "speed": 0.92,
        "description": "害羞、不好意思、轻声细语的语调",
    },
    "normal": {
        "emotion_strength": 0.4,
        "pitch": 0,
        "speed": 1.0,
        "description": "自然、平静的语调",
    },
}


def _ensure_ffmpeg():
    """确保 ffmpeg 可用，否则给出安装指引"""
    import shutil
    if shutil.which('ffmpeg'):
        return
    # 检查项目 scripts/ 目录（可能放了打包的 ffmpeg）
    scripts_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scripts')
    scripts_ffmpeg = os.path.join(scripts_dir, 'ffmpeg.exe')
    if os.path.isfile(scripts_ffmpeg):
        os.environ['PATH'] = scripts_dir + os.pathsep + os.environ.get('PATH', '')
        return
    # 检查常见安装路径
    common_paths = [
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        os.path.expanduser(r'~\scoop\apps\ffmpeg\current\bin\ffmpeg.exe'),
    ]
    for p in common_paths:
        if os.path.isfile(p):
            os.environ['PATH'] = os.path.dirname(p) + os.pathsep + os.environ.get('PATH', '')
            return
    raise RuntimeError(
        "未找到 ffmpeg。音频格式转换需要 ffmpeg。\n"
        "安装方法:\n"
        "  1. winget install ffmpeg\n"
        "  2. 或从 https://ffmpeg.org/download.html 下载并添加到 PATH"
    )


def _to_wav(path: str) -> str:
    """将非 wav/mp3 音频转为 wav（MiMo 不支持 m4a 等格式）"""
    ext = Path(path).suffix.lower()
    if ext in _MIMO_SUPPORTED_EXTS:
        return path
    _ensure_ffmpeg()
    try:
        from pydub import AudioSegment
        logger.info("转换音频格式: %s -> wav", path)
        audio = AudioSegment.from_file(path)
        out = os.path.join(tempfile.gettempdir(), f"tts_conv_{os.getpid()}.wav")
        audio.export(out, format="wav")
        return out
    except ImportError:
        raise RuntimeError(
            "需要 pydub 库来转换 m4a 音频。请运行: pip install pydub"
        )
    except Exception as e:
        raise RuntimeError(f"音频格式转换失败 ({path}): {e}")


def _audio_to_dataurl(path: str) -> str:
    """Read audio file as DataURL with correct MIME type"""
    # 先确保格式是 MiMo 支持的（wav/mp3）
    path = _to_wav(path)
    ext = Path(path).suffix.lower()
    mime = _AUDIO_MIME.get(ext, 'audio/wav')
    with open(path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')
    return f'data:{mime};base64,{b64}'

def _get_env(name: str, default: str = None) -> Optional[str]:
    """获取环境变量，优先从 Windows 系统变量读取（避免缓存的旧值）"""
    # 先从 Windows User 环境变量读取（最新值）
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             f"[Environment]::GetEnvironmentVariable('{name}','User')"],
            capture_output=True, text=True, timeout=5
        )
        val = result.stdout.strip()
        if val:
            os.environ[name] = val
            return val
    except Exception:
        pass
    # 再从 Windows Machine 环境变量读取
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             f"[Environment]::GetEnvironmentVariable('{name}','Machine')"],
            capture_output=True, text=True, timeout=5
        )
        val = result.stdout.strip()
        if val:
            os.environ[name] = val
            return val
    except Exception:
        pass
    # 最后从当前进程环境变量读取
    val = os.environ.get(name)
    if val:
        return val
    return default


class TTSEngine:
    """语音合成引擎"""

    def __init__(
        self,
        engine: str = None,
        voice: str = None,
        mimo_profile: str = None,
    ):
        # 延迟导入配置，避免启动时循环导入问题
        try:
            from ..config import TTS_CONFIG
        except Exception:
            try:
                # 尝试直接导入（当作为独立模块运行时）
                import sys
                from pathlib import Path
                backend_dir = str(Path(__file__).parent.parent)
                if backend_dir not in sys.path:
                    sys.path.insert(0, backend_dir)
                from config import TTS_CONFIG
            except Exception:
                # 回退默认值
                TTS_CONFIG = {}

        self.engine = engine or TTS_CONFIG.get("ENGINE", "web_speech_api")
        self.voice = voice or TTS_CONFIG.get("VOICE", "zh-CN-XiaoxiaoNeural")
        self.mimo_profile = mimo_profile
        self.sample_rate = TTS_CONFIG.get("SAMPLE_RATE", 22050)
        self.model_path = TTS_CONFIG.get("MODEL_PATH", "")
        logger.info("TTS 引擎初始化: %s (voice=%s, sample_rate=%s)", self.engine, self.voice, self.sample_rate)

    @staticmethod
    def parse_emotion_markers(text: str) -> tuple[str, str]:
        """
        解析文本中的情绪标记，返回 (清理后的文本, 情绪类型)

        支持的标记格式：
        - *happy* / *开心* / *兴奋*
        - *sad* / *难过* / *伤心*
        - *angry* / *生气* / *愤怒*
        - *gentle* / *温柔* / *轻声*
        - *shy* / *害羞* / *羞涩*
        - *normal* / *平静* / *自然*

        示例：
        - "你好啊*happy*~" → ("你好啊~", "happy")
        - "*gentle*晚安~" → ("晚安~", "gentle")
        """
        import re
        if not text:
            return text, "normal"

        detected_emotion = "normal"

        # 匹配 *emotion* 格式的标记（支持中英文）
        emotion_pattern = re.compile(r'\*([^*]+)\*')

        def replace_marker(match):
            nonlocal detected_emotion
            marker = match.group(1).strip().lower()

            # 检查是否是已知情绪标记
            for emotion, keywords in EMOTION_MARKERS.items():
                if marker in [k.lower() for k in keywords]:
                    detected_emotion = emotion
                    return ""  # 移除标记

            # 不是情绪标记，保留原样
            return match.group(0)

        # 替换所有情绪标记
        text = emotion_pattern.sub(replace_marker, text)

        # 移除中文括号内容：（xxx）/（xxx）/【xxx】
        text = re.sub(r'[（\(][^）\)]*[）\)]', '', text)
        # 移除方括号内容：[xxx]
        text = re.sub(r'\[[^\]]*\]', '', text)
        # 清理多余空格和换行
        text = re.sub(r'\s+', ' ', text).strip()

        return text, detected_emotion

    @staticmethod
    def clean_text_for_tts(text: str) -> str:
        """清理文本，移除括号内的动作/表情描述，只保留说话内容"""
        import re
        if not text:
            return text
        # 移除中文括号内容：（xxx）/（xxx）/【xxx】
        text = re.sub(r'[（\(][^）\)]*[）\)]', '', text)
        # 移除星号包裹的动作：*xxx*
        text = re.sub(r'\*[^*]+\*', '', text)
        # 移除方括号内容：[xxx]
        text = re.sub(r'\[[^\]]*\]', '', text)
        # 清理多余空格和换行
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def get_emotion_params(emotion: str) -> dict:
        """
        根据情绪类型获取语音参数

        Args:
            emotion: 情绪类型 (happy, sad, angry, gentle, shy, normal)

        Returns:
            包含 emotion_strength, pitch, speed 的字典
        """
        return EMOTION_VOICE_PARAMS.get(emotion, EMOTION_VOICE_PARAMS["normal"])

    def synthesize(self, text: str, emotion: str = None) -> str:
        """
        将文本转为语音，返回音频文件路径

        Args:
            text: 要合成的文本（可以包含情绪标记）
            emotion: 情绪类型（可选，如果为 None 则从文本中解析）

        Returns:
            音频文件路径
        """
        if self.engine == "web_speech_api":
            # 前端通过 Web Speech API 直接合成，后端不生成音频文件
            logger.debug("TTS: 使用 Web Speech API 模式，后端不生成音频")
            return ""

        # 解析情绪标记（如果未指定情绪）
        if emotion is None:
            text, detected_emotion = self.parse_emotion_markers(text)
        else:
            # 即使指定了情绪，也要清理文本中的标记
            text, _ = self.parse_emotion_markers(text)
            detected_emotion = emotion

        # 获取情绪对应的语音参数
        emotion_params = self.get_emotion_params(detected_emotion)
        logger.info("TTS 情绪: %s, 参数: %s", detected_emotion, emotion_params)

        # pyttsx3 本地离线合成为 WAV
        if self.engine == "pyttsx3":
            try:
                import pyttsx3
            except Exception as e:  # pragma: no cover - optional dependency
                raise RuntimeError("pyttsx3 未安装。请运行: pip install pyttsx3") from e

            out_path = os.path.join(tempfile.gettempdir(), f"tts_{os.getpid()}_{int(asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else asyncio.get_event_loop().time())}.wav")
            engine = pyttsx3.init()
            engine.save_to_file(text, out_path)
            engine.runAndWait()
            return out_path

        # edge_tts（需要安装 edge-tts，异步接口）
        if self.engine == "edge_tts":
            try:
                import edge_tts
            except Exception as e:  # pragma: no cover - optional dependency
                raise RuntimeError("edge-tts 未安装。请运行: pip install edge-tts") from e

            fd, out_path = tempfile.mkstemp(prefix="tts_edge_", suffix=".mp3")
            os.close(fd)

            async def _save_edge(text, voice, path):
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(path)

            try:
                asyncio.run(_save_edge(text, self.voice, out_path))
            except Exception:
                Path(out_path).unlink(missing_ok=True)
                raise
            return out_path

        # 小米 MiMo TTS — 通过 Chat Completions API + audio 参数实现（OpenAI 兼容 SDK）
        if self.engine in ("mimo", "xiaomi_mimo"):
            api_key = _get_env("MIMO_API_KEY") or _get_env("API_KEY")
            # 注意：使用 MIMO_BASE_URL 而非 BASE_URL，避免与 LLM 的 SiliconFlow endpoint 冲突
            base_url = _get_env("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
            configured_profile = _get_env("MIMO_TTS_PROFILE")
            configured_model = _get_env("MIMO_TTS_MODEL", "") or ""
            profile = (
                self.mimo_profile
                or configured_profile
                or ("clone" if "voiceclone" in configured_model else "natural")
            ).lower()
            if profile == "natural":
                model = _get_env("MIMO_TTS_STANDARD_MODEL", "mimo-v2.5-tts")
                voice = _get_env("MIMO_TTS_STANDARD_VOICE", "Chloe")
            else:
                model = (
                    configured_model
                    if "voiceclone" in configured_model
                    else "mimo-v2.5-tts-voiceclone"
                )
                voice = _get_env("MIMO_TTS_VOICE", "")
            # 声音克隆参考音频目录（可选）
            # 优先检查项目根目录下的extract_radio
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            default_ref_dir = os.path.join(project_root, "extract_radio")
            clone_ref_dir = (
                _get_env("MIMO_CLONE_REF_DIR", default_ref_dir)
                if profile == "clone"
                else ""
            )
            # 如果目录不存在，尝试Windows环境变量中的值
            if not os.path.isdir(clone_ref_dir):
                clone_ref_dir = _get_env("MIMO_CLONE_REF_DIR", "")
            logger.info("TTS配置: model=%s, clone_ref_dir=%s, exists=%s",
                       model, clone_ref_dir, os.path.isdir(clone_ref_dir) if clone_ref_dir else False)

            logger.info("MiMo TTS 配置: base_url=%s, model=%s, has_api_key=%s", base_url, model, bool(api_key))

            try:
                from openai import OpenAI
                import numpy as np
                import soundfile as sf
            except ImportError as e:
                raise RuntimeError(
                    "MiMo TTS 需要 openai 和 numpy 库。请运行: pip install openai numpy"
                ) from e

            client = OpenAI(api_key=api_key, base_url=base_url)

            # 判断是否为声音克隆模式
            is_voice_clone = profile == "clone" and "voiceclone" in model
            logger.info(
                "MiMo TTS profile=%s, model=%s, voice=%s",
                profile,
                model,
                voice[:80] if voice else None,
            )

            # 如果清理后为空，说一个语气词
            if not text:
                text = "嗯"

            # 根据情绪选择风格描述
            style_descriptions = {
                "happy": "Bright and positive with a light smile; keep it natural, not excited or loud.",
                "sad": "Quiet and subdued but still warm and clear; do not sound tearful.",
                "angry": "Firm and mildly annoyed, controlled and clear; do not shout.",
                "gentle": "Warm, caring and reassuring; slightly slower, soft but clear, never whisper.",
                "shy": "Gently hesitant and soft, with clear pronunciation; avoid exaggerated breathiness.",
                "normal": (
                    "Natural Mandarin from an original adult female voice: warm, bright, and friendly. "
                    "Use clear diction, a gentle smile, moderate pace, and natural pauses. "
                    "Do not imitate any known character or performer."
                ),
            }
            style_desc = style_descriptions.get(detected_emotion, style_descriptions["normal"])

            # 消息结构：user 放风格描述，assistant 放要朗读的文本
            messages = [
                {
                    "role": "user",
                    "content": style_desc,
                },
                {"role": "assistant", "content": text},
            ]

            # 处理 voice 参数：文件名 → DataURL（声音克隆时需要）
            if voice.startswith("data:audio/"):
                # 已经是 DataURL，直接使用
                audio_voice = voice
            elif clone_ref_dir and os.path.isdir(clone_ref_dir):
                # 有参考音频目录 → 选择最合适的音频文件作为参考
                # 优先使用 all_references.wav（拼接的完整参考音频）
                all_ref = os.path.join(clone_ref_dir, "all_references.wav")
                if os.path.isfile(all_ref):
                    ref_path = all_ref
                    logger.info("声音克隆参考音频（拼接）: %s", ref_path)
                    audio_voice = _audio_to_dataurl(ref_path)
                else:
                    # 回退：使用单个参考文件
                    ref_files = sorted([
                        f for f in os.listdir(clone_ref_dir)
                        if f.startswith("reference_") and f.endswith(".wav")
                    ])
                    if ref_files:
                        ref_path = os.path.join(clone_ref_dir, ref_files[0])
                        logger.info("声音克隆参考音频: %s", ref_path)
                        audio_voice = _audio_to_dataurl(ref_path)
                    else:
                        raise RuntimeError(f"声音克隆目录 {clone_ref_dir} 中未找到参考音频文件")
            elif is_voice_clone and voice:
                # 声音克隆模式下，voice 应该指向一个音频文件
                # 处理相对路径：相对于项目根目录
                if not os.path.isabs(voice):
                    # 尝试相对于项目根目录（backend/ 的上级目录）
                    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                    abs_voice = os.path.join(project_dir, voice)
                    if os.path.isfile(abs_voice):
                        voice = abs_voice
                    # 再尝试相对于 backend/ 目录
                    else:
                        backend_dir = os.path.dirname(os.path.dirname(__file__))
                        abs_voice = os.path.join(backend_dir, voice)
                        if os.path.isfile(abs_voice):
                            voice = abs_voice

                if os.path.isfile(voice):
                    logger.info("声音克隆参考音频: %s", voice)
                    audio_voice = _audio_to_dataurl(voice)
                else:
                    raise RuntimeError(
                        f"声音克隆模型需要参考音频，但找不到文件: {voice}\n"
                        "请设置 MIMO_TTS_VOICE 为音频文件路径，或设置 MIMO_CLONE_REF_DIR 指向音频目录"
                    )
            elif is_voice_clone:
                # 声音克隆模式但没有指定参考音频
                raise RuntimeError(
                    "声音克隆模型需要参考音频\n"
                    "请设置 MIMO_TTS_VOICE 为音频文件路径，或设置 MIMO_CLONE_REF_DIR 指向音频目录"
                )
            else:
                # 普通 voice 名称（标准 TTS）
                audio_voice = voice

            try:
                # 构建 audio 参数
                # normal 状态下不传情绪参数，保持原始音色
                if detected_emotion == "normal":
                    audio_params = {
                        "format": "wav" if is_voice_clone else "pcm16",
                        "voice": audio_voice,
                    }
                else:
                    # 其他情绪状态下传入情绪参数
                    audio_params = {
                        "format": "wav" if is_voice_clone else "pcm16",
                        "voice": audio_voice,
                        "emotion_strength": emotion_params["emotion_strength"],
                        "pitch": emotion_params["pitch"],
                        "speed": emotion_params["speed"],
                    }

                if is_voice_clone or audio_voice.startswith("data:audio/"):
                    # ===== 声音克隆模式：非流式 =====
                    completion = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        audio=audio_params,
                        stream=False,
                    )
                    audio_data = completion.choices[0].message.audio
                    if not audio_data or not audio_data.data:
                        raise RuntimeError("MiMo 声音克隆未返回音频数据")
                    pcm_bytes = base64.b64decode(audio_data.data)
                    np_pcm = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                    out_path = os.path.join(
                        tempfile.gettempdir(), f"tts_mimo_{os.getpid()}.wav"
                    )
                    sf.write(out_path, np_pcm, samplerate=24000)
                    logger.info("MiMo 声音克隆合成成功: %s (情绪: %s)", out_path, detected_emotion)
                    return out_path
                else:
                    # ===== 标准 TTS：流式 =====
                    collected_chunks = []
                    completion = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        audio=audio_params,
                        stream=True,
                    )
                    for chunk in completion:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        audio_data = getattr(delta, "audio", None)
                        if audio_data is not None:
                            pcm_bytes = base64.b64decode(audio_data["data"])
                            np_pcm = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                            collected_chunks.append(np_pcm)

                    if not collected_chunks:
                        raise RuntimeError("MiMo TTS 未返回任何音频数据")

                    audio_array = np.concatenate(collected_chunks)
                    out_path = os.path.join(
                        tempfile.gettempdir(), f"tts_mimo_{os.getpid()}.wav"
                    )
                    sf.write(out_path, audio_array, samplerate=24000)
                    logger.info("MiMo TTS 合成成功: %s (情绪: %s)", out_path, detected_emotion)
                    return out_path

            except Exception as e:
                raise RuntimeError(f"MiMo TTS 请求失败: {e}") from e

        raise NotImplementedError(f"TTS engine '{self.engine}' not implemented yet")

    def synthesize_to_bytes(self, text: str, emotion: str = None) -> bytes:
        """
        将文本转为语音，返回音频字节

        Args:
            text: 要合成的文本
            emotion: 情绪类型（可选）

        Returns:
            音频字节数据
        """
        if self.engine == "web_speech_api":
            return b""
        # 先利用 synthesize 生成临时文件，再读取为 bytes
        path = self.synthesize(text, emotion=emotion)
        if not path:
            return b""
        try:
            with open(path, "rb") as f:
                data = f.read()
        finally:
            try:
                # 尝试删除临时文件
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
        return data


# 全局单例，使用配置中的默认引擎
tts_engine = TTSEngine()
