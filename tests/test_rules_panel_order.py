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


# ---------------------------------------------------------------- 只显示启用


class TestEnabledFilter:
    def test_filter_hides_disabled(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        three_rules.update(three_rules.all()[1].id, enabled=False)
        panel.refresh()
        assert panel.table.rowCount() == 3        # 未开过滤，全显
        panel.only_enabled_cb.setChecked(True)
        assert panel.table.rowCount() == 2
        names = [panel.table.item(i, 0).text() for i in range(2)]
        assert names == ["规则甲", "规则丙"]

    def test_filter_keeps_hidden_rules_in_place_on_move(self, qapp, three_rules):
        """过滤下移动可见行，隐藏的停用规则不应被挤到列表末尾。"""
        panel = RulesPanel(three_rules)
        three_rules.update(three_rules.all()[1].id, enabled=False)  # 乙停用
        panel.only_enabled_cb.setChecked(True)
        panel.table.selectRow(1)                  # 丙（可见第 2 行）
        panel._on_move(-1)                        # 丙上移到甲前面
        names = [r.name for r in three_rules.all()]
        # 隐藏的乙保持在原相对位置（甲丙之间），不被挤到末尾
        assert names == ["规则丙", "规则乙", "规则甲"]

    def test_filter_drop_semantics(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        three_rules.update(three_rules.all()[0].id, enabled=False)  # 甲停用
        panel.only_enabled_cb.setChecked(True)
        # 可见 [乙, 丙]：丙(可见行1)拖到 dst=0 → [丙, 乙]
        panel._on_row_dropped(1, 0)
        names = [r.name for r in three_rules.all()]
        assert names == ["甲", "丙", "乙"] or names == ["规则甲", "规则丙", "规则乙"]
        assert [r.name for r in three_rules.all() if r.enabled] == [
            "规则丙", "规则乙"
        ]

    def test_current_rule_via_display_ids(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        three_rules.update(three_rules.all()[0].id, enabled=False)
        panel.only_enabled_cb.setChecked(True)
        panel.table.selectRow(0)
        assert panel._current_rule().name == "规则乙"

    def test_toggle_enable_keeps_selection_visible(self, qapp, three_rules):
        """过滤中停用某规则：它从列表消失，选中不崩。"""
        panel = RulesPanel(three_rules)
        panel.only_enabled_cb.setChecked(True)
        panel.table.selectRow(0)
        rule = panel._current_rule()
        panel._toggle_enable(rule.id)             # 甲停用 → 消失
        assert panel.table.rowCount() == 2
        assert rule.id not in panel._display_ids

    def test_hit_update_respects_filter(self, qapp, three_rules):
        """被过滤隐藏的规则命中时不越界、不崩。"""
        import time as _time

        panel = RulesPanel(three_rules)
        rule = three_rules.all()[0]
        panel.only_enabled_cb.setChecked(True)
        three_rules.update(rule.id, enabled=False)
        panel.refresh()
        rule.hits = 5
        rule.last_hit = _time.time()
        panel.update_hit(rule.id)                 # 隐藏中：应静默跳过
        assert panel.table.rowCount() == 2


# ---------------------------------------------------------------- 表格质感


class TestTablePolish:
    def test_rules_table_styling(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        assert panel.table.alternatingRowColors() is True
        assert panel.table.showGrid() is False
        assert panel.table.verticalHeader().defaultSectionSize() == 22

    def test_traffic_table_row_height(self, qapp, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("MITEPROXY_HOME", str(home))
        from app.ui.traffic_table import TrafficTable

        table = TrafficTable()
        assert table.verticalHeader().defaultSectionSize() == 22

    def test_theme_has_polish_tokens(self):
        from app.ui import theme

        for key in ("alt_row", "header_bg", "grid_line"):
            assert key in theme.COLORS
        qss = theme.stylesheet()
        assert "alternate-background-color" in qss
        assert "QHeaderView::section" in qss


# ------------------------------------------------- 停用时的重复匹配提示

class TestToggleDuplicateWarning:
    """停用规则时若还有相同匹配的启用规则，必须明确告知（防"停用不生效"困惑）。"""

    @pytest.fixture
    def dup_store(self, tmp_path):
        s = RuleStore(path=tmp_path / "rules.json")
        for name in ("规则一", "规则二"):
            r = Rule.create(name)
            r.match = Match(type="contains", value="/api/same")
            s.add(r)
        return s

    def _captured_info(self, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        calls = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: calls.append(a) or QMessageBox.StandardButton.Ok),
        )
        return calls

    @staticmethod
    def _all_text(args) -> str:
        return " ".join(str(x) for x in args)

    def test_disable_warns_when_duplicate_enabled(self, qapp, dup_store, monkeypatch):
        calls = self._captured_info(monkeypatch)
        panel = RulesPanel(dup_store)
        first = dup_store.all()[0]
        panel._toggle_enable(first.id)
        assert dup_store.get(first.id).enabled is False  # 停用照常生效
        assert len(calls) == 1
        assert "规则二" in self._all_text(calls[0])  # 提示里点出仍会命中的规则

    def test_disable_no_warning_without_duplicate(self, qapp, dup_store, monkeypatch):
        calls = self._captured_info(monkeypatch)
        panel = RulesPanel(dup_store)
        # 先停用规则二，再停用规则一就没有重复启用了
        second = dup_store.all()[1]
        dup_store.update(second.id, enabled=False)
        panel._toggle_enable(dup_store.all()[0].id)
        assert calls == []

    def test_enable_never_warns(self, qapp, dup_store, monkeypatch):
        calls = self._captured_info(monkeypatch)
        panel = RulesPanel(dup_store)
        first = dup_store.all()[0]
        dup_store.update(first.id, enabled=False)
        panel._toggle_enable(first.id)  # 这是"启用"方向
        assert calls == []
