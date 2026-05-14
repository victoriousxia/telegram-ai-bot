# Telegram AI Bot

自建 Telegram Bot，接入多模型 API 中转站，支持 OpenAI 和 Anthropic 原生格式。

## 功能

### 已实现（v1）
- `/start` — 欢迎 + 自动创建会话
- `/new` — 新建对话（清空上下文）
- `/model` — Inline Keyboard 切换模型（按 Provider 分组展示）
- 流式回复（带打字光标，完成后渲染 Markdown）
- 多提供商支持（OpenAI / Anthropic 双格式）
- 启动时自动从 `/v1/models` 拉取可用模型
- SQLite 持久化会话和消息
- Docker Compose 一键部署

### 后续计划
- [ ] Topic 管理：多会话侧边栏切换、重命名、删除
- [ ] `/retry` 重新生成最后一条回复
- [ ] `/undo` 撤销最后一条消息
- [ ] `/title` 设置会话标题
- [ ] `/stop` 中断生成
- [ ] `/compress` 上下文压缩（长对话摘要）

---

## 部署（飞牛 NAS）

### 前置条件
- NAS 已安装 Docker 和 docker compose
- NAS 已安装 Git

### 方式一：一键脚本

```bash
bash <(curl -sSL https://raw.githubusercontent.com/victoriousxia/telegram-ai-bot/main/deploy.sh)
```

首次运行会生成 `.env` 模板并提示你编辑，填好后再跑一次即可启动。

### 方式二：手动部署

```bash
# 克隆
git clone https://github.com/victoriousxia/telegram-ai-bot.git /vol2/docker/telegram-ai-bot
cd /vol2/docker/telegram-ai-bot

# 配置
cp config.example.env .env
nano .env

# 启动
docker compose up -d --build
```

### .env 配置说明

```env
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxx

# 提供商配置（JSON）
# api_type: "openai" 或 "anthropic"
# models: 留空数组 [] 则自动从接口拉取
PROVIDERS='[
  {"name":"openai-relay","api_type":"openai","base_url":"https://ai.ilaoxia.cn/v1","api_key":"sk-xxx","models":[]},
  {"name":"anthropic-relay","api_type":"anthropic","base_url":"https://ai.ilaoxia.cn","api_key":"sk-xxx","models":[]}
]'

# 可选
DEFAULT_MODEL=
ALLOWED_USER_IDS=
STREAM_UPDATE_INTERVAL=1.0
```

---

## 日常维护

```bash
cd /vol1/docker/telegram-ai-bot

# 查看日志
docker compose logs -f

# 重启
docker compose restart

# 停止
docker compose down
```

## 更新版本

```bash
cd /vol1/docker/telegram-ai-bot
git pull origin main
docker compose up -d --build
```

或直接重新运行部署脚本：

```bash
bash <(curl -sSL https://raw.githubusercontent.com/victoriousxia/telegram-ai-bot/main/deploy.sh)
```

---

## 项目结构

```
bot/
├── main.py              # 入口
├── config.py            # 配置（环境变量 + Provider 解析）
├── handlers/
│   ├── commands.py      # /start, /new, /model
│   └── chat.py          # 消息处理 + 流式回复
├── services/
│   ├── ai_client.py     # OpenAI/Anthropic 双格式调用
│   └── session.py       # 会话 CRUD
└── database/
    └── models.py        # SQLite schema + init
```
