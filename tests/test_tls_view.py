"""T2：TLS 信息视图（详情面板 TLS 页签）。

覆盖：
- extract_tls / has_tls 纯数据层：明文、全 TLS、单段 TLS、属性缺失容错；
- TlsPane：树渲染（连接属性 + 证书链）、明文占位、clear；
- DetailPanel：TLS 页签显隐、粘性页签回落（明文流量不污染 sticky）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from app.ui.detail_panel import DetailPanel
from app.ui.tls_pane import TlsPane, extract_tls, has_tls


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeCert:
    """够用的证书替身：extract 只碰 subject/issuer/有效期/serial/fingerprint。"""

    subject = SimpleNamespace(rfc4514_string=lambda: "CN=example.com")
    issuer = SimpleNamespace(rfc4514_string=lambda: "CN=Test CA")
    not_valid_before_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)
    not_valid_after_utc = datetime(2027, 1, 1, tzinfo=timezone.utc)
    serial_number = 0xABCDEF

    def fingerprint(self, algo):
        return b"\xde\xad" * 16


def _conn(tls, certs=None, **kw):
    base = dict(
        tls=tls, tls_version="TLSv1.3", cipher_name="TLS_AES_128_GCM_SHA256",
        sni="example.com", alpn_proto_negotiated=b"h2",
        certificate_list=certs or [], clientcert=None,
        timestamp_tls_setup=100.5, timestamp_start=100.0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _flow(client_tls, server_tls, **kw):
    return SimpleNamespace(
        client_conn=_conn(client_tls, **{}),
        server_conn=_conn(server_tls, certs=[_FakeCert()], **{}),
        **kw,
    )


# ---------------------------------------------------------------- 纯数据层


def test_extract_tls_plain_http_returns_none():
    flow = _flow(False, False)
    assert extract_tls(flow) is None
    assert has_tls(flow) is False


def test_extract_tls_full_https():
    info = extract_tls(_flow(True, True))
    assert info is not None
    client_labels = dict(info["client"]["rows"])
    assert client_labels["version"] == "TLSv1.3"
    assert client_labels["cipher"] == "TLS_AES_128_GCM_SHA256"
    assert client_labels["sni"] == "example.com"
    assert client_labels["alpn"] == "h2"
    assert "handshake" in client_labels
    # 服务端带了证书链
    assert len(info["server"]["certs"]) == 1


def test_extract_tls_single_side():
    # 只有客户端段是 TLS（MITM 场景：浏览器 HTTPS，上游明文）
    info = extract_tls(_flow(True, False))
    assert info["client"] is not None
    assert info["server"] is None
    assert has_tls(_flow(True, False)) is True
    # 只有服务端段是 TLS（显式 http:// 但上游重导向 https 的边角场景）
    info = extract_tls(_flow(False, True))
    assert info["client"] is None
    assert info["server"] is not None


def test_extract_tls_missing_attrs_tolerated():
    # 连接对象属性缺失（半成品 flow / 测试替身）不能抛
    flow = SimpleNamespace(
        client_conn=SimpleNamespace(tls=True),
        server_conn=SimpleNamespace(tls=False),
    )
    info = extract_tls(flow)
    assert info["client"]["rows"] == []
    assert info["client"]["certs"] == []


def test_extract_tls_bad_cert_attrs_skipped():
    class _BrokenCert:
        @property
        def subject(self):
            raise ValueError("boom")

        issuer = SimpleNamespace(rfc4514_string=lambda: "CN=CA")
        not_valid_before_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)
        not_valid_after_utc = datetime(2027, 1, 1, tzinfo=timezone.utc)
        serial_number = 7

        def fingerprint(self, algo):
            raise ValueError("nope")

    flow = SimpleNamespace(
        client_conn=_conn(True, certs=[_BrokenCert()]),
        server_conn=_conn(False),
    )
    info = extract_tls(flow)
    assert info["client"]["rows"] == [] or all(
        k in ("version", "cipher", "sni", "alpn", "handshake")
        for k, _ in info["client"]["rows"]
    )
    from app.ui.tls_pane import _fmt_cert
    fmt = dict(_fmt_cert(_BrokenCert()))
    # subject 炸了被跳过，issuer/有效期/serial 还在
    assert "subject" not in fmt
    assert fmt["issuer"] == "CN=CA"
    assert fmt["serial"] == "7"
    assert "sha256" not in fmt


def test_extract_tls_no_conns_at_all():
    # 完全没有连接属性的 flow（mock 会话）不能抛
    assert extract_tls(SimpleNamespace()) is None
    assert has_tls(SimpleNamespace()) is False


# ---------------------------------------------------------------- TlsPane


def test_tls_pane_renders_tree(qapp):
    pane = TlsPane()
    pane.show_flow(_flow(True, True))
    assert not pane.tree.isHidden()
    assert pane.placeholder.isHidden()
    # 客户端 + 服务端两个顶层
    assert pane.tree.topLevelItemCount() == 2
    client_top = pane.tree.topLevelItem(0)
    assert "客户端连接" in client_top.text(0)
    # 服务端顶层下有「证书链」子节点，证书再有明细
    server_top = pane.tree.topLevelItem(1)
    labels = [server_top.child(i).text(0) for i in range(server_top.childCount())]
    assert "证书链" in labels
    chain = next(server_top.child(i) for i in range(server_top.childCount())
                 if server_top.child(i).text(0) == "证书链")
    assert chain.childCount() == 1  # 一张证书


def test_tls_pane_placeholder_for_plain(qapp):
    pane = TlsPane()
    pane.show_flow(_flow(False, False))
    assert pane.tree.isHidden()
    assert not pane.placeholder.isHidden()
    assert "TLS" in pane.placeholder.text()


def test_tls_pane_clear(qapp):
    pane = TlsPane()
    pane.show_flow(_flow(True, True))
    pane.clear()
    assert pane.tree.topLevelItemCount() == 0
    assert pane.tree.isHidden()
    assert pane.placeholder.isHidden()  # clear 后连占位也不显示


# ---------------------------------------------------------------- DetailPanel 集成


def test_detail_panel_tls_tab_visibility(qapp):
    dp = DetailPanel()
    dp.show_flow(_flow(True, True))
    assert dp.tabs.isTabVisible(dp.tls_index) is True
    dp.show_flow(_flow(False, False))
    assert dp.tabs.isTabVisible(dp.tls_index) is False
    dp.clear()
    assert dp.tabs.isTabVisible(dp.tls_index) is False


def test_detail_panel_sticky_tab_not_polluted_by_tls(qapp):
    """用户在 HTTPS 流量停在 TLS 页，再选明文流量：sticky 应回落响应页，
    而不是被 Qt 自动跳页污染成 TLS 页 index。"""
    dp = DetailPanel()
    https = _flow(True, True)
    dp.show_flow(https)
    # 模拟用户切到 TLS 页
    dp.tabs.setCurrentIndex(dp.tls_index)
    dp._on_tab_changed(dp.tls_index)
    assert dp._sticky_tab == dp.tls_index
    # 选明文流量：TLS 页消失，sticky 必须回落到可见页
    dp.show_flow(_flow(False, False))
    assert dp.tabs.isTabVisible(dp.tls_index) is False
    assert dp._sticky_tab == dp.response_index
    assert dp.tabs.currentIndex() == dp.response_index
    # 再选 HTTPS：停在响应页（sticky 已修正），不会又被拽去 TLS 页
    dp.show_flow(https)
    assert dp.tabs.currentIndex() == dp.response_index
