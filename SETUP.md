# AI Girlfriend Agent - 设置指南

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置数据库

编辑 `.env.db` 文件，填入你的MySQL连接信息：

```env
DB_USER=root
DB_PASSWORD=your_password_here
DB_HOST=localhost
DB_PORT=3306
DB_NAME=ai_girlfriend
JWT_SECRET_KEY=your-super-secret-key
```

### 3. 初始化数据库

```bash
python init_db.py
```

这会创建所需的数据库表。

### 4. 迁移旧数据（可选）

如果你之前有JSON格式的数据，可以运行迁移脚本：

```bash
python migrate_data.py
```

### 5. 启动服务

```bash
python -m backend.app
```

服务将在 http://127.0.0.1:8000 启动

### 6. 访问应用

- 打开浏览器访问 http://127.0.0.1:8000
- 首次使用需要注册账号
- 登录后即可开始聊天

---

## 功能说明

### 用户系统
- 用户注册/登录
- JWT Token认证
- 个人资料管理

### 对话功能
- AI女友聊天（带情绪识别）
- 语音合成（TTS）
- 聊天记录持久化

### 记忆系统
- 短期记忆：最近20轮对话
- 长期记忆：用户画像（兴趣、目标等）
- 自动记忆提取

### 主动消息
- 在聊天页开启“主动对话”后，连续10分钟没有聊天才会检查是否发送问候
- 主动消息至少间隔30分钟；关闭开关后停止轮询
- 基于用户画像生成个性化消息

---

## 数据库表结构

### users - 用户表
- id: 用户ID
- username: 用户名（唯一）
- password_hash: 密码哈希
- nickname: 昵称
- created_at: 注册时间
- last_login: 最后登录时间

### messages - 消息表
- id: 消息ID
- user_id: 用户ID
- role: 角色（user/assistant）
- content: 消息内容
- emotion: 情绪
- created_at: 发送时间

### user_profiles - 用户画像表
- id: 画像ID
- user_id: 用户ID（唯一）
- interests: 兴趣爱好（JSON）
- goals: 目标计划（JSON）
- personality: 性格特征（JSON）
- last_chat_time: 最后聊天时间
- active_hours: 活跃时段（JSON）

---

## API接口

### 认证相关
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/profile` - 获取用户信息

### 聊天相关
- `POST /api/chat` - 发送消息（需要token）
- `POST /api/chat/stream` - 流式发送消息（需要token）
- `GET /api/history` - 获取聊天历史（需要token）
- `DELETE /api/history` - 清除聊天历史（需要token）

### 语音相关
- `POST /api/tts` - 语音合成（需要token）

### 主动消息
- `GET /api/proactive` - 获取主动消息（需要token）

---

## 环境变量

### 必需
- `API_KEY` - SiliconFlow API密钥

### 可选（TTS配置）
- `TTS_ENGINE` - TTS引擎（mimo/edge_tts）
- `MIMO_API_KEY` - MiMo API密钥
- `MIMO_TTS_MODEL` - TTS模型
- `MIMO_CLONE_REF_DIR` - 声音克隆参考音频目录

### 数据库配置
- `DB_USER` - MySQL用户名
- `DB_PASSWORD` - MySQL密码
- `DB_HOST` - MySQL主机
- `DB_PORT` - MySQL端口
- `DB_NAME` - 数据库名
- `JWT_SECRET_KEY` - JWT密钥

---

## 常见问题

### Q: 如何重置密码？
A: 目前需要手动修改数据库中的password_hash字段，或重新注册账号。

### Q: 如何备份数据？
A: 备份MySQL数据库即可：
```bash
mysqldump -u root -p ai_girlfriend > backup.sql
```

### Q: 如何切换到其他数据库？
A: 修改 `.env.db` 中的数据库配置，然后重新运行 `init_db.py`。

### Q: 声音克隆不工作？
A: 检查以下配置：
1. `MIMO_API_KEY` 是否正确设置
2. `MIMO_CLONE_REF_DIR` 指向的目录是否存在
3. 参考音频文件是否为WAV格式
