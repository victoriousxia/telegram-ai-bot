# Telegram AI Bot

## 项目概述

自建 Telegram Bot，部署在飞牛 NAS（Docker），接入多模型 API 中转站（ai.ilaoxia.cn），支持 OpenAI 和 Anthropic 原生 API 格式。

## 技术栈

- Python 3.11+
- python-telegram-bot v21 (async)
- openai SDK + anthropic SDK
- httpx（拉取模型列表）
- aiosqlite（SQLite 异步访问）
- Docker Compose 部署

## 项目结构

```
bot/
├── main.py              # 入口，注册 handler，启动时拉取模型
├── config.py            # 环境变量解析，Provider 数据结构
├── handlers/
│   ├── commands.py      # /start, /new, /model（inline keyboard）
│   └── chat.py          # 文本消息处理，流式回复
├── services/
│   ├── ai_client.py     # 双格式 API 调用（OpenAI / Anthropic）
│   └── session.py       # 会话 CRUD，消息存取
└── database/
    └── models.py        # SQLite schema 定义 + init_db()
```

## 架构要点

- 多 Provider 配置通过 `PROVIDERS` 环境变量（JSON 数组），每个 provider 有独立的 api_type/base_url/api_key
- models 字段留空时启动自动从 `/v1/models` 拉取
- `config.get_provider_for_model(model)` 根据模型名路由到对应 provider
- 流式输出：先发占位消息，每 ~1s 编辑更新内容，完成后渲染 Markdown
- SQLite 存储 users/sessions/messages 三张表，WAL 模式

## 开发命令

```bash
# 本地运行（需要 .env）
pon -m bot.main

# Docker 构建
docker compose up -d --build

# 查看日志
docker compose logs -f

# 语法检查
python3 -c "import ast; from pathlib import Path; [ast.parse(f.read_terglob('*.py')]"
```

## 部署

- 目标环境：飞牛 NAS，Docker Compose
- 数据持久化：SQLite 文件挂载到 Docker volume `/data/bot.db`
- 仓库地址：https://github.com/victoriousxia/telegram-ai-bot.git
- 一键部署脚本：`deploy.sh`

## 当前状态（v1 已完成）

- [x] /start, /new, /model 命令
- [x] 流式对话
- [x] 多 Provider 支持（OpenAI + Anthropic）
- [x] 自动拉取模型列表
- [x] Docker Compose 部署
- [x] 一键部署脚本 + README 文档

## 后续功能（TODO）

- [ ] Topic 管理：多会话侧边栏切换、重命名、删除
- [ ] /retry 重新生成最后一条回复
- [ ] /undo 撤销最后一条消息
- [ ] /title 设置会话标题
- [ ] /stop 中断生成
- [ ] /compress 上下文压缩（长对话摘要）

## 注意事项

- 不要在代码中硬编码 API Key 或 Token
- Telegram API 编辑消息有频率限制，流式更新间隔不要低于 1s
- Anthropic Messages API 需要把 system 消息从 messages 数组中分离出来单独传
- `callback_data` 长度限制 64 字节，模型名过长时需要考虑截断或映射
