"""DetailPanel（请求/响应 tab 切换）的单元测试。

验证：普通 HTTP 会话 show_flow 后默认聚焦「响应」页——抓包场景优先看响应，
本工具是 tab 切换布局（Fiddler 是上下布局无此问题），故显式默认到响应。
粘性选择：用户手动切换页签后，当次运行内记住该选择（后续选流不再强制拉回响应）；
新实例（重启）回到默认响应页。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from app.session import BODY_TRUNCATED_KEY, BODY_TRUNCATED_SIZE_KEY
from app.ui.detail_panel import DetailPanel


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _http_flow(with_response: bool = True):
    req = SimpleNamespace(
        method="GET",
        pretty_url="https://example.com/api",
        headers={"Host": "example.com"},
        raw_content=b"",
    )
    req.get_content = lambda strict=False: b""

    if with_response:
        res = SimpleNamespace(
            status_code=200,
            reason="OK",
            headers={"Content-Type": "application/json"},
            raw_content=b'{"ok":1}',
        )
        res.get_content = lambda strict=False: b'{"ok":1}'
    else:
        res = None

    return SimpleNamespace(request=req, response=res, id="flow-1")


def test_default_tab_is_response(qapp):
    p = DetailPanel()
    p.show_flow(_http_flow(with_response=True))
    # 普通 HTTP 会话默认停在「响应」页，而非首个「请求」页
    assert p.tabs.currentIndex() == p.response_index
    p.deleteLater()


def test_default_tab_is_response_even_pending(qapp):
    p = DetailPanel()
    p.show_flow(_http_flow(with_response=False))
    # 响应还没回来也默认响应页（展示「尚未收到响应…」占位）
    assert p.tabs.currentIndex() == p.response_index
    p.deleteLater()


def test_sticky_tab_keeps_user_choice(qapp):
    p = DetailPanel()
    p.show_flow(_http_flow(with_response=True))
    # 启动默认响应页
    assert p.tabs.currentIndex() == p.response_index

    # 用户手动切到「请求」页
    p.tabs.setCurrentIndex(0)
    assert p.tabs.currentIndex() == 0

    # 再选另一条流，应记住「请求」而非跳回响应
    p.show_flow(_http_flow(with_response=True))
    assert p.tabs.currentIndex() == 0
    p.deleteLater()


def test_sticky_tab_resets_on_new_instance(qapp):
    # 每个 DetailPanel 实例独立；新实例重启语义即默认响应页
    p1 = DetailPanel()
    p1.show_flow(_http_flow(with_response=True))
    p1.tabs.setCurrentIndex(0)
    p1.show_flow(_http_flow(with_response=True))
    assert p1.tabs.currentIndex() == 0  # 已粘性切到请求

    p2 = DetailPanel()  # 模拟重启
    p2.show_flow(_http_flow(with_response=True))
    assert p2.tabs.currentIndex() == p2.response_index  # 新实例回到默认响应
    p1.deleteLater()
    p2.deleteLater()


def test_truncated_snapshot_body_is_labelled(qapp):
    """恢复自带截断标记的会话时，响应 body 的提示栏必须说明「已截断」。

    否则用户看到大 JSON 解析失败，只会以为是格式化能力不行。
    """
    flow = _http_flow(with_response=True)
    flow.metadata = {
        BODY_TRUNCATED_KEY: "response",
        BODY_TRUNCATED_SIZE_KEY: {"response": 262144},
    }
    p = DetailPanel()
    p.show_flow(flow)
    note = p.response_pane.body_pane.view_note.text()
    assert "已截断" in note
    # 带上截断前的原始大小，用户才知道差多少
    assert "原 256KB" in note
    # 请求侧没被截断，不该跟着标
    assert "已截断" not in p.request_pane.body_pane.view_note.text()
    p.deleteLater()


def test_truncation_note_without_size(qapp):
    """老记录只有 truncated 标记、没有原始大小时，也得说清楚被截了。"""
    flow = _http_flow(with_response=True)
    flow.metadata = {BODY_TRUNCATED_KEY: "response"}
    p = DetailPanel()
    p.show_flow(flow)
    assert "已截断" in p.response_pane.body_pane.view_note.text()
    p.deleteLater()


def test_normal_flow_has_no_truncation_note(qapp):
    flow = _http_flow(with_response=True)
    flow.metadata = {}
    p = DetailPanel()
    p.show_flow(flow)
    assert "已截断" not in p.response_pane.body_pane.view_note.text()
    p.deleteLater()
