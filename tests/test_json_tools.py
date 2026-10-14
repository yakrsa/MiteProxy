"""JSON 工具：解析与错误定位（jsonutil）、JSONPath（jsonpath）、面板接线。

重点是「出错时给的东西能不能帮到人」——只丢一句 `Expecting ',' delimiter`
用户还是不知道改哪，所以定位、出错行指针、可能原因这三样都要测。
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-json-test-home")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.jsonpath import JsonPathError, find, parse  # noqa: E402
from app.jsonutil import (  # noqa: E402
    count_nodes,
    dumps_json,
    error_snippet,
    hint_for,
    max_depth,
    parse_json,
)

_app = None


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


# ================================================================ 解析与报错


class TestParseOk:
    def test_plain(self):
        result = parse_json('{"a":1,"b":[1,2]}')
        assert result.ok and result.value == {"a": 1, "b": [1, 2]}

    def test_chinese_kept(self):
        assert parse_json('{"n":"张三"}').value == {"n": "张三"}

    def test_bom_stripped(self):
        assert parse_json('\ufeff{"a":1}').ok

    def test_empty_is_error_not_crash(self):
        result = parse_json("")
        assert not result.ok
        assert "空" in result.error.message

    def test_duplicate_keys_noted(self):
        result = parse_json('{"a":1,"b":2,"a":3}')
        assert result.ok
        assert result.value["a"] == 3          # 保留最后一次
        assert "重复 key" in result.notes[0] and "a" in result.notes[0]

    def test_nan_rejected_like_browser(self):
        """Python 的 json 默认接受 NaN，但 JSON.parse 不接受——对齐后者。"""
        result = parse_json('{"a": NaN}')
        assert not result.ok and "NaN" in result.error.message

    def test_infinity_rejected(self):
        assert not parse_json('{"a": Infinity}').ok

    def test_deep_nesting_does_not_crash(self):
        """RecursionError 不是 ValueError 子类，漏接就是界面崩掉。"""
        result = parse_json("[" * 10000 + "]" * 10000)
        assert not result.ok
        assert "嵌套" in result.error.message


class TestParseError:
    def test_location_and_snippet(self):
        text = '{\n  "a": 1\n  "b": 2\n}'
        result = parse_json(text)
        assert not result.ok
        assert result.error.lineno == 3
        assert '"b"' in result.error.snippet
        assert "^" in result.error.snippet
        assert result.error.location == f"第 3 行第 {result.error.colno} 列"

    def test_report_contains_all_three_parts(self):
        text = '{\n  "a": 1,\n  "b": [1,2\n}'
        report = parse_json(text).error.report()
        assert "第" in report and "列" in report      # 定位
        assert "^" in report                          # 指针
        assert "可能原因" in report                    # 人话

    def test_missing_comma_hint(self):
        err = parse_json('{"a":1 "b":2}').error
        assert "逗号" in err.hint

    def test_trailing_comma_hint(self):
        err = parse_json('{"a":1,}').error
        assert err.hint and "引号" in err.hint or "尾逗号" in err.hint

    def test_single_quote_hint(self):
        err = parse_json("{'a':1}").error
        assert "双引号" in err.hint

    def test_extra_data_hint(self):
        err = parse_json('{"a":1} {"b":2}').error
        assert "多余内容" in err.hint

    def test_unterminated_string_hint(self):
        err = parse_json('{"a":"abc}').error
        assert "闭合" in err.hint

    def test_hint_for_unknown_message(self):
        assert hint_for("某个没见过的错误") == ""

    def test_snippet_truncates_long_line(self):
        long_line = '{"a":"' + "x" * 500 + '"}'
        snippet = error_snippet(long_line, 1, 400)
        assert "…" in snippet and len(snippet) < 400

    def test_snippet_out_of_range(self):
        assert error_snippet("{}", 99, 1) == ""


class TestDumps:
    def test_pretty_indent_two(self):
        ok, text = dumps_json({"a": 1})
        assert ok and text == '{\n  "a": 1\n}'

    def test_minify(self):
        ok, text = dumps_json({"a": [1, 2]}, indent=None)
        assert ok and text == '{"a":[1,2]}'

    def test_chinese_not_escaped(self):
        assert "张三" in dumps_json({"n": "张三"})[1]

    def test_key_order_preserved(self):
        assert dumps_json({"b": 1, "a": 2})[1].index("b") < dumps_json({"b": 1, "a": 2})[1].index("a")


class TestScale:
    def test_count_and_depth(self):
        data = {"a": [1, {"b": {"c": 1}}]}
        assert count_nodes(data) == 6
        assert max_depth(data) == 5      # dict → list → dict → dict → 1

    def test_deep_structure_iterative(self):
        """统计用迭代实现，深结构不能爆栈。"""
        node = current = {}
        for _ in range(2000):
            current["x"] = {}
            current = current["x"]
        assert max_depth(node) == 2001


# ================================================================ JSONPath

DATA = {
    "code": 0,
    "data": {
        "list": [
            {"id": 1, "name": "张三", "price": 8.5, "tags": ["a"]},
            {"id": 2, "name": "李四", "price": 12.0, "tags": []},
            {"id": 3, "name": "王五", "price": 30.0},
        ],
        "total": 3,
    },
    "trace": {"id": "abc"},
}


def values(expr: str):
    matches, error = find(expr, DATA)
    assert error is None, error
    return [m.value for m in matches]


class TestJsonPathBasic:
    def test_root(self):
        assert len(values("$")) == 1

    def test_nested_field(self):
        assert values("$.data.total") == [3]

    def test_bracket_notation(self):
        assert values("$['data']['total']") == [3]

    def test_index(self):
        assert values("$.data.list[0].name") == ["张三"]

    def test_negative_index(self):
        assert values("$.data.list[-1].name") == ["王五"]

    def test_slice(self):
        assert values("$.data.list[0:2].id") == [1, 2]

    def test_slice_open_end(self):
        assert values("$.data.list[1:].id") == [2, 3]

    def test_slice_negative_start(self):
        assert values("$.data.list[-2:].id") == [2, 3]

    def test_wildcard_on_array(self):
        assert values("$.data.list[*].id") == [1, 2, 3]

    def test_union_index(self):
        assert values("$.data.list[0,2].id") == [1, 3]

    def test_union_key(self):
        assert values("$['code','trace']") == [0, {"id": "abc"}]

    def test_recursive_by_name(self):
        # trace.id 与 data.list[*].id 都叫 id
        assert sorted(values("$..id"), key=str) == [1, 2, 3, "abc"]

    def test_recursive_keeps_document_order(self):
        """栈式遍历容易把结果倒过来，看着像数据乱了。"""
        assert values("$..name") == ["张三", "李四", "王五"]

    def test_missing_field_is_empty(self):
        assert values("$.data.nope") == []

    def test_out_of_range_index(self):
        assert values("$.data.list[99]") == []

    def test_path_reported(self):
        matches, _ = find("$.data.list[1].name", DATA)
        assert matches[0].path == "$.data.list[1].name"


class TestJsonPathFilter:
    def test_greater_than(self):
        assert values("$.data.list[?(@.price > 10)].name") == ["李四", "王五"]

    def test_equal_string(self):
        assert values("$.data.list[?(@.name == '张三')].id") == [1]

    def test_and(self):
        assert values("$.data.list[?(@.price > 5 && @.price < 20)].id") == [1, 2]

    def test_or(self):
        assert values("$.data.list[?(@.id == 1 || @.id == 3)].id") == [1, 3]

    def test_regex(self):
        assert values("$.data.list[?(@.name =~ '张|王')].id") == [1, 3]

    def test_existence(self):
        """没有比较符 = 判断字段存在（空数组也算存在）。"""
        assert values("$.data.list[?(@.tags)].id") == [1, 2]

    def test_numeric_string_compared_as_number(self):
        data = {"l": [{"p": "20"}, {"p": "5"}]}
        matches, _ = find("$.l[?(@.p > 10)]", data)
        assert [m.value for m in matches] == [{"p": "20"}]


class TestJsonPathFunctions:
    """聚合函数 length()/min()/max()：对整个结果集生效。"""

    def test_length_on_array(self):
        matches, error = find("$.l.length()", {"l": [1, 2, 3]})
        assert error is None
        assert [m.value for m in matches] == [3]
        assert matches[0].path == "$.l.length()"

    def test_length_on_object_and_string(self):
        matches, _ = find("$.o.length()", {"o": {"a": 1, "b": 2}})
        assert [m.value for m in matches] == [2]
        matches, _ = find("$.s.length()", {"s": "你好"})
        assert [m.value for m in matches] == [2]

    def test_length_counts_multi_matches(self):
        data = {"l": [{"p": 1}, {"p": 2}, {"p": 3}]}
        matches, _ = find("$.l[*].p.length()", data)
        assert [m.value for m in matches] == [3]

    def test_min_max_on_array(self):
        data = {"l": [3, 1, 2]}
        matches, _ = find("$.l.min()", data)
        assert [m.value for m in matches] == [1]
        matches, _ = find("$.l.max()", data)
        assert [m.value for m in matches] == [3]

    def test_min_max_over_multi_matches(self):
        data = {"l": [{"p": 3}, {"p": 1}, {"p": 2}]}
        matches, error = find("$.l[*].p.max()", data)
        assert error is None
        assert [m.value for m in matches] == [3]
        assert matches[0].path == "$.l.max()"
        matches, _ = find("$.l[*].p.min()", data)
        assert [m.value for m in matches] == [1]

    def test_field_named_length_still_works(self):
        # 不带括号就是普通字段，与函数不冲突
        matches, error = find("$.a.length", {"a": {"length": 7}})
        assert error is None
        assert [m.value for m in matches] == [7]

    def test_min_max_rejects_non_numbers(self):
        _, error = find("$.l.max()", {"l": [1, "x"]})
        assert error and "只能比较数字" in error and "str" in error

    def test_min_max_on_empty(self):
        _, error = find("$.l.max()", {"l": []})
        assert error and "没有可比较的数字" in error

    def test_min_max_without_parens_is_field(self):
        matches, error = find("$.a.max", {"a": {"max": 9}})
        assert error is None
        assert [m.value for m in matches] == [9]

    def test_function_chained_after_recursive(self):
        data = {"a": {"p": 5}, "b": {"p": 9}}
        matches, error = find("$..p.max()", data)
        assert error is None
        assert [m.value for m in matches] == [9]


class TestJsonPathErrors:
    @pytest.mark.parametrize("expr", [
        "data.list",        # 没写 $
        "$..",              # .. 后面空
        "$.a[",             # 括号没闭合
        "$[?(]",            # 过滤器没闭合
        "$[::2]",           # 步长
        "$.a[?x]",          # ? 后面不是 (
    ])
    def test_syntax_errors_reported(self, expr):
        matches, error = find(expr, DATA)
        assert matches == [] and error and "JSONPath 语法错误" in error

    def test_error_shows_pointer(self):
        _, error = find("$.a[", DATA)
        assert "^" in error

    def test_filter_without_at(self):
        _, error = find("$[?(price > 1)]", DATA)
        assert error and "@" in error

    def test_empty_expression(self):
        _, error = find("", DATA)
        assert error and "请输入" in error

    def test_parse_raises_with_position(self):
        with pytest.raises(JsonPathError) as info:
            parse("nope")
        assert info.value.pos == 0
        assert "^" in info.value.describe("nope")

    def test_deep_data_does_not_crash(self):
        node = current = {}
        for _ in range(500):
            current["x"] = {}
            current = current["x"]
        matches, error = find("$..x", node)
        assert error is None
        assert len(matches) == 500

    def test_too_many_matches_is_capped(self):
        node = {"l": [{"x": i} for i in range(2500)]}
        matches, note = find("$..x", node)
        assert len(matches) == 2000
        assert note and "命中过多" in note


# ================================================================ 面板接线

from app.ui.json_panel import JsonPanel, VIEW_PATH, VIEW_TEXT, VIEW_TREE  # noqa: E402
from app.ui.tool_panel import ToolPanel  # noqa: E402


def _panel() -> JsonPanel:
    panel = JsonPanel()
    panel.resize(1000, 700)
    return panel


class TestJsonPanel:
    def test_formats_and_colors(self):
        panel = _panel()
        panel.input_edit.setPlainText('{"b":2,"a":[1,2]}')
        panel.format_btn.click()
        assert panel.text_view.toPlainText() == '{\n  "b": 2,\n  "a": [\n    1,\n    2\n  ]\n}'
        assert panel._highlighter.enabled      # 小内容要着色

    def test_chinese_kept(self):
        panel = _panel()
        panel.set_text('{"n":"张三"}')
        assert "张三" in panel.text_view.toPlainText()

    def test_indent_switch(self):
        panel = _panel()
        panel.input_edit.setPlainText('{"a":1}')
        panel.indent_combo.setCurrentIndex(1)      # 4 空格
        assert panel.text_view.toPlainText() == '{\n    "a": 1\n}'

    def test_tab_indent(self):
        panel = _panel()
        panel.input_edit.setPlainText('{"a":1}')
        panel.indent_combo.setCurrentIndex(2)      # Tab
        assert "\n\t\"a\": 1" in panel.text_view.toPlainText()

    def test_minify(self):
        panel = _panel()
        panel.input_edit.setPlainText('{\n  "a": [1, 2]\n}')
        panel.minify_btn.click()
        assert panel.text_view.toPlainText() == '{"a":[1,2]}'

    def test_check_only(self):
        panel = _panel()
        panel.input_edit.setPlainText('{"a":1,"b":{"c":2}}')
        panel.check_btn.click()
        assert "合法 JSON" in panel.status_label.text()
        assert "节点" in panel.status_label.text()

    def test_invalid_shows_original_and_error(self):
        """解析失败内容绝不能消失。"""
        panel = _panel()
        panel.input_edit.setPlainText('{"a":1 "b":2}')
        panel.format_btn.click()
        assert panel.text_view.toPlainText() == '{"a":1 "b":2}'      # 原文还在
        assert "第 1 行" in panel.status_label.text()
        assert "可能原因" in panel.status_label.text()

    def test_goto_button_visible_only_on_error(self):
        panel = _panel()
        panel.input_edit.setPlainText('{"a":1}')
        panel.format_btn.click()
        assert panel.goto_btn.isHidden()
        panel.input_edit.setPlainText('{"a":1 "b":2}')
        panel.format_btn.click()
        assert not panel.goto_btn.isHidden()

    def test_goto_moves_cursor_to_error_line(self):
        panel = _panel()
        panel.input_edit.setPlainText('{\n  "a": 1\n  "b": 2\n}')
        panel.format_btn.click()
        panel.goto_btn.click()
        cursor = panel.input_edit.textCursor()
        assert cursor.blockNumber() == 2      # 第 3 行（0-based）

    def test_duplicate_key_note(self):
        panel = _panel()
        panel.input_edit.setPlainText('{"a":1,"a":2}')
        panel.format_btn.click()
        assert "重复 key" in panel.status_label.text()

    def test_tree_view(self):
        panel = _panel()
        panel.input_edit.setPlainText('{"a":{"b":1},"c":[10,20]}')
        panel.view_combo.setCurrentIndex(panel.view_combo.findData(VIEW_TREE))
        assert panel.out_stack.currentWidget() is panel.tree_view
        root = panel.tree_view.topLevelItem(0)
        assert root.text(0) == "$"
        names = [root.child(i).text(0) for i in range(root.childCount())]
        assert names == ["a", "c"]
        assert root.child(1).text(1) == "2 项"       # 数组显示项数

    def test_tree_skipped_when_too_many_nodes(self):
        """懒加载后行为变化：不再整棵跳过——根可见、单层展开填到上限后加占位。"""
        panel = _panel()
        big = json.dumps([{"i": i} for i in range(6000)])
        panel.input_edit.setPlainText(big)
        panel.view_combo.setCurrentIndex(panel.view_combo.findData(VIEW_TREE))
        assert panel.tree_view.topLevelItemCount() == 1  # 根节点可见
        root = panel.tree_view.topLevelItem(0)
        assert root.childCount() == 5001  # 5000 子项 + 1 截断占位
        assert "其余 1000 项未显示" in root.child(5000).text(0)

    def test_tree_lazy_root_only_before_expand(self):
        """懒加载核心：初始只建根节点，子节点等展开信号才填。"""
        panel = _panel()
        panel.input_edit.setPlainText(json.dumps({"a": {"b": 1}}))
        panel._value = json.loads(panel.input_edit.toPlainText())
        panel._build_tree(panel.tree_view, panel._value, "$")
        root = panel.tree_view.topLevelItem(0)
        assert root.childCount() == 0  # 尚未展开，不铺子节点
        assert root.text(1) == "1 项"
        root.setExpanded(True)
        panel.tree_view.itemExpanded.emit(root)  # 模拟展开信号
        assert root.childCount() == 1
        assert root.child(0).text(0) == "a"

    def test_tree_refill_guard_on_reexpand(self):
        """折叠再展开不重复填充。"""
        panel = _panel()
        panel._value = {"a": 1, "b": 2}
        panel._build_tree(panel.tree_view, panel._value, "$")
        root = panel.tree_view.topLevelItem(0)
        panel.tree_view.itemExpanded.emit(root)
        assert root.childCount() == 2
        panel.tree_view.itemExpanded.emit(root)  # 重复信号
        assert root.childCount() == 2

    def test_tree_child_limit_truncates_with_note(self):
        panel = _panel()
        panel._value = list(range(6000))
        panel._build_tree(panel.tree_view, panel._value, "$")
        root = panel.tree_view.topLevelItem(0)
        panel.tree_view.itemExpanded.emit(root)
        assert root.childCount() == 5001
        assert "其余 1000 项未显示" in root.child(5000).text(0)

    def test_tree_node_limit_pauses_deeper_fill(self):
        """全局节点上限：填满 5000 后停止，后续展开不再构建并提示。"""
        panel = _panel()
        panel._value = {"big": [{"i": i} for i in range(4000)],
                        "more": [{"j": j} for j in range(4000)]}
        panel._build_tree(panel.tree_view, panel._value, "$")
        root = panel.tree_view.topLevelItem(0)
        panel.tree_view.itemExpanded.emit(root)
        assert root.childCount() == 2
        assert panel._tree_nodes_built == 2
        big = root.child(0)
        panel.tree_view.itemExpanded.emit(big)     # 逐个展开才是真实交互路径
        assert big.childCount() == 4000
        assert panel._tree_nodes_built == 4002
        more = root.child(1)
        panel.tree_view.itemExpanded.emit(more)
        assert panel._tree_truncated  # 触顶
        assert more.childCount() == 998  # 4002 + 998 = 5000（上限 5000）
        assert "未展开" in panel.status_label.text()

    def test_tree_scalar_root(self):
        panel = _panel()
        panel._value = "just a string"
        panel._build_tree(panel.tree_view, panel._value, "$")
        root = panel.tree_view.topLevelItem(0)
        assert root.text(1) == "just a string"
        assert root.childIndicatorPolicy() != root.ChildIndicatorPolicy.ShowIndicator

    def test_deep_nesting_does_not_crash_ui(self):
        panel = _panel()
        panel.input_edit.setPlainText("[" * 10000 + "]" * 10000)
        panel.format_btn.click()
        assert "嵌套" in panel.status_label.text()

    def test_jsonpath_extract(self):
        panel = _panel()
        panel.input_edit.setPlainText(json.dumps(DATA, ensure_ascii=False))
        panel.format_btn.click()
        panel.path_edit.setText("$.data.list[*].name")
        panel.path_btn.click()
        assert panel.out_stack.currentWidget() is panel.path_table
        assert panel.path_table.rowCount() == 3
        assert panel.path_table.item(0, 2).text() == "张三"
        assert "共 3 处匹配" in panel.status_label.text()

    def test_jsonpath_no_match(self):
        panel = _panel()
        panel.input_edit.setPlainText('{"a":1}')
        panel.format_btn.click()
        panel.path_edit.setText("$.zzz")
        panel.path_btn.click()
        assert "没有匹配" in panel.status_label.text()

    def test_jsonpath_syntax_error_shown(self):
        panel = _panel()
        panel.input_edit.setPlainText('{"a":1}')
        panel.format_btn.click()
        panel.path_edit.setText("a.b")
        panel.path_btn.click()
        assert "JSONPath 语法错误" in panel.status_label.text()

    def test_jsonpath_on_invalid_input(self):
        panel = _panel()
        panel.input_edit.setPlainText("{bad json")
        panel.path_edit.setText("$.a")
        panel.path_btn.click()
        assert "先修好" in panel.status_label.text()

    def test_copy_path_result(self, monkeypatch):
        panel = _panel()
        copied = {}
        monkeypatch.setattr(
            QApplication, "clipboard", staticmethod(lambda: _Clipboard(copied))
        )
        panel.input_edit.setPlainText('{"a":[1,2]}')
        panel.format_btn.click()
        panel.path_edit.setText("$.a[*]")
        panel.path_btn.click()
        assert panel.copy_path_result() is True
        assert json.loads(copied["text"]) == [1, 2]

    def test_copy_result_empty(self):
        panel = _panel()
        assert panel.copy_result() is False

    def test_live_format_paused_for_huge_input(self):
        panel = _panel()
        panel.input_edit.setPlainText("x" * (600 * 1024))
        assert not panel._timer.isActive()
        assert "已暂停自动格式化" in panel.status_label.text()

    def test_clear(self):
        panel = _panel()
        panel.set_text('{"a":1}')
        panel.clear_btn.click()
        assert panel.input_edit.toPlainText() == ""
        assert panel.text_view.toPlainText() == ""

    def test_long_single_line_disables_wrap(self):
        """压缩后的单行可能几百 KB，换行是超线性开销——必须能自动让路。"""
        panel = _panel()
        panel.input_edit.setPlainText(json.dumps({"a": "x" * 200_000}))
        panel.minify_btn.click()
        assert (
            panel.text_view.lineWrapMode()
            == panel.text_view.LineWrapMode.NoWrap
        )
        assert "已临时关闭换行" in panel.status_label.text()

    def test_highlight_disabled_for_large_output(self):
        panel = _panel()
        big = json.dumps([{"i": i, "s": "y" * 40} for i in range(4000)])
        if len(big) < 300 * 1024:      # 确保跨过 HIGHLIGHT_LIMIT
            big = json.dumps([{"i": i, "s": "y" * 200} for i in range(4000)])
        panel.input_edit.setPlainText(big)
        panel.format_btn.click()
        assert len(panel.text_view.toPlainText()) > 256 * 1024
        assert not panel._highlighter.enabled


class _Clipboard:
    def __init__(self, sink: dict):
        self._sink = sink

    def setText(self, text: str) -> None:
        self._sink["text"] = text


class TestJsonComparePanel:
    """JSON 比对子页（复用 app/jsondiff.py 引擎）。"""

    def _panel(self):
        from app.ui.json_compare_panel import JsonComparePanel

        panel = JsonComparePanel()
        panel.resize(1000, 700)
        return panel

    def test_identical(self):
        panel = self._panel()
        panel.set_texts('{"a":1}', '{"a":1}')
        assert panel.table.rowCount() == 0
        assert "完全一致" in panel.status_label.text()
        assert not panel.copy_btn.isEnabled()

    def test_structured_rows(self):
        panel = self._panel()
        panel.set_texts(
            '{"user":{"name":"tom"},"gone":true}',
            '{"user":{"name":"jerry"},"added":5}',
        )
        assert panel.table.rowCount() == 3
        paths = [panel.table.item(r, 0).text() for r in range(3)]
        assert "$.user.name" in paths and "$.added" in paths and "$.gone" in paths
        kinds = {panel.table.item(r, 0).text(): panel.table.item(r, 1).text()
                 for r in range(3)}
        assert kinds["$.added"] == "新增"
        assert kinds["$.gone"] == "删除"
        assert kinds["$.user.name"] == "修改"
        assert "3 处差异" in panel.status_label.text()
        assert panel.copy_btn.isEnabled()

    def test_invalid_side_shows_error_and_keeps_text(self):
        panel = self._panel()
        panel.set_texts('{"a":1}', '{"a":}')
        assert panel.table.rowCount() == 0
        assert "不合法" in panel.status_label.text()
        assert "新 JSON" in panel.status_label.text()
        # 失败不吞内容：右边输入框原样保留
        assert panel.right_edit.toPlainText() == '{"a":}'

    def test_one_side_empty(self):
        panel = self._panel()
        panel.set_texts('{"a":1}', '   ')
        assert "还是空的" in panel.status_label.text()

    def test_swap(self):
        panel = self._panel()
        panel.set_texts('{"a":1}', '{"a":2}')
        panel._swap()
        assert panel.left_edit.toPlainText() == '{"a":2}'
        assert panel.right_edit.toPlainText() == '{"a":1}'
        # 交换后仍是 1 处差异（$.a 从 2 改 1）
        assert panel.table.rowCount() == 1

    def test_copy_report(self):
        panel = self._panel()
        copied = {}
        panel.set_texts('{"a":1}', '{"a":2}')
        from PySide6.QtWidgets import QApplication

        original = QApplication.clipboard
        QApplication.clipboard = staticmethod(lambda: _Clipboard(copied))
        try:
            panel._copy_report()
        finally:
            QApplication.clipboard = original
        assert "~ $.a: 1 → 2" in copied["text"]

    def test_clear(self):
        panel = self._panel()
        panel.set_texts('{"a":1}', '{"a":2}')
        panel._on_clear()
        assert panel.left_edit.toPlainText() == ""
        assert panel.table.rowCount() == 0
        assert not panel.copy_btn.isEnabled()

    def test_many_differences_capped(self):
        left = {str(i): i for i in range(600)}
        right = {str(i): i + 1 for i in range(600)}
        panel = self._panel()
        panel.set_texts(json.dumps(left), json.dumps(right))
        assert panel.table.rowCount() == 500
        assert "仅显示前 500 条" in panel.status_label.text()
        assert "600 处差异" in panel.status_label.text()


class TestToolPanel:
    def test_four_pages(self):
        panel = ToolPanel()
        assert panel.tabs.count() == 4
        assert panel.tabs.tabText(0) == "编码转换"
        assert panel.tabs.tabText(1) == "JSON"
        assert panel.tabs.tabText(2) == "JSON 比对"
        assert panel.tabs.tabText(3) == "API 调试"

    def test_current_key_and_switch(self):
        panel = ToolPanel()
        assert panel.current_key == "codec"
        panel.show_page("json")
        assert panel.current_key == "json"
        panel.show_page("compare")
        assert panel.current_key == "compare"
        panel.show_page("api")
        assert panel.current_key == "api"

    def test_set_body_text_to_compare_page(self):
        panel = ToolPanel()
        panel.set_body_text('{"a":1}', "compare")
        assert panel.current_key == "compare"
        assert panel.compare_panel.left_edit.toPlainText() == '{"a":1}'

    def test_set_body_text_to_json_page(self):
        panel = ToolPanel()
        panel.set_body_text('{"a":1}', "json")
        assert panel.current_key == "json"
        assert panel.json_panel.text_view.toPlainText() == '{\n  "a": 1\n}'

    def test_set_body_text_to_codec_page(self):
        panel = ToolPanel()
        panel.set_body_text("hello", "codec")
        assert panel.current_key == "codec"
        assert panel.codec_panel.input_edit.toPlainText() == "hello"
