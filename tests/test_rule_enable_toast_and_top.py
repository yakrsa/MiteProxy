"""单条启用/停用要给提示 + 右键「置顶」功能。"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from app.rules import Match, Rule, RuleStore  # noqa: E402
from app.ui.rules_panel import RulesPanel  # noqa: E402


@pytest.fixture()
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def store(tmp_path):
    s = RuleStore(path=tmp_path / "rules.json")
    for name in ("甲", "乙", "丙"):
        rule = Rule.create(name)
        rule.match = Match(type="contains", value=name)
        s.add(rule)
    return s


@pytest.fixture()
def panel(store, qapp):
    p = RulesPanel(store)
    p.show()
    return p


class TestToggleEnableToast:
    def test_individual_toggle_shows_toast(self, panel):
        rid = panel._display_ids[0]
        panel._toggle_enable(rid)
        assert isinstance(panel._toast_w, QLabel)
        assert panel._toast_w.isVisible()
        assert "已停用" in panel._toast_w.text()

    def test_toggle_twice_switches_prompt(self, panel):
        rid = panel._display_ids[1]
        panel._toggle_enable(rid)   # -> 已停用
        panel._toggle_enable(rid)   # -> 已启用
        assert "已启用" in panel._toast_w.text()

    def test_toggle_persists(self, panel):
        rid = panel._display_ids[2]
        panel._toggle_enable(rid)
        # 落盘是异步 saver 线程，这里校验内存中的 store 已更新（磁盘持久化
        # 由 test_rules_panel_order 的 test_reorder_persisted 等覆盖）
        assert panel.store.get(rid).enabled is False

    def test_repeated_toggle_shows_toast_each_time(self, panel, qapp):
        """回归：上一条提示超时销毁后，再次操作仍能正常弹出（曾因在已删除
        对象上 deleteLater 抛 RuntimeError 导致后续再也不弹）。"""
        rid = panel._display_ids[0]
        panel._toggle_enable(rid)              # 创建 w1
        w1 = panel._toast_w
        assert w1.isVisible()
        w1.deleteLater()                       # 模拟 2.5s 后超时销毁
        QApplication.processEvents()
        panel._toggle_enable(rid)              # 第二次操作
        w2 = panel._toast_w
        assert w2 is not None and w2.isVisible()
        assert w2 is not w1


class TestMoveToTop:
    def test_move_to_top_reorders_store(self, panel):
        rid = panel._display_ids[2]   # 第三条
        panel._move_to_top(rid)
        assert panel.store.all()[0].id == rid
        # 视图顺序里它也是第一个
        assert panel._display_ids[0] == rid

    def test_move_to_top_shows_toast_and_selects(self, panel):
        rid = panel._display_ids[1]
        panel._move_to_top(rid)
        assert isinstance(panel._toast_w, QLabel)
        assert "已置顶" in panel._toast_w.text()
        assert panel.table.currentRow() == 0

    def test_move_to_top_persists(self, panel):
        rid = panel._display_ids[2]
        panel._move_to_top(rid)
        # 内存中的全量列表顺序已置顶（磁盘持久化由其他用例覆盖）
        assert panel.store.all()[0].id == rid
