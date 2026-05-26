# Telegram Markdown 渲染模块

将 AI 模型输出的标准 Markdown 转为 Telegram 支持的富文本格式（基于 entities），可复用于任何 python-telegram-bot 项目。

## 依赖

```
telegramify-markdown==1.1.5
python-telegram-bot>=21.0
```

## 文文件：`bot/utils/formatting.py`

## 架构设计

### 为什么不用 MarkdownV2 parse_mode

Telegram 的 MarkdownV2 解析器极其严格，任何未转义的特殊字符都会导致整条消息被拒绝（BadRequest）。我们改用 `telegramify_markdown.convert()` 返回的 `(plain_text, entities)` 直接传给 Telegram API 的 `entities` 参数，绕过 MarkdownV2 字符串解析，渲染 100% 可靠。

### 渲染流程

```
原始 Markdown (模型输出)
    │
    ▼
telegramify_markdown.convert(text)  →  (plain_text, entities)
    │
    ▼
_adjust_spacingext, entities)  →  间距调整
    │
    ▼
_safe_split(text, entities)  →  按段落边界分割，保护代码块
    │
    ▼
_convert_entities(entities)  →  转为 telegram.MessageEntity
    │
    ▼
bot_message.edit_text(text, entities=entities)  →  发送
```

## 核心逻辑详解

### 1. 间距调整 `_adjust_spacing`

telegramify-markdown 库转换后的文本间距不理想，我们基于块级语义做后处理：

**规则：**
- 段落后接 ⦁ 子项列表 → 去掉多余空行（冒号上下文紧凑，如"结果如下：\n⦁ item"束后接非列表内容（标题、段落）→ 插入空行（块级分隔）
- 最后一个 ⦁ 子项后接下一个编号项（如 `2. xxx`）→ 插入空行（编号组分隔）
- 同一列表内部不加额外空行

**
- 所有操作基于 UTF-16 偏移量（Telegram entities 使用 UTF-16 编码）
- 插入/删除换行后需要调整后续所有 entity 的 offset

### 2. 安全分割 `_safe_split`

库自带的 `split_entities()` 会在任意位部（导致树形图被切断）。

**我们的策略：**
- 构建"保护区间"：所有 `pre` entity（代码块）的 offset 范围
- 只在 落边界）处分割，且该位置不在保护区间内
- 贪心算法：每个 chunk 取最后一个不超过 4096 的安全分割点
- 无安全分割点时 fallback 到库的 split_entities

### 3. 列表行判断 `_is_list_line`

判断一行是否为列表项：
- `⦁` 开头（子项，库转换后的无序列表）
- `✔` 开头（已完成 checkbox）
- `☐` 开头（未完成 checkbox）
- `^\d+\. ` 匹配（编号列表，注意点后必须有空格，避免把 `3.2 标题` 误判为列表）

### 4. 流式预览 `convert_for_preview`

流式输出时对不完整的中间文本做轻量渲染：
- 只调用 `convert()`，不做 `_adjust_spacing`（避免不完整文本产生错误间距）
- 失败时 fallback 到纯文本（兼容未闭合代码块等中间状态）
- 文本超过 4096 时不做渲染，直接截断显示尾部

### 5. 符号配置

```python
# 标题：无 emoji 前缀，所有级别只用 bold（不加 underline）
EventWalker._HEADING_ENTITIES = {"H1": ["bold"], "H2": ["bold"], ...}

# 勾选框：统一大小的文本符号（不用 emoji ✅ 避免大小不一致）
_cfg.markdown_symbol.task_completed = "✔"
_cfg.markdown_symbol.task_uncompleted = "☐"

# 分割线：em dash × 18，视觉柔和，手机端不换行
_cfg.markdown_symbol.horizontal_rule = "—" * 18
```

## 已解决的问题清单

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 格式标记直接显示为纯文本 | MarkdownV2 被 Telegram 拒绝 | 改用 entities 方式发送 |
| 标题前有 📌✏📚 emoji | 库默认配置 | 设为空字符串 |
| 勾选框 ✅ 和 ☑ 大小不一致 | emoji vs 文本符号 | 统一用 ✔ 和 ☐ |
| 分割线太短/有间隙/太亮 | 字符选择不当 | 改用 em dash × 18 |
| 标题带下划线 | 库对 h1-h3 默认加 underline | 改为全部只用 bold |
| 列表块后接标题无空行 | 库不做间距处理 | _adjust_spacing 后处理 |
| 段落后接子项列表多余空行 | 库保留了原始空行 | 检测并移除 |
| 编号列表各组之间太紧凑 | 库不区分列表组 | 子项结束后接编号项时插入空行 |
| "3.2 标题" 被误判为列表项 | 正则 `^\d+\.` 太宽泛 | 改为 `^\d+\. `（要求空格） |
| 代码块/树形图被截断 | split_entities 不保护 pre | 自定义 _safe_split |
| 流式输出时无格式 | 只在最终渲染时转换 | convert_for_preview 实时渲染 |
| 手机端分割线换行 | 字符太多 | 缩短到 18 个字符 |

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
