"""JSON 语法着色：请求/响应 body 与 JSON 工具页共用一份。

从 detail_panel.py 抽出来，是为了让「JSON 工具页」和「body 视图」用**同一套**
配色与规则——两处各写一份迟早会不一致（比如一处改了深色配色，另一处没改）。

两条不能破的规则：

1. **只改前景、不碰背景**：搜索高亮走 ExtraSelections 的背景色，这里要是也铺
   背景，用户「搜到了却看不出在哪」。
2. **数字/关键字染色要跳过字符串内部**：否则 `"13800138000"` 里的数字会被当成
   JSON number 染成橙色，看着像数据被改了。
"""

from __future__ import annotations

import re

from PySide6.QtGui import (
    QColor,
    QPalette,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import QWidget


def is_dark(widget: QWidget) -> bool:
    """按输入框底色判断深浅主题——两套色都要可读。

    取 `QPalette.Base`（文本输入区底色）而不是 `backgroundRole()`，后者在不同
    控件上语义不一致，容易判反。
    """
    bg = widget.palette().color(QPalette.ColorRole.Base)
    return bg.lightness() < 128


# 两套配色（GitHub 亮/暗风格），都保证在对应底色上有足够对比度
JSON_COLORS_LIGHT = {
    "key": "#0550ae",
    "string": "#0a6b28",
    "number": "#b8500a",
    "keyword": "#8250df",
}
JSON_COLORS_DARK = {
    "key": "#79c0ff",
    "string": "#7ee787",
    "number": "#ffa657",
    "keyword": "#d2a8ff",
}

_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
_KEY_RE = re.compile(r'("(?:\\.|[^"\\])*")(\s*:)')
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_KEYWORD_RE = re.compile(r"\b(?:true|false|null)\b")


class JsonHighlighter(QSyntaxHighlighter):
    """JSON 语法着色（可开关，避免大文档上白付 260ms/2 万行的代价）。"""

    def __init__(self, document):
        super().__init__(document)
        self.enabled = False
        self._dark = False

    def set_enabled(self, enabled: bool, dark: bool = False) -> None:
        if enabled == self.enabled and dark == self._dark:
            return
        self.enabled = enabled
        self._dark = dark
        self.rehighlight()

    def _format(self, kind: str) -> QTextCharFormat:
        colors = JSON_COLORS_DARK if self._dark else JSON_COLORS_LIGHT
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors[kind]))
        return fmt

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        if not self.enabled:
            return
        string_spans = [(m.start(), m.end()) for m in _STRING_RE.finditer(text)]

        def inside_string(pos: int) -> bool:
            return any(s <= pos < e for s, e in string_spans)

        for m in _STRING_RE.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._format("string"))
        # key 后画，覆盖掉 string 的颜色（key 本身也是字符串）
        for m in _KEY_RE.finditer(text):
            self.setFormat(m.start(1), m.end(1) - m.start(1), self._format("key"))
        for m in _KEYWORD_RE.finditer(text):
            if not inside_string(m.start()):
                self.setFormat(m.start(), m.end() - m.start(), self._format("keyword"))
        for m in _NUMBER_RE.finditer(text):
            if not inside_string(m.start()):
                self.setFormat(m.start(), m.end() - m.start(), self._format("number"))


# ===========================================================================
# Python 语法着色（脚本新建/编辑弹窗用）
# ===========================================================================

#: Python 关键字（True/False/None 一并纳入，按关键字着色更准）
PY_KEYWORDS = {
    "and", "as", "assert", "async", "await", "break", "class", "continue",
    "def", "del", "elif", "else", "except", "finally", "for", "from",
    "global", "if", "import", "in", "is", "lambda", "nonlocal", "not",
    "or", "pass", "raise", "return", "try", "while", "with", "yield",
    "True", "False", "None",
}

#: 常用内置（只染最显眼的几个，避免喧宾夺主）
PY_BUILTINS = {
    "print", "len", "range", "enumerate", "zip", "map", "filter", "list",
    "dict", "set", "tuple", "str", "int", "float", "bool", "abs", "min",
    "max", "sum", "sorted", "open", "isinstance", "type", "super",
    "object", "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "AttributeError", "RuntimeError", "IOError", "json",
    "re", "os", "sys", "time", "datetime", "getattr", "setattr",
    "hasattr", "dir", "repr", "format", "any", "all", "round", "ord", "chr",
}

#: GitHub 亮/暗两套色，均保证在对应底色上可读
PY_COLORS_LIGHT = {
    "keyword": "#8250df",
    "string": "#0a6b28",
    "comment": "#6e7781",
    "number": "#b8500a",
    "defname": "#0550ae",
    "decorator": "#bf3989",
    "builtin": "#953800",
}
PY_COLORS_DARK = {
    "keyword": "#d2a8ff",
    "string": "#7ee787",
    "comment": "#8b949e",
    "number": "#ffa657",
    "defname": "#79c0ff",
    "decorator": "#ff7b72",
    "builtin": "#ffa657",
}


class PythonHighlighter(QSyntaxHighlighter):
    """Python 语法着色（脚本编辑器）。

    约定同 JsonHighlighter：只染前景、不碰背景（搜索高亮走 ExtraSelections）；
    深浅主题各一套色。三引号多行字符串用块状态（setCurrentBlockState）跨行续染，
    不会出现「上半截绿、下半截没色」的断层。
    """

    #: 块状态：普通 / 在三单引号串内 / 在三双引号串内
    NORMAL, TRIPLE_SINGLE, TRIPLE_DOUBLE = 0, 1, 2

    def __init__(self, document):
        super().__init__(document)
        self.enabled = True
        self._dark = False
        # 主题切换时重染（控件销毁后 WeakMethod 自动失效，不阻止回收）
        try:
            from app.ui import theme
            theme.add_listener(self._on_theme_changed)
        except Exception:  # pragma: no cover - 极端情况下不阻断编辑器
            pass

    def _on_theme_changed(self) -> None:
        self.rehighlight()

    def set_enabled(self, enabled: bool, dark: bool = False) -> None:
        if enabled == self.enabled and dark == self._dark:
            return
        self.enabled = enabled
        self._dark = dark
        self.rehighlight()

    def _fmt(self, kind: str) -> QTextCharFormat:
        colors = PY_COLORS_DARK if self._dark else PY_COLORS_LIGHT
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors[kind]))
        return fmt

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        if not self.enabled:
            return
        n = len(text)

        # 1) 从上一块续进来的三引号字符串：先把开头到闭引号整段染了
        state = self.previousBlockState()
        if state not in (self.NORMAL, -1):
            delim = "'''" if state == self.TRIPLE_SINGLE else '"""'
            end = text.find(delim)
            if end == -1:
                self.setFormat(0, n, self._fmt("string"))
                self.setCurrentBlockState(state)
                return
            self.setFormat(0, end + 3, self._fmt("string"))
            i = end + 3
        else:
            i = 0

        string_fmt = self._fmt("string")
        comment_fmt = self._fmt("comment")
        number_fmt = self._fmt("number")
        keyword_fmt = self._fmt("keyword")
        builtin_fmt = self._fmt("builtin")
        defname_fmt = self._fmt("defname")
        decorator_fmt = self._fmt("decorator")

        # 2) 逐字符扫描：注释/字符串先吃掉，剩下的区域再染关键字等，
        #    天然避免「字符串里的 def 被当关键字染色」
        while i < n:
            ch = text[i]
            if ch == '#':                      # 行注释：吃到行尾
                self.setFormat(i, n - i, comment_fmt)
                break
            if ch == '"' or ch == "'":         # 字符串
                if text.startswith('"""', i) or text.startswith("'''", i):
                    delim = text[i:i + 3]
                    end = text.find(delim, i + 3)
                    if end == -1:              # 跨行，整块都是字符串
                        self.setFormat(i, n - i, string_fmt)
                        self.setCurrentBlockState(
                            self.TRIPLE_SINGLE if delim == "'''"
                            else self.TRIPLE_DOUBLE)
                        return
                    self.setFormat(i, end + 3 - i, string_fmt)
                    i = end + 3
                    continue
                quote = ch
                j = i + 1
                while j < n:
                    if text[j] == '\\':        # 跳过转义字符
                        j += 2
                        continue
                    if text[j] == quote:
                        j += 1
                        break
                    j += 1
                self.setFormat(i, j - i, string_fmt)
                i = j
                continue
            if ch.isalpha() or ch == '_' or ch == '@':   # 标识符/关键字/装饰器
                j = i
                # 注意：'@' 也要算进扫描集，否则 @装饰器 会让 j 不前进→死循环
                while j < n and (text[j].isalnum() or text[j] in '_@.'):
                    j += 1
                word = text[i:j]
                if word.startswith('@'):
                    self.setFormat(i, j - i, decorator_fmt)
                elif word in PY_KEYWORDS:
                    self.setFormat(i, j - i, keyword_fmt)
                    if word in ("def", "class"):   # def/class 后紧跟的名字另染色
                        k = j
                        while k < n and text[k] in ' \t':
                            k += 1
                        if k < n and (text[k].isalpha() or text[k] == '_'):
                            m = k
                            while m < n and (text[m].isalnum()
                                             or text[m] == '_'):
                                m += 1
                            self.setFormat(k, m - k, defname_fmt)
                            i = m
                            continue
                elif word in PY_BUILTINS:
                    self.setFormat(i, j - i, builtin_fmt)
                i = j
                continue
            if ch.isdigit():                    # 数字（含小数点/下划线分隔）
                j = i
                while j < n and (text[j].isdigit() or text[j] in '._'):
                    j += 1
                self.setFormat(i, j - i, number_fmt)
                i = j
                continue
            i += 1

        self.setCurrentBlockState(self.NORMAL)
