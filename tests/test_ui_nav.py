"""T1 现代化：图标工厂 / 侧栏 rail / 状态码 minimap / 空态引导。"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTabWidget

from app.ui import icons, theme
from app.ui.main_window import MainWindow
from app.ui.traffic_table import TrafficTable


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    theme.apply("light")
    w = MainWindow(restore_prompt=False)
    yield w
    w.close()


# ---------------------------------------------------------------- 图标工厂

ICON_NAMES = (
    "traffic", "mock", "network", "tools", "scripts", "log", "stats",
    "power", "breakpoint", "search", "trash", "mcp",
)


@pytest.mark.parametrize("name", ICON_NAMES)
def test_icon_renders_real_pixels(qapp, name):
    """图标必须真的画出来——之前 SVG 属性重复导致 load 失败、渲染全透明。"""
    pm = icons._render(name, "#374151", 24)
    img = pm.toImage()
    opaque = sum(
        1 for y in range(img.height()) for x in range(img.width())
        if img.pixelColor(x, y).alpha() > 10
    )
    assert opaque > 20, f"icon {name} rendered blank"


def test_icon_unknown_name_returns_empty(qapp):
    assert icons.icon("no-such-icon").isNull()


def test_icon_cache_short_circuit(qapp):
    """同色重复取图标应命中缓存（_render 的 lru_cache 不增长）。"""
    icons.icon("traffic")
    info1 = icons._render.cache_info()
    icons.icon("traffic")
    info2 = icons._render.cache_info()
    assert info2.hits >= info1.hits + 1


# ---------------------------------------------------------------- 主窗口接线

@pytest.fixture
def _win(qapp):
    theme.apply("light")
    w = MainWindow(restore_prompt=False)
    yield w
    w.close()


def test_tabs_are_west_rail_with_icons(win):
    assert win.tabs.tabPosition() == QTabWidget.TabPosition.West
    assert win.tabs.count() == 7
    assert len(win._tab_icon_names) == 7
    for i in range(win.tabs.count()):
        assert not win.tabs.tabIcon(i).isNull(), f"tab {i} missing icon"


def test_toolbar_highfreq_buttons_have_icons(win):
    for btn in (win.clear_btn, win.search_btn, win.proxy_btn,
                win.breakpoint_btn, win.mcp_btn):
        assert not btn.icon().isNull()


def test_refresh_icons_short_circuits_on_same_color(win):
    """_refresh_icons 挂在 _update_status 上，同色必须零开销短路。"""
    win._refresh_icons()
    info1 = icons._render.cache_info()
    win._refresh_icons()
    win._refresh_icons()
    assert icons._render.cache_info().misses == info1.misses


def test_refresh_icons_recolors_on_theme_change(win):
    win._refresh_icons()
    theme.apply("dark")
    win._refresh_icons()
    assert win._icons_color == theme.css("fg")
    theme.apply("light")
    win._refresh_icons()


# ---------------------------------------------------------------- minimap

def test_minimap_exists_next_to_table(win):
    # 窗口未 show，用 isHidden() 判断（isVisible 对未显示窗口恒 False）
    assert not win.minimap.isHidden()
    # 和表格同一个左栏容器（不是 splitter 直属子项，splitter 仍只有两项）
    assert win.traffic_splitter.count() == 2
    assert win.minimap.parent() is not None


def test_minimap_paints_with_rows(win, qtbot=None):
    row = dict(
        id=1, method="GET", host="a.com", path="/x", url="http://a.com/x",
        status=500, req_size=0, size=10, duration_ms=1.0, server_ip="1.2.3.4",
        marked="", content_type="", timestamp=0.0, comment="",
        is_websocket=False, ws_messages=0, is_replay=False, throttle_ms=0,
    )
    win.flow_store.beginResetModel()
    win.flow_store.rows = [row]
    win.flow_store.endResetModel()
    win.minimap.resize(10, 200)
    pm = win.minimap.grab()
    img = pm.toImage()
    colored = sum(
        1 for y in range(img.height()) for x in range(img.width())
        if img.pixelColor(x, y).alpha() > 10
    )
    assert colored > 0, "minimap painted nothing with rows"


def test_minimap_hidden_in_vertical_layout(win):
    win.layout_combo.setCurrentIndex(1)   # 上下布局
    assert win.minimap.isHidden()
    win.layout_combo.setCurrentIndex(0)   # 左右布局
    assert not win.minimap.isHidden()


# ---------------------------------------------------------------- 空态

def test_empty_overlay_shown_when_no_flows(win):
    table = win.traffic_table
    assert table.model().rowCount() == 0
    assert not table.empty_overlay.isHidden()


def test_empty_overlay_hidden_after_rows(win):
    table: TrafficTable = win.traffic_table
    rows = [
        dict(id=i, method="GET", host="a.com", path="/x", url="http://a.com/x",
             status=200, req_size=0, size=1, duration_ms=1.0,
             server_ip="1.2.3.4", marked="", content_type="", timestamp=0.0,
             comment="", is_websocket=False, ws_messages=0, is_replay=False,
             throttle_ms=0)
        for i in range(3)
    ]
    win.flow_store.beginResetModel()
    win.flow_store.rows = rows
    win.flow_store.endResetModel()
    assert table.model().rowCount() == 3
    assert not table.empty_overlay.isVisible()


def test_empty_overlay_mouse_transparent(win):
    assert win.traffic_table.empty_overlay.testAttribute(
        Qt.WidgetAttribute.WA_TransparentForMouseEvents
    )
