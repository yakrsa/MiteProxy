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


def _raw_flow():
    """带 http_version 与 body 的流，用于验证 Raw 页展示完整报文。"""
    req = SimpleNamespace(
        method="POST",
        pretty_url="https://example.com/api",
        http_version="HTTP/1.1",
        headers={"Host": "example.com", "Content-Type": "application/json"},
        raw_content=b'{"a":1}',
    )
    req.get_content = lambda strict=False: b'{"a":1}'
    res = SimpleNamespace(
        status_code=201,
        reason="Created",
        http_version="HTTP/1.1",
        headers={"Content-Type": "application/json"},
        raw_content=b'{"id":7}',
    )
    res.get_content = lambda strict=False: b'{"id":7}'
    return SimpleNamespace(request=req, response=res, id="raw-flow")


def test_message_pane_has_inspect_and_raw_tabs(qapp):
    """请求/响应页内部应同时有「查看」与「原始」两个 tab（Fiddler 风格）。"""
    p = DetailPanel()
    labels = [
        p.request_pane.view_tabs.tabText(i)
        for i in range(p.request_pane.view_tabs.count())
    ]
    assert "查看" in labels
    assert "原始" in labels
    p.deleteLater()


def test_raw_pane_shows_full_request(qapp):
    """原始页必须把请求行 + 全部头 + body 拼成完整报文。"""
    p = DetailPanel()
    p.show_flow(_raw_flow())
    raw = p.request_pane.raw_pane.text.toPlainText()
    assert "POST https://example.com/api HTTP/1.1" in raw
    assert "Host: example.com" in raw
    assert "Content-Type: application/json" in raw
    assert '{"a":1}' in raw
    # 顺序：请求行 → 头 → 空行 → body
    assert raw.index("POST https://example.com/api HTTP/1.1") < raw.index("Host:")
    assert raw.index("Host:") < raw.index('{"a":1}')
    p.deleteLater()


def test_raw_pane_shows_full_response(qapp):
    p = DetailPanel()
    p.show_flow(_raw_flow())
    raw = p.response_pane.raw_pane.text.toPlainText()
    assert "HTTP/1.1 201 Created" in raw
    assert '{"id":7}' in raw
    p.deleteLater()


def test_raw_pane_searchable(qapp):
    """搜索应覆盖原始页（与「查看」页一致）。"""
    p = DetailPanel()
    p.show_flow(_raw_flow())
    # 「查看」页（body）与「原始」页都含 example.com，命中应 > 0
    hits = p.request_pane.highlight("example.com", case_sensitive=False)
    assert hits > 0
    p.deleteLater()


def test_splitter_synced_between_request_and_response(qapp):
    """bug：请求/响应两栏各记一份分隔条，拖动其一后切到另一栏会跳变。

    修复后任一栏拖动的分隔条比例应实时同步到另一栏，切页签不再跳动。
    """
    p = DetailPanel()
    p.resize(700, 500)
    p.show()
    p.show_flow(_http_flow(with_response=True))
    qapp.processEvents()

    # 拖动「请求」栏分隔条（程序化 setSizes 等价于用户拖拽，会触发 splitterMoved）
    p.request_pane._splitter.setSizes([520, 180])
    # 触发布局持久化（emit splitter_moved → DetailPanel 同步到「响应」栏）
    p.request_pane._save_detail_split()
    qapp.processEvents()

    req = p.request_pane._splitter.sizes()
    res = p.response_pane._splitter.sizes()
    # 关键不变量：两栏的"分割线位置"（header 宽）一致，切页签不再跳动。
    # body 宽因两栏实际像素宽细微差异会被 QSplitter 各自夹紧，不比较它。
    assert res[0] == req[0] == 520
    # 已落盘，重启语义下同一比例可被读到（用实际像素宽算 body，不写死）
    assert res[0] + res[1] == req[0] + req[1]
    p.deleteLater()


def test_body_min_width_allows_wide_header(qapp):
    """bug：BodyPane 工具条太宽把 body 最小宽度撑到 ~568px，QSplitter 据此
    把 header 锁死在「总宽 - 568」以内，header 拖不宽、看不全头字段。

    修复后工具条改为可滚动容器，body 最小宽度应大幅降低，header 能被拖到很宽。
    """
    from app.ui.detail_panel import BodyPane

    bp = BodyPane()
    bp.show_body({}, b"{}")
    # 修复前约 568；修复后工具条可滚动，应远小于此
    assert bp.minimumSizeHint().width() < 300

    p = DetailPanel()
    p.resize(700, 500)
    p.show_flow(_http_flow(with_response=True))
    qapp.processEvents()
    sp = p.request_pane._splitter
    # 把 header 拖到占面板 ~85%（body 压到 ~100px），应能生效而非被弹回
    sp.setSizes([600, 100])
    header_w = sp.sizes()[0]
    assert header_w >= 500, f"header 应能拖到很宽，实际仅 {header_w}"
    p.deleteLater()
