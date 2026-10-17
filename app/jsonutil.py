"""JSON 解析 / 格式化 / 错误定位（纯函数，不依赖 Qt）。

给「JSON 工具页」用，也吸取了 body 视图上踩过的坑：

1. **`RecursionError` 必须单独接**——`json.loads("[[[[…]]]]")` 抛它，而它
   **不是 `ValueError` 的子类**，漏接就是整个界面崩掉。
2. **先完整解析、只截断渲染结果**。早期实现先按 512KB 截断再解析，结果任何
   大于 512KB 的 JSON 都被截成半截、解析失败，用户反而看到一句"解析失败"。
   解析本身很便宜（4MB ≈ 30ms），卡的是渲染，所以闸门要放在渲染侧。
3. **失败绝不吞内容**：非法 JSON 时 `value` 保持原文可显示，错误信息另给。
4. **错误信息要能定位到人**：给行、列、出错行原文和 `^` 指针，再附一句
   「可能是……」——只丢一句 `Expecting ',' delimiter` 用户还是不知道改哪。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

#: 出错行太长了就只显示出错位置附近这一段（两侧各留这么多字符）
SNIPPET_CONTEXT = 60
SNIPPET_MAX = 160


class JsonStrictError(ValueError):
    """严格模式下的非法常量（NaN / Infinity）——浏览器 JSON.parse 也不认。"""


@dataclass(frozen=True)
class JsonError:
    """一处解析错误：能定位、能解释。"""

    message: str
    lineno: int = 0       # 1-based，0 = 未知
    colno: int = 0        # 1-based
    snippet: str = ""     # 出错行 + 指针
    hint: str = ""        # 「可能是……」

    @property
    def location(self) -> str:
        if not self.lineno:
            return ""
        if not self.colno:
            return QCoreApplication.translate("jsonutil", '第 {0} 行').format(self.lineno)
        return QCoreApplication.translate("jsonutil", '第 {0} 行第 {1} 列').format(self.lineno, self.colno)

    def report(self) -> str:
        """给人看的完整报告（UI 直接显示这个）。"""
        parts = []
        head = f"{self.location}：{self.message}" if self.location else self.message
        parts.append(head)
        if self.snippet:
            parts.append(self.snippet)
        if self.hint:
            parts.append(QCoreApplication.translate("jsonutil", '可能原因：{0}').format(self.hint))
        return "\n".join(parts)


@dataclass
class ParseResult:
    ok: bool
    value: object = None
    error: JsonError | None = None
    #: 不致命但需要提醒（如重复 key）
    notes: tuple[str, ...] = ()
    #: 原文（非法时供 UI 显示，保证内容不丢）
    text: str = ""


# ---------------------------------------------------------------- 提示映射

#: json 的原始消息 → 人话。按顺序匹配子串，先命中先用。
#: NOOP 打标：同 bodyview.VIEW_MODE_ITEMS，本模块在翻译器装载前被 import，
#: 模块级 translate 只会拿到中文。翻译在 hint_for() 运行时做。
_HINTS: tuple[tuple[str, str], ...] = (
    (
        "Expecting property name enclosed in double quotes",
        QT_TRANSLATE_NOOP("jsonutil", "对象的 key 必须用双引号（单引号不行），或这里多了个尾逗号"),
    ),
    (
        "Expecting ',' delimiter",
        QT_TRANSLATE_NOOP("jsonutil", "两个值之间少了逗号，或者多了个尾逗号"),
    ),
    (
        "Expecting ':' delimiter",
        QT_TRANSLATE_NOOP("jsonutil", "key 后面少了冒号"),
    ),
    (
        "Illegal trailing comma",
        QT_TRANSLATE_NOOP("jsonutil", "对象或数组末尾多了个逗号（标准 JSON 不允许尾逗号）"),
    ),
    (
        "Expecting value",
        QT_TRANSLATE_NOOP("jsonutil", "这里应该是一个值：常见原因是单引号字符串、写了注释、多了尾逗号，或内容为空"),
    ),
    (
        "Unterminated string",
        QT_TRANSLATE_NOOP("jsonutil", "字符串的引号没有闭合；字符串里要换行得写成 \\n"),
    ),
    (
        "Invalid control character",
        QT_TRANSLATE_NOOP("jsonutil", "字符串里有未转义的控制字符（比如直接按了回车），应写成 \\n / \\t"),
    ),
    (
        "Invalid \\escape",
        QT_TRANSLATE_NOOP("jsonutil", "转义序列不合法，\\\\ 才表示一个反斜杠"),
    ),
    (
        "Invalid \\uXXXX escape",
        QT_TRANSLATE_NOOP("jsonutil", "\\u 后面必须跟 4 位十六进制"),
    ),
    (
        "Extra data",
        QT_TRANSLATE_NOOP("jsonutil", "第一个 JSON 结束后还有多余内容：可能是 JSONP 包裹，或多个 JSON 拼在一起"),
    ),
    (
        "Delimiter",
        QT_TRANSLATE_NOOP("jsonutil", "分隔符位置不对，检查逗号与冒号"),
    ),
)


def hint_for(message: str) -> str:
    for needle, hint in _HINTS:
        if needle in message:
            return QCoreApplication.translate("jsonutil", hint)
    return ""


# ---------------------------------------------------------------- 片段


def error_snippet(text: str, lineno: int, colno: int) -> str:
    """出错行 + `^` 指针。行长超限就只显示出错位置附近的一段。"""
    lines = text.splitlines()
    if not (1 <= lineno <= len(lines)):
        return ""
    line = lines[lineno - 1]
    col = max(colno - 1, 0)

    prefix_len = len(str(lineno))
    gutter = " " * prefix_len + " | "

    if len(line) > SNIPPET_MAX:
        start = max(0, col - SNIPPET_CONTEXT)
        end = min(len(line), start + SNIPPET_MAX)
        window = line[start:end]
        head = "…" if start > 0 else ""
        tail = "…" if end < len(line) else ""
        pointer = " " * ((1 if head else 0) + (col - start)) + "^"
        return f"{lineno} | {head}{window}{tail}\n{gutter}{pointer}"

    return f"{lineno} | {line}\n{gutter}{' ' * col}^"


# ---------------------------------------------------------------- 解析


def _reject_constant(name: str) -> object:
    raise JsonStrictError(QCoreApplication.translate("jsonutil", '不合法的 JSON 常量：{0}').format(name))


def parse_json(text: str, *, strict: bool = True) -> ParseResult:
    """解析 JSON。失败时 `value` 为 None、`error` 给出定位与原因。

    `strict=True` 时拒绝 `NaN` / `Infinity`（Python 的 json 默认接受，但
    `JSON.parse` 不接受——对齐 json.cn 的行为，免得"这里能解、前端报错")。
    """
    raw = text
    cleaned = text.lstrip("\ufeff") if text.startswith("\ufeff") else text
    if not cleaned.strip():
        return ParseResult(
            False,
            error=JsonError(QCoreApplication.translate("jsonutil", "内容为空"), 1, 1, hint=QCoreApplication.translate("jsonutil", "先贴一段 JSON 进来")),
            text=raw,
        )

    duplicates: list[str] = []

    def pairs_hook(pairs):
        keys = [k for k, _ in pairs]
        seen: set[str] = set()
        for key in keys:
            if key in seen and key not in duplicates:
                duplicates.append(key)
            seen.add(key)
        return dict(pairs)

    try:
        kwargs = {"object_pairs_hook": pairs_hook}
        if strict:
            kwargs["parse_constant"] = _reject_constant
        value = json.loads(cleaned, **kwargs)
    except JsonStrictError as exc:
        return ParseResult(
            False,
            error=JsonError(
                str(exc),
                hint=QCoreApplication.translate("jsonutil", "浏览器 JSON.parse 也不认它；要表示空值就用 null"),
            ),
            text=raw,
        )
    except RecursionError:
        # 深嵌套：不是 ValueError 的子类，必须单独接
        return ParseResult(
            False,
            error=JsonError(
                QCoreApplication.translate("jsonutil", "嵌套层级过深，超出解析器递归上限"),
                hint=QCoreApplication.translate("jsonutil", "确认内容没被意外重复包裹；可用 JSONPath 先缩小范围"),
            ),
            text=raw,
        )
    except json.JSONDecodeError as exc:
        lineno = getattr(exc, "lineno", 0) or 0
        colno = getattr(exc, "colno", 0) or 0
        message = str(exc).split(": line")[0].strip() or exc.msg
        return ParseResult(
            False,
            error=JsonError(
                message,
                lineno,
                colno,
                error_snippet(cleaned, lineno, colno),
                hint_for(message),
            ),
            text=raw,
        )
    except (ValueError, MemoryError) as exc:
        return ParseResult(False, error=JsonError(str(exc)), text=raw)

    notes: list[str] = []
    if duplicates:
        shown = "、".join(duplicates[:5])
        more = "…" if len(duplicates) > 5 else ""
        notes.append(QCoreApplication.translate("jsonutil", '存在重复 key：{0}{1}（已保留最后一次出现）').format(shown, more))
    return ParseResult(True, value=value, notes=tuple(notes), text=raw)


# ---------------------------------------------------------------- 序列化


def dumps_json(value: object, indent: int | None = 2) -> tuple[bool, str]:
    """序列化。返回 `(是否成功, 文本)`，失败时文本是原因。

    `ensure_ascii=False`：中文原样输出，不变成 `\\uXXXX`。
    不排序 key：保持原顺序，方便和线上对照。
    """
    try:
        if indent is None:      # 压缩：默认的 ", " / ": " 分隔符得去掉
            return True, json.dumps(
                value, ensure_ascii=False, separators=(",", ":")
            )
        return True, json.dumps(value, ensure_ascii=False, indent=indent)
    except RecursionError:
        return False, QCoreApplication.translate("jsonutil", "嵌套层级过深，无法序列化")
    except (ValueError, TypeError, MemoryError) as exc:
        return False, QCoreApplication.translate("jsonutil", '序列化失败：{0}').format(exc)


# ---------------------------------------------------------------- 规模统计


def count_nodes(value: object, limit: int = 200_000) -> int:
    """节点总数（迭代实现，深嵌套不会爆栈）。"""
    total = 0
    stack = [value]
    while stack:
        if total >= limit:
            return total
        item = stack.pop()
        total += 1
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return total


def max_depth(value: object) -> int:
    """最大嵌套深度（迭代实现）。"""
    depth = 0
    stack = [(value, 1)]
    while stack:
        item, level = stack.pop()
        if level > depth:
            depth = level
        if isinstance(item, dict):
            stack.extend((v, level + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, level + 1) for v in item)
    return depth
