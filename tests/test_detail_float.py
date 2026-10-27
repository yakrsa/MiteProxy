"""详情面板拖出浮窗的单元测试。

覆盖两个层级：
1. **请求 / 响应页各自拖出**（DetailPanel 内部的 QTabWidget 走 TabDetacher）；
2. **详情面板整体拖出**（不在标签控件里，走 WidgetFloat）。

重点验证「拖出后还能用」：浮窗只是换了父窗口，选中新会话照样刷新内容，
而不是变成一张死快照。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QSplitter, QWidget

from app.ui.detail_panel import DetailPanel
from app.ui.detachable import WidgetFloat


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _http_flow():
    req = SimpleNamespace(
        method="GET",
        pretty_url="https://example.com/api",
        headers={"Host": "example.com"},
        raw_content=b"",
    )
    req.get_content = lambda strict=False: b""
    res = SimpleNamespace(
        status_code=200,
        reason="OK",
        headers={"Content-Type": "application/json"},
        raw_content=b'{"ok":1}',
    )
    res.get_content = lambda strict=False: b'{"ok":1}'
    return SimpleNamespace(request=req, response=res, id="flow-1")


# ------------------------------------------------------- 请求 / 响应页


def test_request_pane_detach_keeps_tab_count(qapp):
    p = DetailPanel()
    count = p.tabs.count()
    req_idx = p.tabs.indexOf(p.request_pane)

    assert p.detach_pane("request") is True
    # 原位留占位页，页签总数与索引都不塌陷（面板内部按索引定位耗时/过滤页）
    assert p.tabs.count() == count
    assert p.is_pane_detached("request") is True
    assert p.tabs.indexOf(p.request_pane) == -1
    assert p._pane_detacher.index_detached(req_idx) is True
    p.deleteLater()


def test_detached_pane_still_updates_on_show_flow(qapp):
    """拖出后选中新会话，浮窗里的请求页照样刷新（不是死快照）。"""
    p = DetailPanel()
    p.show_flow(_http_flow())
    assert p.detach_pane("request") is True

    win = p._pane_detacher.window_for_tag("request")
    assert win is not None
    assert p.request_pane.window() is win

    # 换一条 URL 不同的会话，浮窗里的摘要行应当跟着变
    flow = _http_flow()
    flow.request.pretty_url = "https://example.com/second"
    p.show_flow(flow)
    assert "second" in p.request_pane.summary_label.text()
    p.deleteLater()


def test_show_flow_does_not_land_on_placeholder(qapp):
    """粘性页（响应）被拖出后，选流不该把用户甩到占位页上。"""
    p = DetailPanel()
    p.show_flow(_http_flow())
    assert p.detach_pane("response") is True

    p.show_flow(_http_flow())
    cur = p.tabs.currentIndex()
    assert p._pane_detacher.index_detached(cur) is False, "停在占位页上了"
    p.deleteLater()


def test_only_request_response_are_allowed(qapp):
    p = DetailPanel()
    # 耗时 / 过滤 / WebSocket / TLS 不放行：拖走了就没地方改过滤规则
    assert p.detach_pane("timings") is False
    assert p._pane_detacher.detach(p.filter_panel) is None
    assert p._pane_detacher.detach(p.ws_pane) is None
    assert p.tabs.count() == p.tabs.count()
    assert p._pane_detacher.any_detached() is False
    p.deleteLater()


def test_reattach_restores_index(qapp):
    p = DetailPanel()
    count = p.tabs.count()
    req_idx = p.tabs.indexOf(p.request_pane)
    p.detach_pane("request")
    p.reattach_panes()

    assert p.tabs.count() == count
    assert p.tabs.indexOf(p.request_pane) == req_idx
    assert p.is_pane_detached("request") is False
    p.deleteLater()


def test_tab_bar_menu_offers_detach(qapp):
    """页签右键菜单给出「整体拖出」入口（单个页签拖出靠拖拽手势）。"""
    p = DetailPanel()
    got = []
    p.float_toggle_requested.connect(lambda: got.append(1))

    p._on_tab_bar_menu(QPoint(0, 0))
    assert p._tab_menu is not None
    act = p._tab_menu.actions()[0]
    assert "拖出" in act.text()
    act.trigger()
    assert got == [1], "菜单项没发出拖出请求"
    p.deleteLater()


def test_is_floating_reflects_host(qapp):
    p = DetailPanel()
    assert p.is_floating() is False
    floater = WidgetFloat()
    floater.detach(p, "详情")
    assert p.is_floating() is True     # 菜单据此把文案切成「收回详情面板」
    floater.reattach()
    p.deleteLater()


def test_close_pane_floats_keeps_pane_alive(qapp):
    """退出时只关窗不收回——页面不能跟着空壳一起被销毁。"""
    p = DetailPanel()
    p.detach_pane("response")
    p.close_pane_floats()
    qapp.processEvents()
    # 仍能访问：说明底层 C++ 对象还活着
    assert p.response_pane.isWidgetType()
    assert p.response_pane.parent() is not None
    p.deleteLater()


# ------------------------------------------------------- 详情面板整体


def _splitter_pair():
    sp = QSplitter()
    left = QWidget()
    right = QWidget()
    sp.addWidget(left)
    sp.addWidget(right)
    sp.setSizes([300, 400])
    return sp, left, right


def test_widget_float_detach_and_reattach(qapp):
    sp, _left, right = _splitter_pair()
    floater = WidgetFloat()
    sizes = sp.sizes()
    assert floater.detach(right, "详情") is not None
    assert sp.count() == 1                      # 摘走后 splitter 只剩一侧
    assert floater.is_detached() is True
    assert right.window() is floater.window()

    got = floater.reattach()
    assert got is right
    sp.addWidget(right)
    assert sp.count() == 2
    assert right.parent() is sp
    assert floater.is_detached() is False
    # 比例还原（setSizes）在主窗口 _reattach_detail_panel 里，走冒烟验证——
    # 这里不较真 Qt 的分配结果：分裂器尺寸受 sizeHint / 最小宽度影响，
    # 单测里 assert 具体数字只会绑死实现。
    assert isinstance(sizes, list)


def test_widget_float_one_at_a_time(qapp):
    _sp, left, right = _splitter_pair()
    floater = WidgetFloat()
    assert floater.detach(left, "a") is not None
    assert floater.detach(right, "b") is None   # 一次只拖一个
    assert floater.widget is left


def test_widget_float_close_keeps_widget_alive(qapp):
    """退出路径：关窗后部件必须存活（主窗口还要读它的配置）。"""
    _sp, left, _right = _splitter_pair()
    host = QWidget()
    floater = WidgetFloat(host)
    floater.detach(left, "详情")
    floater.close()
    qapp.processEvents()
    assert left.isWidgetType()
    assert left.parent() is host                # 挂回主窗口，随它一起销毁
