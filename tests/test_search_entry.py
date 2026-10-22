"""搜索入口（菜单栏 + 工具栏按钮）的单元测试。

背景：搜索栏原本只有 Ctrl+F 能唤出来，没有快捷键的人发现不了这个功能。
这里锁住两个新入口以及按钮态与搜索栏可见性的同步关系。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMenu

from app.ui.main_window import MainWindow


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    win = MainWindow(restore_prompt=False)
    yield win
    win.close()


def test_menu_has_search_action(window):
    texts = []
    for menu in window.menuBar().findChildren(QMenu):
        for action in menu.actions():
            if action.text():
                texts.append(action.text())
    assert any("搜索会话" in t for t in texts)


def test_toolbar_button_toggles_search_bar(window):
    # 注意：offscreen 下父窗口没 show，isVisible() 恒 False —— 一律用 isHidden()
    assert window.search_bar.isHidden()
    assert not window.search_btn.isChecked()

    window.search_btn.setChecked(True)
    assert not window.search_bar.isHidden()

    window.search_btn.setChecked(False)
    assert window.search_bar.isHidden()
    assert not window.search_btn.isChecked()


def test_ctrl_f_syncs_button_state(window):
    """Ctrl+F 唤出搜索栏时，工具栏按钮也要跟着按下。"""
    window._on_find_shortcut()
    assert not window.search_bar.isHidden()
    assert window.search_btn.isChecked()


def test_search_action_shows_bar(window):
    """菜单栏入口与 Ctrl+F 走同一条路。"""
    window._on_find_shortcut()
    assert not window.search_bar.isHidden()
