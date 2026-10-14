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
