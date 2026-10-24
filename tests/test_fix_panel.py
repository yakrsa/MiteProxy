"""FIX 工具页 UI 测试（offscreen Qt，不需要真显示）。

覆盖：tab 渲染（单/多消息、组折叠、错误徽标、条数上限）、状态区文案
（校验 ✓/✗、| 分隔标注、多消息总览）、跳转按钮、tool_panel 接线。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from app import fixprofile
from app.fix import FixGroup
from app.ui.fix_panel import MAX_TAB_MESSAGES, FixPanel
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


def _cur_tree(panel) -> QTreeWidgetItem:
    """当前 tab 里的字段树（tab 页 = 摘要 QLabel + 树）。"""
    page = panel.tab_widget.currentWidget()
    return page.layout().itemAt(1).widget()


def _summary_of(panel, index: int) -> str:
    page = panel.tab_widget.widget(index)
    return page.layout().itemAt(0).widget().text()


class TestFixPanelTree:
    def test_single_message_tree(self, panel):
        panel.set_text(make_fix(ORDER))
        assert panel.tab_widget.count() == 1
        root = _cur_tree(panel).invisibleRootItem()
        # 子节点 = 全部字段（8/9/35/…/10）
        assert root.childCount() == len(ORDER) + 3
        assert root.child(0).text(0) == "8"
        assert "开始字符串" in root.child(0).text(1)
        # 54=1 → 注释列有枚举释义
        tags = [root.child(i).text(0) for i in range(root.childCount())]
        side = root.child(tags.index("54"))
        assert "买入" in side.text(3)

    def test_unknown_tag_shown_as_uncollected(self, panel):
        panel.set_text(make_fix(ORDER + [(9001, "zz")]))
        root = _cur_tree(panel).invisibleRootItem()
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
        root = _cur_tree(panel).invisibleRootItem()
        group_node = None
        for i in range(root.childCount()):
            child = root.child(i)
            if isinstance(child, QTreeWidgetItem) and child.text(0) == "268":
                group_node = child
                break
        assert group_node is not None
        assert "行情条目" in group_node.text(1)
        assert "2" in group_node.text(2)
        assert group_node.childCount() == 2          # 两个实例
        assert group_node.child(0).childCount() == 5  # 每实例 5 个字段

    def test_readable_view_uses_pipe(self, panel):
        panel.set_text(make_fix(ORDER))
        panel.view_combo.setCurrentIndex(panel.view_combo.findData("raw"))
        text = panel.raw_view.toPlainText()
        assert "|" in text
        assert "\x01" not in text
        assert "35=D" in text

    def test_tag_column_fits_private_tag(self, panel):
        # 52px 固定列宽 - 20px 缩进装不下 5 位私有 tag，会被省略成 `1…`
        # → tag 号看不全就没法对字段。列宽必须按内容撑开。
        panel.set_text(make_fix(ORDER + [(16015, "0")]))
        tree = _cur_tree(panel)
        need = (tree.indentation()
                + tree.fontMetrics().horizontalAdvance("16015"))
        assert tree.columnWidth(0) >= need

    def test_private_tag_explained_as_extension(self, panel):
        panel.set_text(make_fix(ORDER + [(16015, "0"), (4999, "x")]))
        root = _cur_tree(panel).invisibleRootItem()
        tags = [root.child(i).text(0) for i in range(root.childCount())]
        private_row = root.child(tags.index("16015"))
        assert "未收录" in private_row.text(1)
        assert "私有扩展" in private_row.text(3)
        # 5000 以下是标准区间，未知就该说「字典未收录」，不冒充私有扩展
        normal_row = root.child(tags.index("4999"))
        assert "私有扩展" not in normal_row.text(3)
        assert "字典未收录" in normal_row.text(3)

    def test_cells_expose_full_text_in_tooltip(self, panel):
        # 列宽有限，长值 / 长注释会被省略；悬停要能看到完整内容
        panel.set_text(make_fix(ORDER + [(16015, "0")]))
        root = _cur_tree(panel).invisibleRootItem()
        tags = [root.child(i).text(0) for i in range(root.childCount())]
        row = root.child(tags.index("16015"))
        assert row.toolTip(0) == "tag 16015"
        assert "私有扩展" in row.toolTip(3)
        assert root.child(0).toolTip(0) == "tag 8"


class TestFixPanelTabs:
    """多消息 tab 化：标题 / 徽标 / 上限 / 跳转 / 单条退化。"""

    @staticmethod
    def _batch(count: int, bad_at=()) -> str:
        parts = []
        for i in range(count):
            text = make_fix([(35, "8"), (49, "S"), (56, "T"), (34, str(i))])
            if (i + 1) in bad_at:
                text = text.rsplit("\x0110=", 1)[0] + "\x0110=001\x01"
            parts.append(text)
        return "".join(parts)

    def test_multiple_messages_become_tabs(self, panel):
        panel.set_text(self._batch(3))
        assert panel.tab_widget.count() == 3
        assert panel.tab_widget.tabText(0) == "#1 35=8"
        assert panel.tab_widget.tabText(2) == "#3 35=8"
        # 多条时 tab 栏可见（单条时隐藏，见下单测）
        assert panel.tab_widget.tabBar().isHidden() is False

    def test_log_lines_one_per_line_become_tabs(self, panel):
        # 真实日志形态：每条各自占一行、行首带时间戳前缀。
        # 旧的垃圾正则不跨行（`.` 不含 `\n`），三条会被并成一条 → 没有 tab
        lines = [
            "[09:30:0{0}.123] {1}".format(
                i, make_fix([(35, t), (49, "S"), (56, "T"), (34, str(i))]))
            for i, t in enumerate(["0", "8", "D"], start=1)
        ]
        panel.set_text("\n".join(lines))
        assert panel.tab_widget.count() == 3
        assert [panel.tab_widget.tabText(i) for i in range(3)] == [
            "#1 35=0", "#2 35=8", "#3 35=D"]
        assert panel.tab_widget.tabBar().isHidden() is False
        assert "共 3 条消息" in panel.status_label.text()

    def test_bad_message_tab_has_badge_and_color(self, panel):
        panel.set_text(self._batch(3, bad_at=(2,)))
        assert panel.tab_widget.tabText(1) == "#2 35=8 ✗"
        # 错误 tab 用错误色（theme error token 浅色 #cf222e）
        assert panel.tab_widget.tabBar().tabTextColor(1).name() == "#cf222e"
        assert panel.tab_widget.tabBar().tabTextColor(0).name() != "#cf222e"
        # 摘要行也带 ✗ 信息
        assert "CheckSum ✗" in _summary_of(panel, 1)
        assert "CheckSum ✓" in _summary_of(panel, 0)

    def test_tab_count_capped_and_status_hints(self, panel):
        panel.set_text(self._batch(15))
        assert panel.tab_widget.count() == MAX_TAB_MESSAGES
        assert "共 15 条消息" in panel.status_label.text()
        assert "显示前 10 条" in panel.status_label.text()
        # 可读原文始终含全部（tab 截断不影响原文视图）
        panel.view_combo.setCurrentIndex(panel.view_combo.findData("raw"))
        assert panel.raw_view.toPlainText().count("\n\n") == 14

    def test_jump_button_visible_and_jumps(self, panel):
        panel.set_text(self._batch(5, bad_at=(3,)))
        btn = panel.jump_bad_btn
        # isVisible() 受父部件显示状态影响（offscreen 下 panel 未 show），
        # 这里断言的是「显式隐藏」状态
        assert btn.isHidden() is False
        assert "1" in btn.text()
        panel.tab_widget.setCurrentIndex(0)
        panel._jump_to_first_bad()
        assert panel.tab_widget.currentIndex() == 2

    def test_jump_button_hidden_without_problems(self, panel):
        panel.set_text(self._batch(2))
        assert panel.jump_bad_btn.isHidden() is True

    def test_single_message_hides_tab_bar(self, panel):
        panel.set_text(make_fix(ORDER))
        assert panel.tab_widget.count() == 1
        assert panel.tab_widget.tabBar().isHidden() is True

    def test_log_prefix_multi_message(self, panel):
        # 日志复制形态：每条带时间戳前缀，仍能逐条 tab 化
        text = ("[09:30:01.123] " + make_fix([(35, "8"), (34, "1")])
                + "[09:30:02.456] " + make_fix([(35, "D"), (34, "2")]))
        panel.set_text(text)
        assert panel.tab_widget.count() == 2
        assert panel.tab_widget.tabText(0) == "#1 35=8"
        assert panel.tab_widget.tabText(1) == "#2 35=D"
        assert "BodyLength ✓" in _summary_of(panel, 0)


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

    def test_multi_message_summary_lists_bad_ones(self, panel):
        text = (make_fix([(35, "8"), (34, "1")])
                + make_fix([(35, "D"), (34, "2")]).rsplit("\x0110=", 1)[0]
                + "\x0110=001\x01")
        panel.set_text(text)
        status = panel.status_label.text()
        assert "共 2 条消息" in status
        assert "#2" in status           # 坏消息序号进总览

    def test_non_fix_text_hint(self, panel):
        panel.input_edit.setPlainText("hello world")
        assert "未识别为 FIX" in panel.status_label.text()
        assert panel.tab_widget.count() == 0

    def test_garbage_input_does_not_crash(self, panel):
        panel.set_text("8=FIX.4.4\x01abc=1\x0135=D")
        assert panel.tab_widget.count() >= 0   # 不抛即通过


class TestFixPanelDictionary:
    """合作方字典：导入 → 下拉切换 → 私有 tag 有名字（app/fixprofile）。"""

    @pytest.fixture()
    def home(self, qapp, tmp_path, monkeypatch):
        # 面板通过 fixprofile 读写字典目录，指到 tmp 才是真隔离
        monkeypatch.setattr(fixprofile, "CONFIG_DIR", tmp_path)
        return tmp_path

    @staticmethod
    def _csv(tmp_path) -> str:
        path = tmp_path / "xx期货.csv"
        path.write_text(
            "tag,英文名,中文名,类型,枚举,组成员\n"
            "10001,LocalOrderID,本地订单号,String,,\n"
            "10002,LegSide,腿方向,char,1=买;2=卖,\n"
            "10010,NoSubOrders,子订单数,NumInGroup,,10011\n"
            "10011,SubOrderID,子订单号,String,,\n",
            encoding="utf-8")
        return str(path)

    def test_import_adds_profile_and_switches(self, home):
        panel = FixPanel()
        assert panel.dict_combo.count() == 1          # 初始只有内置
        assert panel.import_profile(self._csv(home)) is True
        assert panel.dict_combo.count() == 2
        assert panel.dict_combo.currentData() == "xx期货"
        assert "已导入字典" in panel.status_label.text()
        # 选择会落盘（下次启动仍是这家）
        assert fixprofile.get_active_slug() == "xx期货"
        panel.deleteLater()

    def test_private_field_named_after_import(self, home):
        panel = FixPanel()
        panel.import_profile(self._csv(home))
        panel.set_text(make_fix(ORDER + [(10001, "LOC-9"), (10002, "2")]))
        root = _cur_tree(panel).invisibleRootItem()
        tags = [root.child(i).text(0) for i in range(root.childCount())]
        assert "本地订单号" in root.child(tags.index("10001")).text(1)
        assert "卖" in root.child(tags.index("10002")).text(3)
        panel.deleteLater()

    def test_switch_back_to_builtin(self, home):
        panel = FixPanel()
        panel.import_profile(self._csv(home))
        panel.set_text(make_fix(ORDER + [(10001, "LOC-9")]))
        panel.dict_combo.setCurrentIndex(0)           # 内置
        root = _cur_tree(panel).invisibleRootItem()
        tags = [root.child(i).text(0) for i in range(root.childCount())]
        assert "未收录" in root.child(tags.index("10001")).text(1)
        assert fixprofile.get_active_slug() == ""
        panel.deleteLater()

    def test_custom_group_expands(self, home):
        panel = FixPanel()
        panel.import_profile(self._csv(home))
        panel.set_text(make_fix(ORDER + [
            (10010, "2"), (10011, "A"), (10011, "B")]))
        root = _cur_tree(panel).invisibleRootItem()
        node = None
        for i in range(root.childCount()):
            if root.child(i).text(0) == "10010":
                node = root.child(i)
        assert node is not None and node.childCount() == 2
        panel.deleteLater()

    def test_remove_current_profile(self, home, monkeypatch):
        panel = FixPanel()
        panel.import_profile(self._csv(home))
        # 删除走确认框：offscreen 下真模态会挂死，必须拦掉
        from PySide6.QtWidgets import QMessageBox
        monkeypatch.setattr("app.ui.fix_panel.dialogs.question",
                            lambda *a, **k: QMessageBox.StandardButton.Yes)
        assert panel.remove_current_profile() is True
        assert panel.dict_combo.count() == 1
        assert fixprofile.list_profiles() == []
        panel.deleteLater()

    def test_failed_import_keeps_current_dict(self, home):
        panel = FixPanel()
        panel.import_profile(self._csv(home))
        bad = home / "bad.csv"
        bad.write_text("这不是字段表\n", encoding="utf-8")
        assert panel.import_profile(str(bad)) is False
        assert panel.dict_combo.currentData() == "xx期货"
        assert "导入失败" in panel.status_label.text()
        panel.deleteLater()

    def test_reimport_same_file_updates_in_place(self, home):
        """改版后把同一个文件再导一次：覆盖旧内容，不多出一份。"""
        panel = FixPanel()
        path = self._csv(home)
        panel.import_profile(path)
        assert panel.dict_combo.count() == 2

        Path(path).write_text(
            "tag,英文名,中文名\n"
            "10001,LocalOrderID,本地订单号(新版)\n"
            "10003,NewField,新字段\n",
            encoding="utf-8")
        assert panel.import_profile(path) is True
        assert panel.dict_combo.count() == 2          # 覆盖，不是新增
        assert "已更新字典" in panel.status_label.text()
        assert "原 4 个" in panel.status_label.text()
        assert len(fixprofile.list_profiles()) == 1
        # 旧字段被替换成新含义，新字段立刻能解析
        panel.set_text(make_fix(ORDER + [(10001, "L"), (10003, "v")]))
        root = _cur_tree(panel).invisibleRootItem()
        tags = [root.child(i).text(0) for i in range(root.childCount())]
        assert "新版" in root.child(tags.index("10001")).text(1)
        assert "新字段" in root.child(tags.index("10003")).text(1)
        panel.deleteLater()

    def test_reimport_renamed_file_with_partner_comment(self, home):
        """换了文件名但写了 `# 合作方:`：仍认作同一家，不生成 -2 副本。"""
        panel = FixPanel()
        panel.import_profile(self._csv(home))
        other = home / "xx期货-2026Q4.csv"
        other.write_text(
            "# 合作方: xx期货\n"
            "tag,英文名\n10001,LocalOrderID\n10005,Extra\n",
            encoding="utf-8")
        assert panel.import_profile(str(other)) is True
        assert len(fixprofile.list_profiles()) == 1
        assert "已更新字典" in panel.status_label.text()
        panel.deleteLater()

    def test_template_copied_to_clipboard(self, home):
        from PySide6.QtWidgets import QApplication
        panel = FixPanel()
        panel._copy_template("csv")
        assert "tag" in QApplication.clipboard().text()
        panel.deleteLater()


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
