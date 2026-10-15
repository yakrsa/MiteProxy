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

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.rules import Action, Match, Rule, RuleStore  # noqa: E402
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
    def test_checkbox_and_seq_are_first_columns(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        headers = [panel.table.horizontalHeaderItem(i).text() for i in range(9)]
        assert headers == [
            "选", "序号", "名称", "启用", "匹配", "动作", "来源", "命中", "创建时间"
        ]

    def test_created_at_column_new_rule_shows_time(self, qapp, three_rules):
        from datetime import datetime

        panel = RulesPanel(three_rules)
        text = panel.table.item(0, 8).text()
        assert text != "—"  # 新建规则有创建时间，不是占位符
        datetime.strptime(text, "%Y-%m-%d %H:%M")  # 本地时间格式

    def test_created_at_column_unknown_shows_dash(self, qapp, store):
        # 旧规则/导入规则无创建时间记录 → 显示「—」
        r = Rule("x", "老规则", True, Match(), Action())
        store.add(r)
        panel = RulesPanel(store)
        assert panel.table.item(0, 8).text() == "—"

    def test_refresh_fills_name_column(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        assert panel.table.item(0, 2).text() == "规则甲"
        assert panel.table.item(1, 2).text() == "规则乙"
        assert panel.table.item(2, 2).text() == "规则丙"

    def test_seq_matches_global_position(self, qapp, three_rules):
        """序号 = 规则在完整列表中的位置（与 MOCK#N 徽标对应）。"""
        panel = RulesPanel(three_rules)
        assert [panel.table.item(i, 1).text() for i in range(3)] == ["1", "2", "3"]

    def test_seq_keeps_global_number_under_filter(self, qapp, three_rules):
        """过滤后序号仍显示全局位置（甲1、乙2 停用 → 丙仍显示 3）。"""
        panel = RulesPanel(three_rules)
        three_rules.update(three_rules.all()[1].id, enabled=False)
        panel.only_enabled_cb.setChecked(True)
        assert panel.table.rowCount() == 2
        assert panel.table.item(0, 1).text() == "1"
        assert panel.table.item(1, 1).text() == "3"

    def test_hits_column_unchanged(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        assert panel.table.horizontalHeaderItem(7).text() == "命中"
        assert panel.table.item(0, 7).text() == "—"


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
        three_rules.flush_save()  # 落盘已异步：断言前先等后台写完成
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
        three_rules.flush_save()  # 落盘已异步：断言前先等后台写完成
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
        names = [panel.table.item(i, 2).text() for i in range(2)]
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
        # 回归守卫：视图级背景属性会压制模型 BackgroundRole（v1.15 高亮/
        # mock 行底色集体失效的根因），QSS 里不能再出现（带冒号=实际属性）
        assert "alternate-background-color:" not in qss
        assert "QTableView::item" not in qss
        assert "QHeaderView::section" in qss



# --------------------------------------------- 原生规则导出 / 导入（v1.15）

class TestNativeExportImport:
    @staticmethod
    def _stub_info(monkeypatch):
        """导出/导入成功路径会弹模态提示框，offscreen 测试必须吞掉。"""
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(
            QMessageBox, "information", staticmethod(lambda *a, **k: None)
        )

    def test_export_writes_native_json(self, qapp, three_rules, tmp_path, monkeypatch):
        from app.ui.rules_panel import RulesPanel

        self._stub_info(monkeypatch)
        out = tmp_path / "out.json"
        monkeypatch.setattr(
            "app.ui.rules_panel.QFileDialog.getSaveFileName",
            staticmethod(lambda *a, **k: (str(out), "")),
        )
        panel = RulesPanel(three_rules)
        panel._on_export()
        import json as _json

        data = _json.loads(out.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert [r["name"] for r in data["rules"]] == ["规则甲", "规则乙", "规则丙"]

    def test_import_appends_without_overwrite(self, qapp, three_rules, tmp_path, monkeypatch):
        import json as _json

        self._stub_info(monkeypatch)
        src = tmp_path / "in.json"
        src.write_text(
            _json.dumps(
                {"version": 1, "rules": [
                    {"id": "r_x", "name": "外来规则", "enabled": False,
                     "match": {"type": "contains", "value": "/imported/"},
                     "action": {"status": 200, "body": "hi"}},
                ]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "app.ui.rules_panel.QFileDialog.getOpenFileName",
            staticmethod(lambda *a, **k: (str(src), "")),
        )
        panel = RulesPanel(three_rules)
        panel._on_import_native()
        names = [r.name for r in three_rules.all()]
        assert names == ["规则甲", "规则乙", "规则丙", "外来规则"]  # 追加不覆盖
        imported = three_rules.all()[3]
        assert imported.enabled is False  # 启停状态保留
        assert imported.id != "r_x"       # merge 重生成 id，避免撞车

    def test_import_bad_file_shows_error(self, qapp, three_rules, tmp_path, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        bad = tmp_path / "bad.json"
        bad.write_text("not-json", encoding="utf-8")
        monkeypatch.setattr(
            "app.ui.rules_panel.QFileDialog.getOpenFileName",
            staticmethod(lambda *a, **k: (str(bad), "")),
        )
        calls = []
        monkeypatch.setattr(
            QMessageBox, "critical",
            staticmethod(lambda *a, **k: calls.append(a)),
        )
        panel = RulesPanel(three_rules)
        panel._on_import_native()
        assert len(calls) == 1
        assert len(three_rules.all()) == 3  # 坏文件不进数据


# ------------------------------------------------- 批量勾选操作（v1.15）

class TestBatchOperations:
    """首列复选框勾选后出现批量按钮，作用于勾选的规则。"""

    @staticmethod
    def _check(panel, rows):
        """模拟用户点击首列复选框（勾选指定行）。"""
        for row in rows:
            item = panel.table.item(row, 0)
            item.setCheckState(Qt.CheckState.Checked)

    @staticmethod
    def _stub_confirm(monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
        )
        monkeypatch.setattr(
            QMessageBox, "information", staticmethod(lambda *a, **k: None)
        )

    def test_batch_buttons_hidden_initially(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        assert panel.batch_enable_btn.isHidden()
        assert panel.batch_disable_btn.isHidden()
        assert panel.batch_delete_btn.isHidden()
        assert panel.batch_export_btn.isHidden()

    def test_batch_buttons_appear_on_check(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        self._check(panel, [0, 2])
        assert not panel.batch_enable_btn.isHidden()
        assert "2" in panel.batch_enable_btn.text()  # 按钮文字带数量

    def test_batch_buttons_hide_on_uncheck(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        self._check(panel, [0])
        self._check(panel, [])  # 无操作
        panel.table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        assert panel.batch_enable_btn.isHidden()
        assert panel._selected_rule_ids() == []

    def test_batch_disable_checked_only(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        self._check(panel, [0, 2])  # 甲、丙
        panel._on_batch_set_enabled(False)
        states = [r.enabled for r in three_rules.all()]
        assert states == [False, True, False]  # 乙不受影响

    def test_batch_enable(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        for r in three_rules.all():
            three_rules.update(r.id, enabled=False)
        self._check(panel, [1])
        panel._on_batch_set_enabled(True)
        assert [r.enabled for r in three_rules.all()] == [False, True, False]

    def test_batch_delete_checked(self, qapp, three_rules, monkeypatch):
        self._stub_confirm(monkeypatch)
        panel = RulesPanel(three_rules)
        self._check(panel, [0, 1])
        panel._on_delete()
        assert [r.name for r in three_rules.all()] == ["规则丙"]

    def test_selected_ids_are_checked_in_display_order(self, qapp, three_rules):
        panel = RulesPanel(three_rules)
        self._check(panel, [1])
        assert panel._selected_rule_ids() == [three_rules.all()[1].id]

    def test_checked_survives_refresh(self, qapp, three_rules):
        """刷新（如命中更新）后勾选状态保留。"""
        panel = RulesPanel(three_rules)
        self._check(panel, [1])
        panel.refresh()
        assert panel.table.item(1, 0).checkState() == Qt.CheckState.Checked
        assert panel._selected_rule_ids() == [three_rules.all()[1].id]

    def test_export_only_checked(self, qapp, three_rules, tmp_path, monkeypatch):
        import json as _json

        self._stub_confirm(monkeypatch)
        out = tmp_path / "sel.json"
        monkeypatch.setattr(
            "app.ui.rules_panel.QFileDialog.getSaveFileName",
            staticmethod(lambda *a, **k: (str(out), "")),
        )
        panel = RulesPanel(three_rules)
        self._check(panel, [0, 2])
        panel._on_export()
        data = _json.loads(out.read_text(encoding="utf-8"))
        assert [r["name"] for r in data["rules"]] == ["规则甲", "规则丙"]

    def test_export_all_when_none_checked(self, qapp, three_rules, tmp_path, monkeypatch):
        import json as _json

        self._stub_confirm(monkeypatch)
        out = tmp_path / "all.json"
        monkeypatch.setattr(
            "app.ui.rules_panel.QFileDialog.getSaveFileName",
            staticmethod(lambda *a, **k: (str(out), "")),
        )
        panel = RulesPanel(three_rules)
        panel._on_export()
        data = _json.loads(out.read_text(encoding="utf-8"))
        assert len(data["rules"]) == 3


class TestBatchToast:
    def test_toast_shown_after_batch_enable(self, qapp, three_rules):
        from PySide6.QtWidgets import QTableWidgetItem
        panel = RulesPanel(three_rules)
        # 勾选全部规则（首列复选框）
        for r in range(panel.table.rowCount()):
            item = panel.table.item(r, 0)
            if item is None:
                item = QTableWidgetItem()
                panel.table.setItem(r, 0, item)
            item.setCheckState(Qt.CheckState.Checked)
        panel._on_batch_set_enabled(True)
        # 成功提示浮层已创建，文本含数量与状态
        assert getattr(panel, "_toast_w", None) is not None
        assert "3" in panel._toast_w.text()
        assert "启用" in panel._toast_w.text()

    def test_toast_visible_inside_panel(self, qapp, three_rules):
        """toast 是面板子控件，必须落在面板可视范围内（此前误用 mapToGlobal
        的屏幕坐标喂给子控件 move()，窗口不在屏幕原点时整层被裁剪掉）。"""
        from PySide6.QtWidgets import QTableWidgetItem
        panel = RulesPanel(three_rules)
        panel.resize(900, 500)
        panel.show()
        for r in range(panel.table.rowCount()):
            item = panel.table.item(r, 0)
            if item is None:
                item = QTableWidgetItem()
                panel.table.setItem(r, 0, item)
            item.setCheckState(Qt.CheckState.Checked)
        panel._on_batch_set_enabled(False)
        w = panel._toast_w
        assert w is not None and w.isVisible()
        # 面板局部坐标必须完整落在面板 rect 内（被裁剪 = 用户看不见）
        assert panel.rect().contains(w.geometry())
        assert "停用" in w.text()
