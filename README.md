# AI 陪伴聊天应用

一个使用 Flask、MySQL 和 OpenAI 兼容 API 构建的中文 AI 陪伴应用。提供账号登录、流式聊天、对话记忆、主动对话开关、语音输入，以及可试听和切换的多种回复声线。

## 功能一览

### 账号和个人资料

- 注册、登录和 JWT 令牌认证。
- 用户资料支持昵称、兴趣和目标。
- MySQL 保存账号和个人资料；按用户 ID 分开的 JSON 文件保存聊天上下文和长期记忆。

### AI 聊天和记忆

- 通过兼容 OpenAI Chat Completions 的模型接口生成回复。
- 支持流式回复、对话情绪识别，以及安慰、聊天、故事等对话技能。
- 短期记忆保存近期对话（默认最多 20 条消息），启动后可重新加载；会话超过 10 天时会尝试压缩较早的对话。
- 长期记忆记录对话中整理出的用户兴趣、目标等信息。
- 页面加载时可恢复该账号对应的历史聊天；可清除当前账号的聊天记录。

### 主动对话

- 页面顶部的“主动对话”开关默认关闭；状态按账号保存在当前浏览器。
- 开启后，页面每 30 秒向服务端检查一次；需要页面保持打开并已登录。
- 连续 10 分钟没有新聊天时，Agent 根据近期上下文决定是否发起问候；两次主动决策至少间隔 30 分钟。
- 主动消息会显示在聊天页面，并尝试使用当前选择的声线播放。

### 页面与语音

- 深色卡片式桌面界面，并适配手机屏幕。
- 可以修改聊天页面显示的 AI 名称；设置仅保存在当前设备/浏览器，不会更改模型人格设定，也不会同步到其他设备。
- 支持浏览器语音输入；可用性取决于浏览器的语音识别支持和安全上下文（HTTPS 或 localhost）。
- 回复声线可选择：
  - Edge TTS：晓晓、晓伊、云希、云扬、云健、云夏。
  - “我的合成声线（MiMo）”：使用本机配置的参考音频和 MiMo voice-clone API。
  - Ayaka_RVC：通过单独运行的本机 RVC sidecar 合成。
- “试听”按钮可测试当前选择的声线；服务器默认回复声线为 Edge TTS 晓晓。

## 环境要求

- Python 3.10 或更新版本；RVC sidecar 建议使用独立的 Python 3.11 环境。
- MySQL 服务。
- 可调用的 OpenAI 兼容聊天模型 API，以及对应的 API Key。
- MiMo 和 Ayaka_RVC 是可选声线，会分别需要 MiMo API 配置/参考音频或本地 RVC 模型文件。

## Windows 快速开始

在项目根目录运行 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item .env.db.example .env.db
```

编辑 `.env` 和 `.env.db`，填写聊天模型 API、MySQL 连接信息以及随机生成的 `JWT_SECRET_KEY`。启动 MySQL 后：

```powershell
python init_db.py
python -m backend.app
```

打开 <http://127.0.0.1:8000>，注册账号并登录。

也可以在 Windows 上运行 `start.bat` 启动 Flask 服务。部署到其他环境时，请使用适合生产环境的 WSGI 服务，不要开启 Flask 调试模式对公网提供服务。

## 语音配置

### Edge TTS

Edge TTS 声线由服务端调用，无需下载模型文件。依赖已列在 `requirements.txt`；服务器需要能够访问 Edge TTS 服务。

### MiMo 自定义声线

1. 在 `.env` 中配置 `MIMO_API_KEY`、`MIMO_BASE_URL` 和 `MIMO_TTS_MODEL`。
2. 准备自己的 WAV/MP3 参考音频，并将其保存在本机；配置 `MIMO_TTS_VOICE` 或 `MIMO_CLONE_REF_DIR`。
3. 网页选择“我的合成声线（MiMo）”，点击“试听”检查效果。

参考音频包含在克隆请求中；请勿把个人录音或 API Key 上传到 Git。

### Ayaka_RVC 本地模型（可选）

需要独立 Python 3.11 环境、模型权重和索引文件，以及运行中的本机 RVC sidecar。模型不随此仓库分发。详细安装命令、模型来源和许可说明见 [VOICE_MODELS.md](VOICE_MODELS.md)。

## 配置文件

- `.env.example`：聊天模型、MiMo 和语音合成配置模板。
- `.env.db.example`：MySQL 和 JWT 配置模板。
- `requirements.txt`：Web 应用运行依赖。
- `requirements-rvc.txt`：单独 RVC 环境的依赖。
- [SETUP.md](SETUP.md)：数据库、API 和服务设置详情。
- [VOICE_MODELS.md](VOICE_MODELS.md)：声线选择、模型准备及 RVC 说明。

## 主要 API

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/auth/register` | 注册账号 |
| `POST` | `/api/auth/login` | 登录 |
| `GET` / `PUT` | `/api/auth/profile` | 查询或更新个人资料 |
| `POST` | `/api/chat/stream` | 流式聊天 |
| `POST` | `/api/chat` | 非流式聊天 |
| `GET` / `DELETE` | `/api/history` | 读取或清除聊天历史 |
| `POST` | `/api/tts` | 合成选定声线 |
| `GET` | `/api/proactive` | 检查是否有主动消息 |

## 隐私与安全

- `.env`、`.env.db`、数据库、日志、聊天记忆文件、参考音频及模型权重均属于本地数据，不应提交到 Git。
- API Key、数据库密码和 JWT 密钥应使用自己的强随机值；示例文件中的值只是占位符。
- 默认 Flask 开发服务器仅适合本地开发。公开部署前应配置 HTTPS、访问控制、生产级 WSGI 服务，并评估聊天及历史接口的认证与网络暴露策略。
- Ayaka_RVC 权重的来源与非商业许可要求见 [VOICE_MODELS.md](VOICE_MODELS.md)；模型不包含在本仓库中。
