"""Mock 规则表头「选择」一键全选/取消全选（含点击「选择」文字切换）。"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

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
    for name in ("规则甲", "规则乙", "规则丙"):
        rule = Rule.create(name)
        rule.match = Match(type="contains", value=name)
        s.add(rule)
    return s


@pytest.fixture()
def panel(store, qapp):
    p = RulesPanel(store)
    p.show()
    return p


def _press_event():
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(1, 1),
        QPointF(1, 1),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


class TestToggleSelectAll:
    def test_toggle_from_empty_checks_all(self, panel):
        panel._toggle_select_all()
        assert len(panel._checked_ids) == 3
        assert panel.select_all_cb.checkState() == Qt.CheckState.Checked

    def test_toggle_twice_unchecks_all(self, panel):
        panel._toggle_select_all()
        panel._toggle_select_all()
        assert panel._checked_ids == set()
        assert panel.select_all_cb.checkState() == Qt.CheckState.Unchecked

    def test_partial_selection_toggles_to_full(self, panel):
        """只勾了一部分时，点一下应该是「补全选」而不是「清空」。"""
        panel.table.item(0, 8).setCheckState(Qt.CheckState.Checked)
        panel._toggle_select_all()
        assert len(panel._checked_ids) == 3

    def test_click_on_host_toggles(self, panel):
        """点「选择」文字/表头空白区（MouseButtonPress 落在 host 上）即切换。"""
        ret = panel.eventFilter(panel._select_all_host, _press_event())
        assert ret is True
        assert len(panel._checked_ids) == 3

    def test_click_on_host_twice_unchecks(self, panel):
        panel.eventFilter(panel._select_all_host, _press_event())
        panel.eventFilter(panel._select_all_host, _press_event())
        assert panel._checked_ids == set()

    def test_other_objects_not_intercepted(self, panel):
        ret = panel.eventFilter(panel.table, _press_event())
        assert ret is False

    def test_checkbox_still_works(self, panel):
        """勾选框本体仍走 stateChanged 路径，行为不变。"""
        panel.select_all_cb.setCheckState(Qt.CheckState.Checked)
        assert len(panel._checked_ids) == 3
        panel.select_all_cb.setCheckState(Qt.CheckState.Unchecked)
        assert panel._checked_ids == set()

    def test_no_tristate_on_user_click_path(self, panel):
        """去掉 tristate：一次点击就在勾/不勾之间切换，不会卡在中间态。"""
        assert not panel.select_all_cb.isTristate()
