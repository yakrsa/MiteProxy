"""FIX 工具页 UI 测试（offscreen Qt，不需要真显示）。

覆盖：树渲染（单/多消息、组折叠）、状态区文案（校验 ✓/✗、| 分隔标注）、
tool_panel 接线（第五子页与路由）。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from app.fix import FixGroup
from app.ui.fix_panel import FixPanel
from app.ui.tool_panel import ToolPanel


def make_fix(body_fields, begin: str = "FIX.4.4") -> str:
    body = "".join("{0}={1}\x01".format(t, v) for t, v in body_fields)
    head = "8={0}\x019={1}\x01".format(begin, len(body.encode())) + body
    return head + "10={0:03d}\x01".format(sum(ord(c) for c in head) % 256)


ORDER = [
    (35, "D"), (49, "SENDER"), (56, "TARGET"), (34, "42"),
    (52, "20261023-14:30:00.000"), (11, "ORD-1"), (55, "000001"),
    (54, "1"), (38, "100"), (40, "2"), (44, "10.50"), (59, "0"),
]


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def panel(qapp):
    p = FixPanel()
    yield p
    p.deleteLater()


def _rows(tree) -> list[QTreeWidgetItem]:
    return [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]


class TestFixPanelTree:
    def test_single_message_tree(self, panel):
        panel.set_text(make_fix(ORDER))
        roots = _rows(panel.tree)
        assert len(roots) == 1
        # 根 = 消息；子节点 = 全部字段（8/9/35/…/10）
        assert roots[0].childCount() == len(ORDER) + 3
        assert "D" in roots[0].text(2)
        assert "新单" in roots[0].text(2)
        # 第一行子节点是 8 字段，注释列有字典内容
        first = roots[0].child(0)
        assert first.text(0) == "8"
        assert "开始字符串" in first.text(1)
        # 54=1 → 注释列有枚举释义
        side = roots[0].child(
            [roots[0].child(i).text(0) for i in range(roots[0].childCount())].index("54"))
        assert "买入" in side.text(3)

    def test_unknown_tag_shown_as_uncollected(self, panel):
        panel.set_text(make_fix(ORDER + [(9001, "zz")]))
        root = _rows(panel.tree)[0]
        tags = [root.child(i).text(0) for i in range(root.childCount())]
        row = root.child(tags.index("9001"))
        assert "未收录" in row.text(1)
        assert "字典未收录" in row.text(3)

    def test_group_rendered_as_foldable_node(self, panel):
        body = [(35, "W"), (49, "S"), (56, "T"), (262, "REQ-1"), (268, "2")]
        for i in range(2):
            body += [(279, "0"), (269, str(i)), (278, "E{0}".format(i)),
                     (270, "10.5"), (271, "100")]
        panel.set_text(make_fix(body))
        root = _rows(panel.tree)[0]
        group_node = None
        for i in range(root.childCount()):
            if isinstance(root.child(i), QTreeWidgetItem) and root.child(i).text(0) == "268":
                group_node = root.child(i)
                break
        assert group_node is not None
        assert "行情条目" in group_node.text(1)
        assert "2" in group_node.text(2)
        assert group_node.childCount() == 2          # 两个实例
        assert group_node.child(0).childCount() == 5  # 每实例 5 个字段

    def test_multiple_messages(self, panel):
        text = make_fix(ORDER) + make_fix([(35, "8"), (49, "S"), (56, "T")])
        panel.set_text(text)
        assert len(_rows(panel.tree)) == 2
        assert "消息 1" in _rows(panel.tree)[0].text(1)
        assert "消息 2" in _rows(panel.tree)[1].text(1)

    def test_readable_view_uses_pipe(self, panel):
        panel.set_text(make_fix(ORDER))
        panel.view_combo.setCurrentIndex(panel.view_combo.findData("raw"))
        text = panel.raw_view.toPlainText()
        assert "|" in text
        assert "\x01" not in text
        assert "35=D" in text


class TestFixPanelStatus:
    def test_valid_message_ok_status(self, panel):
        panel.set_text(make_fix(ORDER))
        assert "BodyLength ✓" in panel.status_label.text()
        assert "CheckSum ✓" in panel.status_label.text()

    def test_checksum_mismatch_flagged(self, panel):
        text = make_fix(ORDER).rsplit("\x0110=", 1)[0] + "\x0110=001\x01"
        panel.set_text(text)
        assert "CheckSum ✗" in panel.status_label.text()

    def test_pipe_input_skips_checksum(self, panel):
        panel.set_text(make_fix(ORDER).replace("\x01", "|"))
        assert "未校验" in panel.status_label.text()

    def test_non_fix_text_hint(self, panel):
        panel.input_edit.setPlainText("hello world")
        assert "未识别为 FIX" in panel.status_label.text()
        assert panel.tree.topLevelItemCount() == 0

    def test_garbage_input_does_not_crash(self, panel):
        panel.set_text("8=FIX.4.4\x01abc=1\x0135=D")
        assert panel.tree.topLevelItemCount() >= 0   # 不抛即通过


class TestToolPanelWiring:
    def test_fix_tab_exists(self, qapp):
        tp = ToolPanel()
        assert tp.fix_panel is not None
        tp.show_page("fix")
        assert tp.current_key == "fix"
        assert tp.tabs.currentWidget() is tp.fix_panel
        tp.set_body_text("8=FIX.4.4|9=5|35=D", page="fix")
        assert tp.fix_panel.input_edit.toPlainText() == "8=FIX.4.4|9=5|35=D"
        tp.deleteLater()
