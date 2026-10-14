"""Mock 规则面板：名称列前置 + 拖拽/按钮调整顺序（DESIGN 3.4.3）。

盯这些点：
1. 名称列必须在第 0 列（用户第一眼看到规则用途），启用列后移；
2. 拖拽排序语义：dst 为「拖放前列表」的插入位置索引，pop 源行后
   dst > src 需 -1 修正；拖回原位是 no-op；
3. 排序结果要持久化（重新加载 RuleStore 顺序不变）；
4. 按钮移动（上移/下移）与拖拽走同一条 store.reorder 通路。
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.rules import Match, Rule, RuleStore  # noqa: E402
from app.ui.rules_panel import RuleTable, RulesPanel  # noqa: E402


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def store(tmp_path):
    return RuleStore(path=tmp_path / "rules.json")


def _add(store: RuleStore, name: str) -> Rule:
    rule = Rule.create(name)
    rule.match = Match(type="contains", value=name)
    return store.add(rule)


@pytest.fixture
def three_rules(store):
    _add(store, "规则甲")
    _add(store, "规则乙")
    _add(store, "规则丙")
    return store


# ---------------------------------------------------------------- 列布局


class TestColumnLayout:
    def test_name_is_first_column(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        assert panel.table.horizontalHeaderItem(0).text() == "名称"
        assert panel.table.horizontalHeaderItem(1).text() == "启用"

    def test_refresh_fills_name_column(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        assert panel.table.item(0, 0).text() == "规则甲"
        assert panel.table.item(1, 0).text() == "规则乙"
        assert panel.table.item(2, 0).text() == "规则丙"

    def test_hits_column_unchanged(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        assert panel.table.horizontalHeaderItem(5).text() == "命中"
        assert panel.table.item(0, 5).text() == "—"


# ---------------------------------------------------------------- 拖拽排序


class TestDragReorder:
    def test_row_dropped_signal_exists(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        assert isinstance(panel.table, RuleTable)
        assert hasattr(panel.table, "row_dropped")

    def test_drop_moves_row_down(self, qapp, three_rules):
        """第 0 行拖到表尾（dst=rowCount=3）→ 乙、丙、甲。"""
        panel = RulesPanel(three_rules)
        panel._on_row_dropped(0, 3)
        names = [r.name for r in three_rules.all()]
        assert names == ["规则乙", "规则丙", "规则甲"]

    def test_drop_moves_row_up(self, qapp, three_rules):
        """第 2 行拖到 dst=0（插到最前）→ 丙、甲、乙。"""
        panel = RulesPanel(three_rules)
        panel._on_row_dropped(2, 0)
        names = [r.name for r in three_rules.all()]
        assert names == ["规则丙", "规则甲", "规则乙"]

    def test_drop_semantics_dst_after_src(self, qapp, three_rules):
        """dst(2) > src(0)：语义是插到原列表 index 2 之前 → pop 后 insert(1)。"""
        panel = RulesPanel(three_rules)
        panel._on_row_dropped(0, 2)
        names = [r.name for r in three_rules.all()]
        # 甲 pop 掉剩 [乙, 丙]，insert(1) → 乙、甲、丙
        assert names == ["规则乙", "规则甲", "规则丙"]

    def test_drop_same_position_noop(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        panel._on_row_dropped(1, 1)
        names = [r.name for r in three_rules.all()]
        assert names == ["规则甲", "规则乙", "规则丙"]

    def test_drop_invalid_src_noop(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        panel._on_row_dropped(-1, 0)
        panel._on_row_dropped(99, 0)
        names = [r.name for r in three_rules.all()]
        assert names == ["规则甲", "规则乙", "规则丙"]

    def test_reorder_persisted(self, qapp, three_rules, tmp_path):
        panel = RulesPanel(three_rules)
        panel._on_row_dropped(2, 0)
        reloaded = RuleStore(path=tmp_path / "rules.json")
        reloaded.load()
        assert [r.name for r in reloaded.all()] == ["规则丙", "规则甲", "规则乙"]

    def test_selection_follows_moved_row(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        panel._on_row_dropped(2, 0)
        assert panel.table.currentRow() == 0


# ---------------------------------------------------------------- 按钮排序


class TestButtonReorder:
    def test_move_up_and_down(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        panel.table.selectRow(1)
        panel._on_move(-1)
        assert [r.name for r in three_rules.all()] == ["规则乙", "规则甲", "规则丙"]
        panel._on_move(1)
        assert [r.name for r in three_rules.all()] == ["规则甲", "规则乙", "规则丙"]

    def test_move_boundary_noop(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        panel.table.selectRow(0)
        panel._on_move(-1)  # 已在顶部
        assert [r.name for r in three_rules.all()] == ["规则甲", "规则乙", "规则丙"]


# ---------------------------------------------------------------- 右键菜单


class TestContextMenu:
    def _texts(self, menu):
        return [a.text() for a in menu.actions() if not a.isSeparator()]

    def _action(self, menu, text):
        return next(a for a in menu.actions() if a.text() == text)

    def test_row_menu_has_rule_operations(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        menu = panel._build_context_menu(0)
        texts = self._texts(menu)
        assert texts == ["编辑", "停用", "上移", "下移", "删除"]

    def test_row_menu_boundary_actions_disabled(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        top = panel._build_context_menu(0)
        assert self._action(top, "上移").isEnabled() is False
        assert self._action(top, "下移").isEnabled() is True
        bottom = panel._build_context_menu(2)
        assert self._action(bottom, "上移").isEnabled() is True
        assert self._action(bottom, "下移").isEnabled() is False

    def test_toggle_enable_text_and_effect(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        rule = three_rules.all()[0]
        assert rule.enabled is True
        # 菜单文字按当前状态显示「停用」
        assert self._action(panel._build_context_menu(0), "停用") is not None
        panel._toggle_enable(rule.id)
        assert three_rules.all()[0].enabled is False
        # 停用后菜单变「启用」
        menu = panel._build_context_menu(0)
        assert self._action(menu, "启用") is not None
        panel._toggle_enable(rule.id)
        assert three_rules.all()[0].enabled is True

    def test_toggle_persisted(self, qapp, three_rules, tmp_path):
        panel = RulesPanel(three_rules)
        rule_id = three_rules.all()[1].id
        panel._toggle_enable(rule_id)
        reloaded = RuleStore(path=tmp_path / "rules.json")
        reloaded.load()
        assert reloaded.all()[1].enabled is False

    def test_blank_menu_has_add_and_import(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        menu = panel._build_context_menu(-1)
        assert self._texts(menu) == ["新增", "导入 Fiddler 规则"]

    def test_row_menu_selects_row(self, qapp, three_rules):
        """右键某行后 currentRow 应指向该行（编辑/删除基于当前行）。"""
        panel = RulesPanel(three_rules)
        panel._build_context_menu(2)
        assert panel.table.currentRow() == 2
