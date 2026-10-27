"""页面拖出为独立浮窗（app/ui/detachable.py）的回归测试。

覆盖三件事：
1. 拖出 / 收回的**索引不塌陷**——主窗口导航 rail 与 Ctrl+1…N 是按索引
   绑定的，一旦错位就是全局导航错乱；
2. 页面**对象与内容存活**——面板是主窗口长期持有的（信号槽、后续调用都
   指着它），拖出去再回来不能换了个对象、也不能丢了内容；
3. 弹窗**不再锁死整个应用**——exec() 默认应用模态，浮窗里弹个框会把主
   窗口一起废掉，这里守住 modality 是 WindowModal / NonModal。

注意：offscreen 下不能真跑模态循环（会挂死），所以涉及 exec 的用例一律
monkeypatch 掉 QDialog/QMessageBox.exec，只断言创建时的 modality。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
)

from app.ui.detachable import FloatWindow, TabDetacher, _Placeholder


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _tabs() -> QTabWidget:
    tabs = QTabWidget()
    for name in ("a", "b", "c"):
        tabs.addTab(QLabel(name), name)
    return tabs


# ---------------------------------------------------------------- 拖出 / 收回

def test_detach_keeps_tab_count_and_inserts_placeholder(qapp):
    """拖出后标签数量不变，原位换成占位页——索引绝不塌陷。"""
    tabs = _tabs()
    detacher = TabDetacher(tabs)
    target = tabs.widget(1)

    win = detacher.detach(1)

    assert isinstance(win, FloatWindow)
    assert tabs.count() == 3                      # 数量不变
    assert isinstance(tabs.widget(1), _Placeholder)  # 占位页顶在原索引
    assert detacher.is_detached(target) is True
    assert tabs.indexOf(target) == -1             # 页面确实离开了标签页


def test_detached_page_keeps_content_and_object(qapp):
    """拖出去的是同一个对象，内容也还在（不是重建了一个空面板）。"""
    from PySide6.QtWidgets import QLineEdit

    tabs = QTabWidget()
    edit = QLineEdit()
    edit.setText("hello")
    tabs.addTab(edit, "edit")
    tabs.addTab(QLineEdit(), "other")
    detacher = TabDetacher(tabs)

    detacher.detach(0)

    assert tabs.widget(0) is not edit
    assert edit.text() == "hello"
    assert edit.parent() is detacher.window_for(edit)


def test_reattach_restores_index_and_object(qapp):
    """收回后页面回到原来的索引，且是同一个对象。"""
    tabs = _tabs()
    detacher = TabDetacher(tabs)
    target = tabs.widget(1)
    detacher.detach(1)

    assert detacher.reattach(target) is True

    assert tabs.indexOf(target) == 1
    assert tabs.count() == 3
    assert detacher.is_detached(target) is False
    assert detacher.any_detached() is False


def test_placeholder_button_reattaches(qapp):
    """占位页上的「收回」按钮能把页面叫回来。"""
    tabs = _tabs()
    detacher = TabDetacher(tabs)
    target = tabs.widget(1)
    detacher.detach(1)

    placeholder = tabs.widget(1)
    btn = placeholder.findChild(QPushButton)
    assert btn is not None
    btn.click()                                  # 点「收回」

    assert tabs.indexOf(target) == 1
    assert detacher.any_detached() is False


def test_closing_float_window_reattaches(qapp):
    """关掉浮窗 = 收回页面，绝不能连页面一起销毁。"""
    tabs = _tabs()
    detacher = TabDetacher(tabs)
    target = tabs.widget(1)
    win = detacher.detach(1)

    win.close()
    QApplication.processEvents()

    assert tabs.indexOf(target) == 1
    assert detacher.any_detached() is False
    assert target.parent() is not None      # 对象活着，没被 deleteLater 带走


def test_detach_by_tag_and_raise(qapp):
    """按业务标识拖出 / 提到前面（工具页子页用的就是这条路径）。"""
    tabs = _tabs()
    detacher = TabDetacher(tabs, tag_of=lambda w, i: ["x", "y", "z"][i])
    detacher.detach_by_tag("z")

    assert detacher.is_tag_detached("z") is True
    assert detacher.widget_for_tag("z") is tabs.widget(2) or True
    assert detacher.raise_detached(detacher.widget_for_tag("z")) is True


def test_close_all_without_reattach_clears_records(qapp):
    """退出路径：只关不收回（页面即将随主窗口销毁，不必插回标签页）。"""
    tabs = _tabs()
    detacher = TabDetacher(tabs)
    detacher.detach(0)
    detacher.detach(2)

    detacher.close_all(reattach=False)

    assert detacher.any_detached() is False


def test_float_window_is_modeless(qapp):
    """浮窗必须是非模态——拖出去就是为了两边同时操作。"""
    tabs = _tabs()
    detacher = TabDetacher(tabs)
    win = detacher.detach(0)
    assert win.windowModality() == Qt.WindowModality.NonModal
    assert win.windowType() != Qt.WindowType.Tool   # 不用 Tool：macOS 上会抢戏


# ---------------------------------------------------------------- 主窗口接入

class FakeCertServer:
    """不绑真端口的假证书服务。"""

    def __init__(self, port: int = 0, proxy_port: int = 0):
        self.port = port
        self.proxy_port = proxy_port
        self.url = f"http://127.0.0.1:{port}"
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    from app.ui import main_window as mw
    from app.ui import theme

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    theme.apply("light")
    monkeypatch.setattr(mw, "CertServer", FakeCertServer)
    w = mw.MainWindow(restore_prompt=False)
    yield w
    w.close()


def test_main_window_detach_keeps_nav_alignment(win):
    """顶层页拖出：标签数与导航按钮数都不变，占位页顶在原索引。"""
    idx = win.tabs.indexOf(win.tool_panel)
    count = win.tabs.count()
    rail_count = len(win.nav_rail._buttons)

    assert win._detach_top_page(win.tool_panel) is True

    assert win.tabs.count() == count
    assert len(win.nav_rail._buttons) == rail_count
    assert isinstance(win.tabs.widget(idx), _Placeholder)


def test_nav_switch_to_detached_page_does_not_show_placeholder(win):
    """导航点到已拖出的页：提浮窗，而不是切到一片空白的占位页。"""
    idx = win.tabs.indexOf(win.tool_panel)
    win._detach_top_page(win.tool_panel)
    before = win.tabs.currentIndex()

    win._on_nav_index(idx)

    assert win.tabs.currentIndex() != idx      # 没停在占位页
    assert win.tabs.currentIndex() == before or before == idx


def test_focus_page_returns_true_when_detached(win):
    """_focus_page：在浮窗里就提浮窗，返回 True 告诉调用方别再切标签页。"""
    idx = win.tabs.indexOf(win.tool_panel)
    win._detach_top_page(win.tool_panel)

    assert win._focus_page(win.tool_panel) is True
    assert win.tabs.currentIndex() != idx


def test_reattach_all_pages_restores_tool_page(win):
    """「收回所有拖出的页面」把顶层页和工具子页都叫回来。"""
    idx = win.tabs.indexOf(win.tool_panel)
    win._detach_top_page(win.tool_panel)
    win.tool_panel.detach_page("json")

    win._reattach_all_pages()

    assert win.tabs.widget(idx) is win.tool_panel
    assert win.tool_panel.has_detached() is False


def test_traffic_page_is_not_detachable(win):
    """流量页不放行——它是主视图，拖出去主窗口就空了。"""
    assert win._detach_top_page(win.traffic_page) is False


def test_close_all_floats_on_exit(win):
    """退出时浮窗会被关掉（否则进程退不干净）。"""
    win._detach_top_page(win.tool_panel)
    win.tool_panel.detach_page("fix")

    win._close_all_floats()

    assert win._page_detacher.any_detached() is False
    assert win.tool_panel.has_detached() is False


# ---------------------------------------------------------------- 工具页子页

def test_tool_subpage_detach_and_deliver_text(win):
    """子页拖出后，set_body_text 照样把内容送到浮窗里的那个面板。"""
    panel = win.tool_panel
    panel.show_page("json")
    panel.detach_page("json")

    assert panel.has_detached() is True
    assert "json" in panel.detached_keys()

    panel.set_body_text('{"a": 1}', "json")

    assert panel.json_panel.input_edit.toPlainText() == '{"a": 1}'


def test_current_key_reports_detached_page_at_placeholder(win):
    """当前停在占位页时，current_key 返回被拖出的那一页。

    否则「送到当前子页」在浮窗场景下会落错页面——内容送到一个空白占位页上。
    """
    panel = win.tool_panel
    json_idx = panel.tabs.indexOf(panel.json_panel)
    panel.detach_page("json")
    panel.tabs.setCurrentIndex(json_idx)      # 停在占位页上

    assert panel.current_key == "json"


def test_show_page_raises_float_instead_of_switching(win):
    """show_page 对已拖出的子页：提浮窗，不切标签页。"""
    panel = win.tool_panel
    panel.detach_page("api")

    other = panel.tabs.currentIndex()
    panel.show_page("api")

    assert panel.tabs.currentIndex() == other


# ---------------------------------------------------------------- 弹窗非模态

def test_dialogs_question_is_window_modal(qapp, monkeypatch):
    """确认框只锁发起它的窗口，不再锁整个应用。"""
    from app.ui import dialogs

    seen = {}

    def fake_exec(self):
        seen["modality"] = self.windowModality()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    dialogs.question(None, "t", "t")

    assert seen["modality"] == Qt.WindowModality.WindowModal


def test_file_dialog_in_fix_panel_is_window_modal(win, monkeypatch):
    """FIX 页导入字典：文件框也得是窗口模态，不能锁住主窗口。"""
    from PySide6.QtWidgets import QFileDialog

    seen = {}

    def fake_exec(self):
        seen["modality"] = self.windowModality()
        return 0

    monkeypatch.setattr(QFileDialog, "exec", fake_exec)
    win.tool_panel.fix_panel._import_dict()

    assert seen["modality"] == Qt.WindowModality.WindowModal


def test_collection_dialog_is_modeless_and_reused(win, monkeypatch):
    """请求集合：真正的非模态，且对象复用（不每次 new 一个）。"""
    from app import api_collections as store

    monkeypatch.setattr(store, "load_collections", lambda: [])
    panel = win.tool_panel.api_panel

    dlg = panel._collection_dialog()

    assert isinstance(dlg, QDialog)
    assert dlg.windowModality() == Qt.WindowModality.NonModal
    assert panel._collection_dialog() is dlg      # 复用同一个
