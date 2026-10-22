"""PythonHighlighter 语法着色单元测试（v2.4.3 新增脚本编辑器高亮）。

只验证「颜色落到正确位置」：关键字 / 字符串 / 注释 / 装饰器 / def·class 名 /
三引号多行续染，以及普通变量名不被误染。用 RecordingHighlighter 重写 setFormat
记录调用，绕过界面渲染（沙箱里裸 Qt 渲染进程会被杀）。

行号用「按内容查找」动态定位，避免样板代码改动导致下标错位。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication

from app.ui import highlight


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


class RecordingHighlighter(highlight.PythonHighlighter):
    """记录每次 setFormat 调用：(block, start, length, color)。"""

    def __init__(self, document):
        super().__init__(document)
        self.calls: list[tuple[int, int, int, str]] = []

    def setFormat(self, start, count, fmt):  # noqa: N802
        bn = self.currentBlock().blockNumber()
        col = fmt.foreground().color().name()
        self.calls.append((bn, start, count, col))


SAMPLE = (
    "# 这是注释\n"
    "import os  # 行内注释\n"
    'x = "普通字符串"\n'
    'y = """三引号\n'
    '多行字符串"""\n'
    "@my_decorator\n"
    "def foo(a, b):\n"
    "    return a + b  # 计算\n"
    "class Bar:\n"
    "    def meth(self):\n"
    "        print(len([1, 2, 3]))\n"
)

LIGHT = highlight.PY_COLORS_LIGHT
DARK = highlight.PY_COLORS_DARK


def _lines():
    return SAMPLE.split("\n")


def _line_index(substr):
    for li, line in enumerate(_lines()):
        if substr in line:
            return li
    raise AssertionError(f"找不到包含 {substr!r} 的行")


def _color_at(rec, li, col):
    for bn, s, ln, c in rec.calls:
        if bn == li and s <= col < s + ln:
            return c
    return None


@pytest.fixture()
def rec(qapp):
    doc = QTextDocument()
    r = RecordingHighlighter(doc)
    doc.setPlainText(SAMPLE)
    r.set_enabled(True, dark=False)
    r.rehighlight()
    return r


def test_import_is_keyword(rec):
    li = _line_index("import os")
    i = _lines()[li].index("import")
    assert _color_at(rec, li, i) == LIGHT["keyword"]


def test_comment_colored(rec):
    li = _line_index("# 这是注释")
    assert _color_at(rec, li, 2) == LIGHT["comment"]


def test_string_colored(rec):
    li = _line_index('x = "普通字符串"')
    i = _lines()[li].index('"')
    assert _color_at(rec, li, i) == LIGHT["string"]


def test_decorator_colored(rec):
    li = _line_index("@my_decorator")
    assert _color_at(rec, li, 0) == LIGHT["decorator"]


def test_def_keyword_and_defname(rec):
    li = _line_index("def foo")
    i = _lines()[li].index("def")
    assert _color_at(rec, li, i) == LIGHT["keyword"]
    j = _lines()[li].index("foo")
    assert _color_at(rec, li, j) == LIGHT["defname"]


def test_triple_quote_spans_lines(rec):
    # 续接行（上一块未闭合三引号）整行应是字符串色
    li = _line_index("多行字符串")
    assert _color_at(rec, li, 0) == LIGHT["string"]
    # 起始行的三引号之后也应是字符串色（不含行首的 y）
    li2 = _line_index('y = """')
    line = _lines()[li2]
    q = line.index('"""') + 1  # 三引号内部的字符
    assert _color_at(rec, li2, q) == LIGHT["string"]


def test_classname_colored(rec):
    li = _line_index("class Bar")
    i = _lines()[li].index("Bar")
    assert _color_at(rec, li, i) == LIGHT["defname"]


def test_plain_variable_not_colored(rec):
    li = _line_index("def foo")
    i = _lines()[li].index("a")  # foo(a, b) 里的形参 a
    assert _color_at(rec, li, i) is None


def test_dark_swaps_palette(qapp):
    doc = QTextDocument()
    r = RecordingHighlighter(doc)
    doc.setPlainText(SAMPLE)
    r.set_enabled(True, dark=True)
    r.rehighlight()
    li = _line_index("import os")
    i = _lines()[li].index("import")
    assert _color_at(r, li, i) == DARK["keyword"]
    # 深色配色与浅色不同
    assert DARK["keyword"] != LIGHT["keyword"]
