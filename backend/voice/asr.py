"""
AI-Girlfriend-Agent — 语音识别 (ASR)

将用户语音转为文本。
当前为占位实现，后续可接入：
- 本地: Vosk / Whisper.cpp
- API: 讯飞 / 阿里云 / Azure Speech
"""

import logging
import json

logger = logging.getLogger("asr")


class ASREngine:
    """语音识别引擎"""

    def __init__(self, engine: str = "web_speech_api"):
        self.engine = engine
        logger.info("ASR 引擎初始化: %s", engine)

    def transcribe(self, audio_file: str) -> str:
        """将语音文件转为文字"""
        if self.engine == "web_speech_api":
            # 前端通过 Web Speech API 直接识别，后端暂不处理音频
            logger.warning("ASR: 使用 Web Speech API 模式，后端不处理音频")
            return ""

        # TODO: 接入本地或云端 ASR
        raise NotImplementedError(f"ASR engine '{self.engine}' not implemented yet")

    def transcribe_bytes(self, audio_bytes: bytes) -> str:
        """从字节数据识别语音"""
        if self.engine == "web_speech_api":
            return ""
        raise NotImplementedError(f"ASR engine '{self.engine}' not implemented yet")


# 全局单例
asr_engine = ASREngine()