"""JSON 树数据层（app/jsontree.py）的单元测试。

锁住三件事：
1. **子节点懒加载**——这是树视图撑得住大响应的前提；展开前不得实例化 Node。
2. **路径 / 类型 / 值文本**——复制路径、类型染色、值列都依赖这些，错一处就整列错。
3. **体量与合法性边界**——超限和非法 JSON 都要抛 JsonTreeError（由 UI 决定怎么提示）。
"""

from __future__ import annotations

import json

import pytest

from app.jsontree import (
    TREE_MAX_BYTES,
    VALUE_PREVIEW_LIMIT,
    JsonNode,
    JsonTreeError,
    parse_tree,
    walk,
)


def _root(obj) -> JsonNode:
    return parse_tree(json.dumps(obj, ensure_ascii=False).encode())


class TestLazyChildren:
    def test_children_not_built_before_access(self):
        root = _root({"data": [{"id": i} for i in range(100)]})
        assert not root.expanded_children
        rows = root.rows()
        assert root.expanded_children
        assert len(rows) == 1

    def test_rows_are_cached_by_identity(self):
        """缓存不只是为了快：Node 身份必须稳定，搜索命中才找得回同一行。"""
        root = _root({"a": 1})
        assert root.rows() is root.rows()

    def test_scalar_has_no_children(self):
        root = _root({"a": 1})
        leaf = root.rows()[0]
        assert leaf.rows() == []
        assert not leaf.is_container


class TestLabelsAndTypes:
    def test_root_label_and_path(self):
        root = _root({"a": 1})
        assert root.label == "$"
        assert root.path == "$"
        assert root.type_name == "object"
        assert root.value_text.startswith("{")

    def test_object_child(self):
        leaf = _root({"msg": "你好"}).rows()[0]
        assert leaf.label == "msg"
        assert leaf.path == "$.msg"
        assert leaf.type_name == "string"
        assert leaf.value_text == '"你好"'

    def test_array_child_uses_bracket_index(self):
        arr = _root({"a": [10, 20]}).rows()[0]
        second = arr.rows()[1]
        assert second.label == "[1]"
        assert second.path == "$.a[1]"
        assert second.type_name == "number"
        assert second.value_text == "20"

    def test_key_needing_brackets_in_path(self):
        leaf = _root({"a-b": 1, "": 2}).rows()[0]
        assert leaf.path == '$["a-b"]'
        assert _root({"a-b": 1, "": 2}).rows()[1].path == '$[""]'

    @pytest.mark.parametrize(
        "literal, type_name, text",
        [
            ("null", "null", "null"),
            ("true", "boolean", "true"),
            ("1.5", "number", "1.5"),
            ('"s"', "string", '"s"'),
        ],
    )
    def test_scalar_types(self, literal, type_name, text):
        root = parse_tree(literal.encode())
        assert root.type_name == type_name
        assert root.value_text == text

    def test_container_preview_shows_inline_content(self):
        # Fiddler / Charles 风格：折叠态也内联预览前几项，而不是只显示 {2} / [3]
        rows = _root({"obj": {"x": 1, "y": 2}, "arr": [1, 2, 3]}).rows()
        assert rows[0].value_text == "{x: 1, y: 2}"
        assert rows[1].value_text == "[1, 2, 3]"

    def test_preview_caps_items_and_nests(self):
        # 顶层只取前 3 项 + "…"；嵌套容器只标 {…} / […]，不递归
        node = _root({"a": 1, "b": [1], "c": {"k": 2}, "d": 4, "e": 5})
        text = node.preview_text()
        assert text.startswith("{")
        assert "…" in text
        assert "{…}" in text and "[…]" in text

    def test_preview_respects_limit(self):
        node = _root({"a": 1, "b": 2, "c": 3, "d": 4})
        assert node.preview_text(limit=2).count(",") == 2   # 2 项 + …



class TestLongValues:
    def test_preview_truncated_but_full_text_kept(self):
        leaf = _root({"blob": "x" * 500}).rows()[0]
        assert leaf.truncated
        assert len(leaf.value_text) == VALUE_PREVIEW_LIMIT + 1   # + 省略号
        assert leaf.value_text.endswith("…")
        # 完整值一字符不能少：tooltip / 复制值全靠它
        assert len(leaf.full_text) == 502

    def test_short_value_not_marked_truncated(self):
        assert not _root({"a": "short"}).rows()[0].truncated


class TestSubtreeJson:
    def test_subtree_json_is_indented(self):
        node = _root({"a": {"b": 1}}).rows()[0]
        dumped = node.subtree_json()
        assert json.loads(dumped) == {"b": 1}
        assert "\n" in dumped          # indent=2


class TestWalk:
    def test_walk_visits_every_node(self):
        # $ + data + 2 个数组元素对象 + 2 个叶子 = 6
        root = _root({"data": [{"id": 1}, {"id": 2}]})
        assert sum(1 for _ in walk(root)) == 6

    def test_walk_materializes_children(self):
        root = _root({"a": {"b": 1}})
        assert not root.expanded_children
        list(walk(root))
        assert root.expanded_children


class TestErrors:
    def test_empty_body(self):
        with pytest.raises(JsonTreeError):
            parse_tree(b"")

    def test_invalid_json(self):
        with pytest.raises(JsonTreeError):
            parse_tree(b"not json at all")

    def test_is_value_error_subclass(self):
        """继承 ValueError：调用方能一次接住 json.JSONDecodeError 与本错误。"""
        assert issubclass(JsonTreeError, ValueError)

    def test_too_large_rejected_without_parsing(self):
        with pytest.raises(JsonTreeError) as exc:
            parse_tree(b'{"a":1}' + b" " * TREE_MAX_BYTES)
        assert "too large" in str(exc.value)

    def test_scalar_root_is_supported(self):
        assert parse_tree(b'"just a string"').type_name == "string"
        assert parse_tree(b"[1,2]").type_name == "array"
