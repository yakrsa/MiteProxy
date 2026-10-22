"""SSE（Server-Sent Events，`text/event-stream`）解析（路线图 #8）。

按 WHATWG SSE 规范的字段语法切事件流：
- 一行一个字段 ``field: value``（value 前一个空格要剥掉）；
- 空行 = 派发一个事件（``data`` 多行用 ``\\n`` 连接）；
- ``:`` 开头是注释，忽略；
- 认识的字段：``event`` / ``data`` / ``id`` / ``retry``，其余忽略。

设计约束：
1. **迭代不递归**：一次解析整条流，行数上限防失控（流式响应可能很长）；
2. **区分「完整」与「没收尾」**：响应仍在进行时最后一段没有空行收尾，
   调用方要能提示用户「最后一个事件可能不完整」，不能默默显示半截；
3. **纯逻辑不依赖 Qt**：解析与 UI 分离，单测不需要 QApplication；
4. 乱码 / 超长行不抛异常——按字符截断并继续，展示层另有总量上限。
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: 单次解析的最大行数：流式响应理论上是无限的，UI 只需要最近一段
MAX_LINES = 20_000
#: 单个字段值的最大字符数（防某行 data 长到几十 MB）
MAX_FIELD_CHARS = 64 * 1024
#: 事件数上限：超出即停（trailing_incomplete 仍如实标注）
MAX_EVENTS = 2_000

#: SSE 的 content-type（可能带 `;charset=utf-8` 参数）
SSE_CONTENT_TYPE = "text/event-stream"


def is_sse(content_type: str) -> bool:
    """content-type 是否是 SSE。"""
    return SSE_CONTENT_TYPE in (content_type or "").lower()


@dataclass
class SseEvent:
    """一个 SSE 事件。

    data 已是多行拼接后的文本（规范语义：每个 data 行之间一个 \\n）；
    complete=False = 这段是流尾巴上没收尾的（响应可能仍在写）。
    """

    index: int                  # 从 1 开始的事件序号
    event: str = ""             # event 字段（默认 "message" 由展示层决定）
    data: str = ""
    id: str = ""
    retry: str = ""
    complete: bool = True

    @property
    def has_fields(self) -> bool:
        return bool(self.event or self.data or self.id or self.retry)


@dataclass
class SseResult:
    events: list[SseEvent] = field(default_factory=list)
    #: 流的最后一段没有空行收尾（响应仍在进行 / 被截断）
    trailing_incomplete: bool = False
    #: 事件数达到上限被截断
    truncated: bool = False
    #: 解析的行数（超出 MAX_LINES 时后续行被丢弃）
    lines_seen: int = 0


def _split_field(line: str) -> tuple[str, str]:
    """``field: value`` → (field, value)；无冒号时整行是 field、value 为空。"""
    colon = line.find(":")
    if colon < 0:
        return line, ""
    field_name = line[:colon]
    value = line[colon + 1:]
    if value.startswith(" "):
        value = value[1:]       # 规范：剥掉值前的一个空格
    return field_name, value


def parse_sse(text: str, max_events: int = MAX_EVENTS) -> SseResult:
    """解析 SSE 文本 → 事件列表。

    ``max_events`` 超出即停并标 truncated；行数超 MAX_LINES 同样截断。
    任何畸形输入都不抛异常——这是抓包工具的兜底职责。
    """
    result = SseResult()
    if not text:
        return result

    event = SseEvent(index=1)
    data_lines: list[str] = []
    seen_fields = False

    def _dispatch() -> None:
        nonlocal event, data_lines, seen_fields
        if seen_fields:
            event.data = "\n".join(data_lines)
            if len(result.events) < max_events:
                result.events.append(event)
            else:
                result.truncated = True
            event = SseEvent(index=len(result.events) + 1)
            data_lines = []
            seen_fields = False

    lines = text.splitlines()
    result.lines_seen = len(lines)
    if len(lines) > MAX_LINES:
        result.truncated = True
        lines = lines[:MAX_LINES]
    for raw in lines:
        if not raw:
            # 空行：派发。没收尾过任何字段（连续空行）时什么都不做
            _dispatch()
            continue
        if raw.startswith(":"):
            continue                    # 注释行（保活 / 心跳常见）
        name, value = _split_field(raw)
        if len(value) > MAX_FIELD_CHARS:
            value = value[:MAX_FIELD_CHARS]
        seen_fields = True
        if name == "data":
            data_lines.append(value)
        elif name == "event":
            event.event = value
        elif name == "id":
            event.id = value
        elif name == "retry":
            event.retry = value
        # 其余字段按规范忽略

    # 流尾巴：最后一段没有空行收尾 → 仍然展示，但标注不完整
    if seen_fields:
        result.trailing_incomplete = True
        event.data = "\n".join(data_lines)
        event.complete = False
        if len(result.events) < max_events:
            result.events.append(event)
        else:
            result.truncated = True
    return result
