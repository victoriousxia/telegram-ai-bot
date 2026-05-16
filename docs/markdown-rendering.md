# Telegram Markdown 渲染模块

将 AI 模型输出的标准 Markdown 转为 Telegram 支持的富文本格式（基于 entities），可复用于任何 python-telegram-bot 项目。

## 依赖

```
telegramify-markdown==1.1.5
python-telegram-bot>=21.0
```

## 文件

核心文件：`bot/utils/formatting.py`

## API

### `split_message(text: str) -> list[tuple[str, list[MessageEntity]]]`

完整渲染：将 markdown 文本转为 (plain_text, entities) 列表，自动处理：
- 间距调整（列表块分隔、段落与子项紧凑）
- 智能分割（不切断代码块，在段落边界分割）
- 超长消息自动拆分为多条（每条 <= 4096 UTF-16 单元）

```python
from bot.utils.formatting import split_message

chunks = split_message(ai_response)
for text, entities in chunks:
    await message.reply_text(text, entities=entities)
```

### `convert_for_preview(text: str) -> tuple[str, list[MessageEntity]]`

轻量渲染：用于流式预览，不做间距调整，适合不完整的中间文本。

```python
from bot.utils.formatting import convert_for_preview

text, entities = convert_for_preview(partial_response)
await bot_message.edit_text(text + " ▍", entities=entities)
```

## 流式输出集成示例

```python
import time
from bot.utils.formatting import split_message, convert_for_preview

TELEGRAM_MAX_LENGTH = 4096

async def stream_and_send(stream, bot_message, chat):
    full_response = ""
    last_update = time.time()

    async for chunk in stream:
        full_response += chunk
        now = time.time()
        if now - last_update >= 1.0:
            if len(full_response) > TELEGRAM_MAX_LENGTH - 4:
                # 超长时 fallback 纯文本截断
                preview = "… " + full_response[-(TELEGRAM_MAX_LENGTH - 4):]
                await bot_message.edit_text(preview + " ▍")
            else:
                # 实时 markdown 渲染
                try:
                    text, entities = convert_for_preview(full_response)
                    await bot_message.edit_text(text + " ▍", entities=entities)
                except Exception:
                    await bot_message.edit_text(full_response + " ▍")
            last_update = now

    # 最终完整渲染
    chunks = split_message(full_response)
    for i, (text, entities) in enumerate(chunks):
        if i == 0:
            await bot_message.edit_text(text, entities=entities)
        else:
            await chat.send_message(text, entities=entities)
```

## 支持的 Markdown 元素

| Markdown 语法 | Telegram 渲染效果 |
|---|---|
| `# 标题` / `## 标题` / `### 标题` | **加粗** |
| `**粗体**` | **粗体** |
| `*斜体*` | *斜体* |
| `` `行内代码` `` | `等宽字体` |
| ` ```代码块``` ` | 代码块（支持语言标注） |
| `- 列表` | ⦁ 列表 |
| `1. 编号` | 1. 编号 |
| `- [x]` / `- [ ]` | ✔ / ☐ |
| `~~删除线~~` | ~~删除线~~ |
| `[链接](url)` | 可点击链接 |
| `---` | —————————————————— |
| 表格 | 等宽对齐文本 |

## 自定义配置

文件顶部可调整：

```python
# 标题前缀符号（默认为空，即无 emoji）
_cfg.markdown_symbol.heading_level_1 = ""

# 勾选框样式
_cfg.markdown_symbol.task_completed = "✔"
_cfg.markdown_symbol.task_uncompleted = "☐"

# 分割线样式和长度
_cfg.markdown_symbol.horizontal_rule = "—" * 18
```

## 适配其他 bot 框架

如果使用 aiogram 或其他框架，修改 `_convert_entities` 函数中的 `TgEntity` 为对应框架的 MessageEntity 类即可。
