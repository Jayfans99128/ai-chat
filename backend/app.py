"""
AI-Girlfriend-Agent — Flask 主服务

从 AI-Girlfriend-Agent 架构引入 GirlfriendAgent，
同时保留原有的 职小猪 路由以兼容旧前端。
"""
import os
import json
import logging
import time
from logging.handlers import TimedRotatingFileHandler

from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager, get_jwt_identity, jwt_required

from openai import OpenAI
from dotenv import load_dotenv
from .auth import auth_bp
from .agent.girlfriend_agent import GirlfriendAgent
from .database import init_db
from .proactive_agent import ProactiveBehaviorAgent
from .voice.tts import TTSEngine
from .voice.rvc import RVCServiceError, synthesize_with_rvc

load_dotenv()
load_dotenv(".env.db")

# ── API 配置（直接创建，不依赖旧 config.py）──
api_key = os.getenv("API_KEY")
if not api_key:
    raise RuntimeError("API_KEY must be configured in the environment or .env file")

client = OpenAI(
    api_key=api_key,
    base_url=os.getenv("BASE_URL", "https://api.siliconflow.cn/v1"),
)
MODEL = os.getenv("MODEL", "deepseek-ai/DeepSeek-V4-Flash")

EDGE_TTS_VOICES = {
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-XiaoyiNeural",
    "zh-CN-YunxiNeural",
    "zh-CN-YunyangNeural",
    "zh-CN-YunjianNeural",
    "zh-CN-YunxiaNeural",
}
RVC_VOICE = "ayaka-rvc"
MIMO_CLONE_VOICE = "mimo-clone"
DEFAULT_TTS_VOICE = "zh-CN-XiaoxiaoNeural"


def _get_tts_engine_for_voice(voice):
    """Use an allowlisted standard Edge voice when the client requests one."""
    if voice not in EDGE_TTS_VOICES:
        raise ValueError("Unsupported voice")
    return TTSEngine(engine="edge_tts", voice=voice)


LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# ── 通用请求日志（7 天滚转） ──
_app_handler = TimedRotatingFileHandler(
    os.path.join(LOG_DIR, "app.log"),
    when="D", interval=1, backupCount=6,
    encoding="utf-8",
)
_app_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
_app_handler.setLevel(logging.INFO)
logger = logging.getLogger("girlfriend_app")
logger.addHandler(_app_handler)
logger.setLevel(logging.INFO)

# ── 访问日志（HTTP 状态码 + 路径，7 天滚转） ──
_access_handler = TimedRotatingFileHandler(
    os.path.join(LOG_DIR, "access.log"),
    when="D", interval=1, backupCount=6,
    encoding="utf-8",
)
_access_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
access_logger = logging.getLogger("access_log")
access_logger.addHandler(_access_handler)
access_logger.setLevel(logging.INFO)
access_logger.propagate = False

app = Flask(__name__)
CORS(app)
init_db(app)
JWTManager(app)
app.register_blueprint(auth_bp)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
agent = GirlfriendAgent(client, MODEL)
proactive_agent = ProactiveBehaviorAgent(client, MODEL, agent)


# ── 请求日志 ──────────────────────────────────────────
@app.before_request
def _log_request_start():
    request._start_time = time.time()

@app.after_request
def _log_request(response):
    duration = int((time.time() - getattr(request, "_start_time", time.time())) * 1000)
    logger.info("%s %s -> %s (%dms)", request.method, request.path, response.status_code, duration)
    # 访问日志（含状态码）
    access_logger.info(
        "%s %s -> %d (%dms)",
        request.method, request.path, response.status_code, duration,
    )
    return response


# ── TTS 语音接口（供前端播放）────────────────────────
@app.route("/api/tts", methods=["POST"])
def tts():
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    voice = payload.get("voice")
    if voice is not None and not isinstance(voice, str):
        return jsonify({"error": "voice must be a string"}), 400
    if voice and voice not in EDGE_TTS_VOICES and voice not in {
        RVC_VOICE,
        MIMO_CLONE_VOICE,
    }:
        return jsonify({"error": "unsupported voice"}), 400

    if voice == RVC_VOICE:
        try:
            audio_bytes = synthesize_with_rvc(
                text,
                emotion=payload.get("emotion"),
            )
        except RVCServiceError as exc:
            logger.error("RVC 语音转换服务不可用: %s", exc)
            return jsonify({"error": str(exc)}), 503
        except Exception as exc:
            logger.error("RVC 语音合成失败: %s", exc, exc_info=True)
            return jsonify({"error": str(exc)[:500]}), 500
        return Response(audio_bytes, mimetype="audio/wav")

    if voice == MIMO_CLONE_VOICE:
        engine = TTSEngine(engine="mimo", mimo_profile="clone")
    else:
        engine = (
            _get_tts_engine_for_voice(voice)
            if voice
            else _get_tts_engine_for_voice(DEFAULT_TTS_VOICE)
        )

    try:
        audio_bytes = engine.synthesize_to_bytes(
            text,
            emotion=payload.get("emotion"),
        )
    except Exception as exc:
        logger.error("TTS 合成失败: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)[:500]}), 500

    if not audio_bytes:
        return jsonify({"error": "TTS returned empty audio"}), 500

    if engine.engine == "edge_tts":
        mimetype = "audio/mpeg"
    else:
        mimetype = "audio/wav"
    return Response(audio_bytes, mimetype=mimetype)


# ── 静态文件（旧前端：职小猪页面）────────────────────────
@app.route("/")
def index():
    response = send_from_directory(FRONTEND_DIR, "index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

@app.route("/<path:path>")
def static_files(path):
    response = send_from_directory(FRONTEND_DIR, path)
    if path == "index.html":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


# ── 聊天 API（SSE 流式，符合前端 JSON 期望）────────────────
@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    """职小猪旧前端使用的端点：/chat/stream"""
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    user_id = str(payload.get("user_id") or "default")
    proactive_agent.update_activity(user_id)

    def generate():
        for chunk in agent.stream_chat(user_id, message):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    """新前端使用的端点：/api/chat/stream"""
    return chat_stream()


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    user_id = str(payload.get("user_id") or "default")
    proactive_agent.update_activity(user_id)
    reply = agent.chat(user_id, message)
    return jsonify({"reply": reply})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    return chat()


# ── 主动对话 ──────────────────────────────────────────
@app.route("/api/proactive", methods=["GET"])
@jwt_required()
def api_proactive():
    user_id = get_jwt_identity()

    if user_id not in proactive_agent.last_activity:
        proactive_agent.update_activity(user_id)
        return jsonify({"has_message": False})

    message = proactive_agent.check_and_generate(user_id)
    if not message:
        return jsonify({"has_message": False})

    return jsonify({"has_message": True, "message": message})


# ── 情绪 API ──────────────────────────────────────────
@app.route("/api/emotion/<user_id>", methods=["GET"])
def get_emotion(user_id):
    emotion = agent.emotion.get_current(user_id)
    return jsonify({"emotion": emotion})


# ── 历史记录 ──────────────────────────────────────────
@app.route("/chat/history", methods=["GET"])
def history():
    user_id = request.args.get("user_id", "default").strip()
    return jsonify({"messages": agent.get_history(user_id)})

@app.route("/api/history", methods=["GET"])
def api_history():
    return history()

@app.route("/chat/history", methods=["DELETE"])
def clear_history():
    user_id = request.args.get("user_id", "default").strip()
    agent.clear_history(user_id)
    return jsonify({"ok": True})

@app.route("/api/history", methods=["DELETE"])
def api_clear_history():
    return clear_history()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)