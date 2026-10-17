"""轻量 JSONPath 提取（纯函数，不依赖 Qt）。

只实现调试时真正会用的那部分语法，宁可少而准：

| 写法 | 含义 |
|---|---|
| `$` | 根 |
| `$.a.b`、`$['a']['b']` | 取字段（点号只能跟简单 key，括号里能带特殊字符） |
| `$[0]`、`$[-1]` | 数组下标（支持负号） |
| `$[1:3]`、`$[:2]`、`$[1:]` | 切片（不含右端） |
| `$[*]`、`$.*` | 通配：所有元素 / 所有值 |
| `$..name`、`$..*` | 递归下降：所有层级里叫 name 的字段 / 所有节点 |
| `$[?(expr)]` | 过滤：`== != > >= < <= =~`，`&&` / `||` 组合 |
| `$['a','b']`、`$[0,1]` | 联合：一次取多个 |
| `.length()` / `.min()` / `.max()` | 聚合函数（须带括号，与名字恰好的字段不冲突）：`length()` 对单个数组/对象/字符串取其长度、对多个命中计条数；`min()`/`max()` 对单个数组取其数字极值、对多个命中取全体数字极值 |

不做的：脚本表达式、step 切片、正则之外的模糊匹配。
这些在抓包调试里用得极少，做进来只会让报错更难懂。

两条安全约束：
- 递归下降与树遍历都用**迭代**实现——接口返回的嵌套可能很深，递归会爆栈
  （`RecursionError` 不是 `ValueError` 的子类，漏接就是界面崩掉）。
- 结果条数有上限，防止 `$..*` 命中几十万节点把界面拖死。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from PySide6.QtCore import QCoreApplication

#: 单次提取最多返回多少条（再多只统计不展示）
MAX_MATCHES = 2000

#: 递归下降时最多遍历多少节点
MAX_WALK_NODES = 200_000


class JsonPathError(ValueError):
    """JSONPath 语法错误，带出错位置。"""

    def __init__(self, message: str, pos: int = 0):
        super().__init__(message)
        self.pos = pos

    def describe(self, expr: str) -> str:
        """带上出错位置与指针，和 JSON 的错误提示保持一致的手感。"""
        pos = min(max(self.pos, 0), len(expr))
        pointer = " " * pos + "^"
        return QCoreApplication.translate("JsonPath", 'JSONPath 语法错误（第 {0} 个字符）：{1}\n{2}\n{3}').format(pos + 1, self, expr, pointer)


@dataclass(frozen=True)
class Match:
    path: str
    value: object


# ---------------------------------------------------------------- 选择器

@dataclass(frozen=True)
class Key:
    name: str


@dataclass(frozen=True)
class Index:
    index: int


@dataclass(frozen=True)
class Slice:
    start: int | None
    stop: int | None


@dataclass(frozen=True)
class Wildcard:
    pass


@dataclass(frozen=True)
class Recursive:
    """`..name` / `..*`：递归下降收集所有匹配节点。"""
    name: str | None = None     # None = `..*`


@dataclass(frozen=True)
class Filter:
    expr: str


@dataclass(frozen=True)
class Union:
    items: tuple


@dataclass(frozen=True)
class Function:
    """聚合函数：`length()` / `min()` / `max()`。

    对**整个选择器结果**生效（不是逐节点）：`$.a.max()` 取数组 a 的极值，
    `$.a[*].price.max()` 取所有 price 的极值——后者才是抓包调试里的常用形态。
    """

    name: str


#: 支持的聚合函数
FUNCTIONS = ("length", "min", "max")


def _fmt_key(name: str) -> str:
    if re.match(r"^[A-Za-z_$][\w$]*$", name):
        return f".{name}"
    return f"['{name}']"


# ---------------------------------------------------------------- 词法/语法

_IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
_INT_RE = re.compile(r"-?\d+")


class _Parser:
    def __init__(self, expr: str):
        self.s = expr
        self.i = 0

    # -- 工具

    def _skip_ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1

    def _eof(self) -> bool:
        return self.i >= len(self.s)

    def _peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def _fail(self, message: str) -> JsonPathError:
        return JsonPathError(message, self.i)

    # -- 入口

    def parse(self) -> list:
        self._skip_ws()
        if self._peek() not in ("$", "@"):
            raise self._fail(QCoreApplication.translate("JsonPath", "必须以 $ 开头（如 $.data.list[0]）"))
        if self._peek() == "@":
            raise self._fail(QCoreApplication.translate("JsonPath", "最外层请用 $ 而不是 @（@ 只在过滤器里表示当前元素）"))
        self.i += 1
        selectors: list = []
        while not self._eof():
            self._skip_ws()
            if self._eof():
                break
            ch = self._peek()
            if ch == ".":
                selectors.append(self._parse_dot())
            elif ch == "[":
                selectors.append(self._parse_bracket())
            else:
                raise self._fail(QCoreApplication.translate(
                    "JsonPath", "无法识别的 {0}：字段前要有 . 或 [").format(repr(ch)))
        return selectors

    def _parse_dot(self) -> object:
        start = self.i
        self.i += 1                     # 吃掉第一个 .
        if self._peek() == ".":
            self.i += 1                 # `..` 递归下降
            if self._peek() == "*":
                self.i += 1
                return Recursive(None)
            m = _IDENT_RE.match(self.s, self.i)
            if not m:
                raise self._fail(QCoreApplication.translate("JsonPath", ".. 后面要跟字段名或 *（如 $..id）"))
            self.i = m.end()
            return Recursive(m.group(0))
        if self._peek() == "*":
            self.i += 1
            return Wildcard()
        m = _IDENT_RE.match(self.s, self.i)
        if not m:
            raise self._fail(QCoreApplication.translate("JsonPath", ". 后面要跟字段名或 *（如 $.data）"))
        self.i = m.end()
        if start == self.i:
            raise self._fail(QCoreApplication.translate("JsonPath", "空的字段访问"))
        name = m.group(0)
        # `length()` / `min()` / `max()`：带括号才是函数，
        # 字段恰巧叫 length 的（$.a.length）不受影响
        if name in FUNCTIONS and self.s[self.i : self.i + 2] == "()":
            self.i += 2
            return Function(name)
        return Key(name)

    def _parse_bracket(self) -> object:
        self.i += 1                     # 吃掉 [
        self._skip_ws()

        if self._peek() == "?":
            return self._parse_filter()

        content, end = self._read_until_bracket()
        self.i = end + 1                # 吃掉 ]
        body = content.strip()
        if not body:
            raise self._fail(QCoreApplication.translate("JsonPath", "[] 里是空的"))

        parts = self._split_union(body)
        if len(parts) > 1:
            return Union(tuple(self._parse_simple(p) for p in parts))
        return self._parse_simple(body)

    def _read_until_bracket(self) -> tuple[str, int]:
        """读到配对的 `]`，引号内的括号不算。"""
        depth = 0
        quote = ""
        j = self.i
        while j < len(self.s):
            ch = self.s[j]
            if quote:
                if ch == "\\":
                    j += 2
                    continue
                if ch == quote:
                    quote = ""
                j += 1
                continue
            if ch in "'\"":
                quote = ch
            elif ch == "[":
                depth += 1
            elif ch == "]":
                if depth == 0:
                    return self.s[self.i : j], j
                depth -= 1
            j += 1
        raise self._fail(QCoreApplication.translate("JsonPath", "缺少配对的 ]"))

    def _split_union(self, body: str) -> list[str]:
        """按顶层逗号切分（引号内的逗号不算）。"""
        parts: list[str] = []
        buf: list[str] = []
        quote = ""
        for ch in body:
            if quote:
                buf.append(ch)
                if ch == quote:
                    quote = ""
                continue
            if ch in "'\"":
                quote = ch
                buf.append(ch)
            elif ch == ",":
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        parts.append("".join(buf).strip())
        return [p for p in parts if p]

    def _parse_simple(self, token: str) -> object:
        if token == "*":
            return Wildcard()
        if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
            return Key(token[1:-1])
        if ":" in token:
            return self._parse_slice(token)
        if _INT_RE.fullmatch(token):
            return Index(int(token))
        if _IDENT_RE.fullmatch(token):
            return Key(token)
        raise self._fail(QCoreApplication.translate("JsonPath", '无法识别的 [{0}]').format(token))

    def _parse_slice(self, token: str) -> Slice:
        parts = token.split(":")
        if len(parts) > 2:
            raise self._fail(QCoreApplication.translate("JsonPath", "暂不支持带步长的切片（如 [::2]）"))
        def num(text: str) -> int | None:
            text = text.strip()
            if not text:
                return None
            if not _INT_RE.fullmatch(text):
                raise self._fail(QCoreApplication.translate(
                    "JsonPath", "切片的 {0} 不是整数").format(repr(text)))
            return int(text)
        return Slice(num(parts[0]), num(parts[1]))

    def _parse_filter(self) -> Filter:
        self.i += 1                     # 吃掉 ?
        self._skip_ws()
        if self._peek() != "(":
            raise self._fail(QCoreApplication.translate("JsonPath", "? 后面要跟 ( 表达式 )，如 $[?(@.price > 10)]"))
        depth = 0
        quote = ""
        j = self.i
        start = j
        while j < len(self.s):
            ch = self.s[j]
            if quote:
                if ch == "\\":
                    j += 2
                    continue
                if ch == quote:
                    quote = ""
            elif ch in "'\"":
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth != 0:
            raise self._fail(QCoreApplication.translate("JsonPath", "过滤器缺少配对的 )"))
        expr = self.s[start + 1 : j]
        self.i = j + 1
        self._skip_ws()
        if self._peek() != "]":
            raise self._fail(QCoreApplication.translate("JsonPath", "过滤器后面要跟 ]"))
        self.i += 1
        if not expr.strip():
            raise self._fail(QCoreApplication.translate("JsonPath", "过滤器是空的，如 $[?(@.price > 10)]"))
        return Filter(expr)


def parse(expr: str) -> list:
    return _Parser(expr).parse()


# ---------------------------------------------------------------- 过滤器求值

_OPS = ("==", "!=", ">=", "<=", "=~", ">", "<")


def _literal(token: str) -> object:
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
        return token[1:-1]
    if token in ("true", "false"):
        return token == "true"
    if token == "null":
        return None
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    return token


def _resolve_field(node, parts: list[str]):
    current = node
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.lstrip("-").isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def _compare(left, op: str, right) -> bool:
    if op == "=~":
        try:
            return re.search(str(right), str(left)) is not None
        except re.error:
            return False
    if op in (">", ">=", "<", "<="):
        # 一边是数字一边是数字字符串时按数字比，否则按 Python 默认规则
        if isinstance(left, (int, float)) and isinstance(right, str):
            try:
                right = float(right)
            except ValueError:
                return False
        elif isinstance(right, (int, float)) and isinstance(left, str):
            try:
                left = float(left)
            except ValueError:
                return False
    try:
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "<":
            return left < right
        return left <= right
    except TypeError:
        return False


def _eval_condition(node, condition: str) -> bool:
    """` @.a == 1 ` 这类单条件。"""
    for op in _OPS:
        if op in condition:
            left, right = condition.split(op, 1)
            break
    else:
        # 没有比较符 → 存在性判断
        return _resolve_field(node, _field_parts(condition)) is not None

    parts = _field_parts(left)
    if not parts:
        raise JsonPathError(QCoreApplication.translate(
            "JsonPath", "过滤器左边要以 @ 开头：{0}").format(repr(condition.strip())))
    return _compare(_resolve_field(node, parts), op, _literal(right))


def _field_parts(text: str) -> list[str]:
    """`@.a.b` / `@['a']` → ['a', 'b']；不是 @ 开头时返回 []。"""
    text = text.strip()
    if not text.startswith("@"):
        return []
    text = text[1:].strip()
    parts: list[str] = []
    while text:
        if text.startswith("."):
            text = text[1:]
            m = _IDENT_RE.match(text)
            if not m:
                raise JsonPathError(QCoreApplication.translate(
                "JsonPath", "过滤器里的字段名不合法：{0}").format(repr(text)))
            parts.append(m.group(0))
            text = text[m.end():]
        elif text.startswith("["):
            end = text.find("]")
            if end < 0:
                raise JsonPathError(QCoreApplication.translate("JsonPath", "过滤器里的 [ 缺少配对的 ]"))
            token = text[1:end].strip()
            if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
                parts.append(token[1:-1])
            else:
                parts.append(token)
            text = text[end + 1:]
        else:
            raise JsonPathError(QCoreApplication.translate(
                "JsonPath", "过滤器里无法解析：{0}").format(repr(text)))
    if not parts:
        raise JsonPathError(QCoreApplication.translate("JsonPath", "过滤器里 @ 后面没有字段，如 @.price"))
    return parts


def _eval_filter(node, expr: str) -> bool:
    """`&&` 优先级高于 `||`。"""
    for clause in _split_top(expr, "||"):
        ok = True
        for cond in _split_top(clause, "&&"):
            if not _eval_condition(node, cond):
                ok = False
                break
        if ok:
            return True
    return False


def _split_top(expr: str, delim: str) -> list[str]:
    """按 `&&` / `||` 切分（引号内的不算）。"""
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    i = 0
    while i < len(expr):
        ch = expr[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            buf.append(ch)
        elif expr.startswith(delim, i):
            parts.append("".join(buf))
            buf = []
            i += len(delim)
            continue
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p for p in parts if p.strip()]


# ---------------------------------------------------------------- 求值


def _walk(node):
    """迭代前序遍历，产出 (path, value, key)；深嵌套不会爆栈。

    key 单独带出来，递归下降 `..name` 才能精确按字段名匹配——靠路径字符串
    反推会因为 key 里带 `.` 或 `[]` 而认错。
    """
    stack = [("$", node, None)]
    count = 0
    while stack:
        if count >= MAX_WALK_NODES:
            return
        path, value, key = stack.pop()
        count += 1
        yield path, value, key
        # 逆序压栈 → pop 出来是文档顺序（否则结果会整体倒过来，看着像数据乱了）
        if isinstance(value, dict):
            for k, item in reversed(list(value.items())):
                stack.append((path + _fmt_key(str(k)), item, str(k)))
        elif isinstance(value, list):
            for idx in range(len(value) - 1, -1, -1):
                stack.append((f"{path}[{idx}]", value[idx], str(idx)))


def _common_prefix(paths: list[str]) -> str:
    """多个路径的公共前缀，截到最后一个完整段边界。

    `$.a[0].price` / `$.a[1].price` → `$.a`（聚合结果的展示路径）。
    """
    prefix = paths[0]
    for p in paths[1:]:
        while not p.startswith(prefix):
            prefix = prefix[:-1]
    cut = max(prefix.rfind("."), prefix.rfind("["))
    return prefix[:cut] if cut > 0 else "$"


def _apply_function(func: Function, nodes: list[tuple[str, object]]) -> list[tuple[str, object]]:
    """聚合函数：对整个结果集生效，返回单条 (路径, 值)。"""
    if func.name == "length":
        if len(nodes) == 1:
            value = nodes[0][1]
            if isinstance(value, (list, dict, str)):
                return [(f"{nodes[0][0]}.length()", len(value))]
        # 多个命中 → 计条数（bool 不是 str，不会被 len 误伤）
        return [("$.length()", len(nodes))]

    # min / max：单个数组节点取数组内极值，否则对所有命中值取极值
    if len(nodes) == 1 and isinstance(nodes[0][1], list):
        values = list(nodes[0][1])
        base = nodes[0][0]
    else:
        values = [v for _, v in nodes]
        base = _common_prefix([p for p, _ in nodes]) if nodes else "$"
    numbers: list[float] = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise JsonPathError(
                QCoreApplication.translate(
                    "JsonPath", "{0}() 只能比较数字（遇到 {1}：{2}）"
                ).format(func.name, type(v).__name__, repr(v))
            )
        numbers.append(v)
    if not numbers:
        raise JsonPathError(QCoreApplication.translate("JsonPath", '{0}() 没有可比较的数字（结果为空）').format(func.name))
    result = min(numbers) if func.name == "min" else max(numbers)
    return [(f"{base}.{func.name}()", result)]


def _apply(selector, nodes: list[tuple[str, object]]) -> list[tuple[str, object]]:
    if isinstance(selector, Function):
        return _apply_function(selector, nodes)
    out: list[tuple[str, object]] = []
    for path, value in nodes:
        if isinstance(selector, Key):
            if isinstance(value, dict) and selector.name in value:
                out.append((path + _fmt_key(selector.name), value[selector.name]))
        elif isinstance(selector, Index):
            if isinstance(value, list):
                try:
                    item = value[selector.index]
                except IndexError:
                    continue
                out.append((f"{path}[{selector.index}]", item))
        elif isinstance(selector, Slice):
            if isinstance(value, list):
                # 用 range 切片拿到**实际下标**：起点为负或缺省时不能硬套 offset
                for idx in range(len(value))[selector.start : selector.stop]:
                    out.append((f"{path}[{idx}]", value[idx]))
        elif isinstance(selector, Wildcard):
            if isinstance(value, dict):
                for key, item in value.items():
                    out.append((path + _fmt_key(str(key)), item))
            elif isinstance(value, list):
                for idx, item in enumerate(value):
                    out.append((f"{path}[{idx}]", item))
        elif isinstance(selector, Recursive):
            for sub_path, sub_value, sub_key in _walk(value):
                if sub_path == path:
                    continue        # 跳过自身
                if selector.name is None or sub_key == selector.name:
                    out.append((sub_path, sub_value))
        elif isinstance(selector, Filter):
            if isinstance(value, list):
                for idx, item in enumerate(value):
                    try:
                        hit = _eval_filter(item, selector.expr)
                    except JsonPathError:
                        raise
                    if hit:
                        out.append((f"{path}[{idx}]", item))
            elif isinstance(value, dict):
                for key, item in value.items():
                    if _eval_filter(item, selector.expr):
                        out.append((path + _fmt_key(str(key)), item))
        elif isinstance(selector, Union):
            for child in selector.items:
                out.extend(_apply(child, [(path, value)]))
    return out


def find(expr: str, data: object) -> tuple[list[Match], str | None]:
    """执行 JSONPath。返回 `(匹配列表, 错误信息)`——错误不抛，交给 UI 显示。"""
    text = (expr or "").strip()
    if not text:
        return [], QCoreApplication.translate("JsonPath", "请输入 JSONPath 表达式（如 $.data.list[0]）")
    try:
        selectors = parse(text)
    except JsonPathError as exc:
        return [], exc.describe(text)
    except RecursionError:
        return [], QCoreApplication.translate("JsonPath", "表达式嵌套过深")

    nodes: list[tuple[str, object]] = [("$", data)]
    try:
        for selector in selectors:
            nodes = _apply(selector, nodes)
    except JsonPathError as exc:
        return [], exc.describe(text)
    except RecursionError:
        return [], QCoreApplication.translate("JsonPath", "数据嵌套过深，无法继续提取")

    if len(nodes) > MAX_MATCHES:
        nodes = nodes[:MAX_MATCHES]
        note = QCoreApplication.translate("JsonPath", '（命中过多，仅显示前 {0} 条）').format(MAX_MATCHES)
    else:
        note = None
    matches = [Match(path, value) for path, value in nodes]
    if note:
        return matches, note
    return matches, None
