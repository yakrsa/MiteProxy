"""流量列表键盘快捷键：R 重放 / E 编辑后重放（无修饰键），带修饰键不触发。

对应需求：请求列表支持快捷键，选中某条请求按 R 重放、按 E 编辑后重放；
Ctrl+X 清表在 main_window 通过 QShortcut 绑定（见 test_clear_shortcut）。
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.traffic_table import TrafficTable  # noqa: E402


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _key(key, modifiers=Qt.KeyboardModifier.NoModifier):
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers)


class TestTrafficShortcuts:
    def test_r_emits_replay(self, qapp):
        table = TrafficTable()
        hits = []
        table.replay_requested.connect(lambda: hits.append("r"))
        table.keyPressEvent(_key(Qt.Key.Key_R))
        assert hits == ["r"]

    def test_e_emits_edit_replay(self, qapp):
        table = TrafficTable()
        hits = []
        table.edit_replay_requested.connect(lambda: hits.append("e"))
        table.keyPressEvent(_key(Qt.Key.Key_E))
        assert hits == ["e"]

    def test_modified_r_does_not_emit(self, qapp):
        """带修饰键（如已有的 Ctrl+R 重放）不应在这里触发，避免双触发；
        Ctrl+R 由主窗口 QShortcut 处理。"""
        table = TrafficTable()
        hits = []
        table.replay_requested.connect(lambda: hits.append("r"))
        table.edit_replay_requested.connect(lambda: hits.append("e"))
        table.keyPressEvent(_key(Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier))
        table.keyPressEvent(_key(Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier))
        assert hits == []

    def test_other_keys_passthrough(self, qapp):
        """无关键（如方向键）不触发重放，交回父类处理。"""
        table = TrafficTable()
        hits = []
        table.replay_requested.connect(lambda: hits.append("r"))
        table.edit_replay_requested.connect(lambda: hits.append("e"))
        table.keyPressEvent(_key(Qt.Key.Key_Down))
        table.keyPressEvent(_key(Qt.Key.Key_Delete))
        assert hits == []
