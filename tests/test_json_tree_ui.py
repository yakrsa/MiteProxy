"""JSON「树」视图的 UI 测试。

重点不是画得好不好看，而是这几条**最容易漏**的行为：

1. 树 + 搜索联动：BodyPane.highlight() 必须走到树这条分支，否则「搜不到东西」。
2. 非 JSON / 超大体量：必须回落文本视图并说明原因，不能留白屏。
3. 视图切换不能互相污染：切回 JSON 要恢复换行开关、收起树专用按钮。
4. 右键复制：值 / 键 / 路径 / 整个节点 JSON 四条都要拿到正确的东西。
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QApplication

from app.bodyview import VIEW_JSON, VIEW_TREE
from app.jsontree import TREE_MAX_BYTES, TREE_WARN_BYTES
from app.ui.detail_panel import BodyPane

_FLOW = {"code": 0, "msg": "你好", "data": [{"id": 1, "name": "alice"}]}
_BODY = json.dumps(_FLOW, ensure_ascii=False).encode()


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _pane(body: bytes = _BODY, content_type: str = "application/json") -> BodyPane:
    pane = BodyPane()
    pane.show_body({"Content-Type": content_type}, body)
    pane.set_mode(VIEW_TREE)
    return pane


def _rows(model, index=QModelIndex()) -> list[str]:
    return [model.data(model.index(r, 0, index), Qt.ItemDataRole.DisplayRole)
            for r in range(model.rowCount(index))]


class TestTreeViewSwitch:
    def test_mode_switch_shows_tree(self, qapp):
        pane = _pane()
        assert pane.body_stack.currentWidget() is pane.tree_view
        assert pane.current_mode == VIEW_TREE
        pane.deleteLater()

    def test_wrap_checkbox_hidden_in_tree(self, qapp):
        # 树里没有换行概念，留着会让人以为是坏的
        pane = _pane()
        assert pane.wrap_cb.isHidden()
        assert not pane.expand_btn.isHidden()
        pane.deleteLater()

    def test_switching_back_restores_controls(self, qapp):
        pane = _pane()
        pane.set_mode(VIEW_JSON)
        assert pane.body_stack.currentWidget() is pane.body_view
        assert not pane.wrap_cb.isHidden()
        assert pane.expand_btn.isHidden()
        pane.deleteLater()

    def test_auto_mode_still_picks_text_view(self, qapp):
        """默认必须是文本视图：树不能抢原文/JSON 的位置。"""
        pane = BodyPane()
        pane.show_body({"Content-Type": "application/json"}, _BODY)
        assert pane.current_mode == VIEW_JSON
        assert pane.body_stack.currentWidget() is pane.body_view
        pane.deleteLater()


class TestTreeStructure:
    def test_top_level_rows(self, qapp):
        pane = _pane()
        model = pane.tree_view.model()
        root = model.index(0, 0, QModelIndex())
        assert _rows(model, root) == ["code", "msg", "data"]
        pane.deleteLater()

    def test_nested_node_and_path(self, qapp):
        pane = _pane()
        model = pane.tree_view.model()
        root = model.index(0, 0, QModelIndex())
        data_row = model.index(2, 0, root)
        item = model.index(0, 0, data_row)
        node = model.node_at(item)
        assert node.path == "$.data[0]"
        # data 本身是数组（1 项）；它的第 0 项才是含 2 个键的对象
        assert model.data(model.index(2, 1, root),
                          Qt.ItemDataRole.DisplayRole) == "[1]"
        assert model.data(model.index(0, 1, data_row),
                          Qt.ItemDataRole.DisplayRole) == "{2}"
        pane.deleteLater()

    def test_header_labels(self, qapp):
        pane = _pane()
        model = pane.tree_view.model()
        assert model.headerData(0, Qt.Orientation.Horizontal,
                                Qt.ItemDataRole.DisplayRole) == "键"
        assert model.headerData(1, Qt.Orientation.Horizontal,
                                Qt.ItemDataRole.DisplayRole) == "值"
        pane.deleteLater()

    def test_deep_rows_not_materialized(self, qapp):
        """懒加载：没点开的容器不产生行数据（大文档不卡的关键）。"""
        big = json.dumps({"root": {"deep": [{"i": i} for i in range(1000)]}}).encode()
        pane = _pane(big)
        model = pane.tree_view.model()
        root = model.index(0, 0, QModelIndex())
        # 根的子节点已物化，但更深的层级还没
        assert _rows(model, root) == ["root"]
        pane.deleteLater()

    def test_clear_releases_model(self, qapp):
        pane = _pane()
        pane.clear()
        assert pane.tree_view.model() is None
        pane.deleteLater()


class TestTreeSearch:
    def test_highlight_counts_and_locates(self, qapp):
        pane = _pane()
        hits = pane.highlight("ali", False)
        assert hits == 1                       # $.data[0].name
        model = pane.tree_view.model()
        assert len(model._hits) == 1
        pane.deleteLater()

    def test_highlight_matches_key(self, qapp):
        pane = _pane()
        assert pane.highlight("data", False) >= 1
        pane.deleteLater()

    def test_clear_highlight(self, qapp):
        pane = _pane()
        pane.highlight("alice", False)
        assert pane.highlight("", False) == 0
        assert not pane.tree_view.model()._hits
        pane.deleteLater()

    def test_no_match_returns_zero(self, qapp):
        pane = _pane()
        assert pane.highlight("zzz-not-exist", False) == 0
        pane.deleteLater()

    def test_case_sensitive_search(self, qapp):
        pane = _pane()
        assert pane.highlight("ALICE", True) == 0
        assert pane.highlight("ALICE", False) == 1
        pane.deleteLater()


class TestTreeFallback:
    def test_non_json_falls_back_to_text(self, qapp):
        pane = _pane(b"hello world", "text/plain")
        assert pane.body_stack.currentWidget() is pane.body_view
        assert "JSON" in pane.view_note.text()
        pane.deleteLater()

    def test_too_large_falls_back_with_reason(self, qapp):
        big = b'{"blob":"' + b"x" * (TREE_MAX_BYTES + 10) + b'"}'
        pane = _pane(big)
        assert pane.body_stack.currentWidget() is pane.body_view
        assert str(TREE_MAX_BYTES // 1024) in pane.view_note.text()
        pane.deleteLater()

    def test_large_but_allowed_warns(self, qapp):
        """在阈值内的大 JSON 仍可建树，但提示一句展开会慢。"""
        body = json.dumps({"blob": "x" * (TREE_WARN_BYTES + 10)}).encode()
        pane = _pane(body)
        assert pane.body_stack.currentWidget() is pane.tree_view
        assert "展开" in pane.view_note.text()
        pane.deleteLater()


class TestTreeCopy:
    def test_copy_value_and_path(self, qapp):
        pane = _pane()
        model = pane.tree_view.model()
        root = model.index(0, 0, QModelIndex())
        pane.tree_view.setCurrentIndex(model.index(1, 0, root))   # msg
        pane.tree_view.copy_value()
        assert QApplication.clipboard().text() == '"你好"'
        pane.tree_view.copy_path()
        assert QApplication.clipboard().text() == "$.msg"
        pane.tree_view.copy_key()
        assert QApplication.clipboard().text() == "msg"
        pane.deleteLater()

    def test_copy_subtree_json(self, qapp):
        pane = _pane()
        model = pane.tree_view.model()
        root = model.index(0, 0, QModelIndex())
        pane.tree_view.setCurrentIndex(model.index(2, 0, root))   # data
        pane.tree_view.copy_subtree()
        assert json.loads(QApplication.clipboard().text()) == _FLOW["data"]
        pane.deleteLater()

    def test_copy_without_selection_is_noop(self, qapp):
        pane = _pane()
        QApplication.clipboard().setText("unchanged")
        pane.tree_view.setCurrentIndex(QModelIndex())
        pane.tree_view.copy_value()
        assert QApplication.clipboard().text() == "unchanged"
        pane.deleteLater()
