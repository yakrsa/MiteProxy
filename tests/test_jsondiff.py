"""JSON 结构化 diff 测试（纯函数）。

覆盖：增/删/改、容器类型变化、bool vs 数字、key 顺序、列表下标对齐、
深嵌套不爆栈、双上限截断、报告渲染。
"""

import json

import pytest

from app.jsondiff import (
    MAX_DIFF_ENTRIES,
    DiffEntry,
    diff_json,
    format_diff_report,
    render_value,
)
from app.textutil import unified_diff


class TestScalarDiff:
    def test_identical(self):
        result = diff_json({"a": 1}, {"a": 1})
        assert result.identical
        assert result.count == 0

    def test_changed_scalar(self):
        result = diff_json({"a": 1}, {"a": 2})
        assert result.count == 1
        entry = result.entries[0]
        assert entry.path == "$.a"
        assert entry.kind == "changed"
        assert entry.old == 1
        assert entry.new == 2

    def test_added_and_removed(self):
        result = diff_json({"a": 1, "b": 2}, {"a": 1, "c": 3})
        paths = {e.path: e.kind for e in result.entries}
        assert paths == {"$.b": "removed", "$.c": "added"}
        removed = next(e for e in result.entries if e.kind == "removed")
        added = next(e for e in result.entries if e.kind == "added")
        assert removed.old == 2 and removed.new is None
        assert added.old is None and added.new == 3

    def test_bool_vs_int_not_equal(self):
        # Python 里 True == 1，JSON 语义里 true != 1
        result = diff_json({"flag": True}, {"flag": 1})
        assert result.count == 1
        assert result.entries[0].kind == "changed"

    def test_bool_true_vs_false(self):
        result = diff_json({"flag": True}, {"flag": False})
        assert result.count == 1

    def test_none_vs_zero(self):
        result = diff_json({"a": None}, {"a": 0})
        assert result.count == 1
        assert result.entries[0].kind == "changed"

    def test_int_and_float_equal_value(self):
        # 1 与 1.0 数值相等，不算差异
        result = diff_json({"a": 1}, {"a": 1.0})
        assert result.identical

    def test_nested_path(self):
        result = diff_json({"a": {"b": {"c": 1}}}, {"a": {"b": {"c": 2}}})
        assert result.count == 1
        assert result.entries[0].path == "$.a.b.c"


class TestContainerDiff:
    def test_list_element_changed(self):
        result = diff_json({"xs": [1, 2, 3]}, {"xs": [1, 9, 3]})
        assert result.count == 1
        assert result.entries[0].path == "$.xs[1]"

    def test_list_growth_and_shrink(self):
        result = diff_json({"xs": [1]}, {"xs": [1, 2]})
        assert result.count == 1
        assert result.entries[0].kind == "added"
        assert result.entries[0].path == "$.xs[1]"

        result = diff_json({"xs": [1, 2]}, {"xs": [1]})
        assert result.count == 1
        assert result.entries[0].kind == "removed"
        assert result.entries[0].path == "$.xs[1]"

    def test_dict_vs_list_is_change(self):
        result = diff_json({"a": {"x": 1}}, {"a": [1, 2]})
        assert result.count == 1
        assert result.entries[0].kind == "changed"

    def test_dict_vs_scalar_is_change(self):
        result = diff_json({"a": {"x": 1}}, {"a": 5})
        assert result.count == 1
        assert result.entries[0].kind == "changed"

    def test_key_order_not_a_difference(self):
        old = json.loads('{"a":1,"b":2}')
        new = json.loads('{"b":2,"a":1}')
        assert diff_json(old, new).identical

    def test_root_replaced(self):
        result = diff_json({"a": 1}, [1, 2])
        assert result.count == 1
        assert result.entries[0].path == "$"


class TestDeepAndLimits:
    def test_deeply_nested_no_recursion_error(self):
        # 10000 层：递归实现会 RecursionError
        depth = 10000
        old = 0
        for _ in range(depth):
            old = [old]
        new = 1
        for _ in range(depth):
            new = [new]
        result = diff_json(old, new)
        assert result.count == 1
        assert result.entries[0].path == "$" + "[0]" * depth
        assert result.entries[0].kind == "changed"

    def test_entry_limit_truncates(self):
        old = {str(i): i for i in range(100)}
        new = {str(i): i + 1 for i in range(100)}
        result = diff_json(old, new)
        assert result.count == 100
        assert not result.truncated

    def test_node_limit_truncates(self):
        # 巨型数组：两棵树节点数远超上限（seen 按对计，翻倍才够）
        big = list(range(120_000))
        result = diff_json(big, big)
        assert result.truncated
        # 完全相同但超限：identical 应为 False（内容没比完）
        assert not result.identical


class TestRender:
    def test_render_value_scalars(self):
        assert render_value(None) == "null"
        assert render_value(True) == "true"
        assert render_value(False) == "false"
        assert render_value(42) == "42"
        assert render_value("hi") == '"hi"'

    def test_render_value_container_compact(self):
        assert render_value({"a": 1, "b": [2]}) == '{"a":1,"b":[2]}'

    def test_render_value_truncates_long(self):
        text = render_value("x" * 500, limit=50)
        assert text.startswith('"xxx')
        # json.dumps 的引号也计入长度：500 + 2 = 502
        assert "共 502 字符" in text

    def test_entry_render_kinds(self):
        added = DiffEntry("$.a", "added", None, 1).render()
        removed = DiffEntry("$.b", "removed", 2, None).render()
        changed = DiffEntry("$.c", "changed", "x", "y").render()
        assert added == "+ $.a = 1"
        assert removed == "- $.b = 2"
        assert changed == '~ $.c: "x" → "y"'

    def test_format_report_identical(self):
        assert format_diff_report(diff_json(1, 1)) == "两个 JSON 完全一致"

    def test_format_report_counts_and_cap(self):
        old = {str(i): i for i in range(50)}
        new = {str(i): i + 1 for i in range(50)}
        report = format_diff_report(diff_json(old, new), max_entries=10)
        lines = report.splitlines()
        assert lines[0] == "共 50 处差异（显示前 10 条）:"
        assert len(lines) == 11

    def test_format_report_truncated_note(self):
        big = list(range(50_000))
        report = format_diff_report(diff_json(big, [0]))
        assert "已停止" in report

    def test_weird_key_quoted(self):
        result = diff_json({}, {"a.b": 1})
        assert result.count == 1
        assert result.entries[0].path == '$."a.b"'


class TestUnifiedDiff:
    def test_no_difference_empty(self):
        assert unified_diff("a\nb", "a\nb") == ""

    def test_basic_change(self):
        diff = unified_diff("a\nb\nc", "a\nB\nc", context_lines=1)
        assert "-b" in diff
        assert "+B" in diff
        assert "原响应" in diff and "新响应" in diff

    def test_truncation(self):
        # 每行都不同且无可对齐公共行：1000 删 + 1000 增 = 2002 行 diff
        old = "\n".join(f"line{i}" for i in range(1000))
        new = "\n".join(f"LINE{i}" for i in range(1000))
        diff = unified_diff(old, new, max_lines=50)
        assert "已截断" in diff
        assert len(diff.splitlines()) == 51

    def test_empty_inputs(self):
        assert unified_diff("", "") == ""
