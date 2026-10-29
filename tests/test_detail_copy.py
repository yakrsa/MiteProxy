"""detail_panel 的两个交互细节的回归测试：

1. 双击 header 表的 Value 单元格 → 复制内容到剪贴板 + 弹出「已复制」浮层。
2. body 最大化态可被 exit_focus 重置（切换页签/会话自动还原的底层保证）。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QTableWidgetItem


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeClipboard:
    def __init__(self) -> None:
        self.text: str | None = None

    def setText(self, t: str) -> None:  # noqa: N802（模仿 Qt 命名）
        self.text = t


@pytest.fixture()
def fake_clipboard(monkeypatch):
    cb = _FakeClipboard()
    monkeypatch.setattr(
        "app.ui.detail_panel.QGuiApplication.clipboard", lambda: cb
    )
    return cb


def test_header_double_click_copies_value(qapp, fake_clipboard):
    from app.ui.detail_panel import MessagePane

    pane = MessagePane()
    pane.headers_table.setRowCount(1)
    pane.headers_table.setItem(0, 0, QTableWidgetItem("Content-Type"))
    pane.headers_table.setItem(0, 1, QTableWidgetItem("application/json"))

    pane._on_header_double_clicked(0, 1)

    assert fake_clipboard.text == "application/json"
    # 浮层已生成（2 秒后自动消失，这里只验证创建成功）
    assert getattr(pane, "_copy_toast_w", None) is not None


def test_header_double_click_ignores_empty(qapp, fake_clipboard):
    from app.ui.detail_panel import MessagePane

    pane = MessagePane()
    pane.headers_table.setRowCount(1)
    pane.headers_table.setItem(0, 0, QTableWidgetItem("X-Custom"))
    pane.headers_table.setItem(0, 1, QTableWidgetItem(""))

    pane._on_header_double_clicked(0, 1)

    assert fake_clipboard.text is None
    assert getattr(pane, "_copy_toast_w", None) is None


def test_body_focus_exit_resets_state(qapp):
    from app.ui.detail_panel import BodyPane

    bp = BodyPane()
    # 走真实路径：点按钮 → setChecked 触发 toggled → _on_max_toggle
    bp.max_btn.setChecked(True)
    assert bp._focus_mode is True
    assert bp.max_btn.text() == bp.tr("还原")

    bp.exit_focus()
    assert bp._focus_mode is False
    assert bp.max_btn.isChecked() is False

    # 幂等：再次退出不应报错
    bp.exit_focus()
    assert bp._focus_mode is False
