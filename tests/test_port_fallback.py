"""端口被占用自动顺延：CertServer 与 ProxyService 的端口回退行为。"""

import socket

import pytest

from app import certserver
from app.certserver import CertServer
from app.proxy import ProxyService, _port_bindable


def _occupy_0_0_0_0() -> tuple[socket.socket, int]:
    """占住一个 0.0.0.0 端口（保持打开），返回 (socket, port)。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("0.0.0.0", 0))
    port = s.getsockname()[1]
    return s, port


class TestPortBindable:
    def test_free_port_is_bindable(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        assert _port_bindable("127.0.0.1", port) is True

    def test_occupied_port_is_not_bindable(self):
        s, port = _occupy_0_0_0_0()
        try:
            assert _port_bindable("0.0.0.0", port) is False
        finally:
            s.close()


class TestProxyPickPort:
    def test_requested_port_free_returns_it(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        svc = ProxyService(host="0.0.0.0", port=port)
        assert svc._pick_port() == port

    def test_requested_port_occupied_falls_forward(self):
        s, port = _occupy_0_0_0_0()
        try:
            svc = ProxyService(host="0.0.0.0", port=port)
            chosen = svc._pick_port()
            assert chosen is not None and chosen > port
        finally:
            s.close()


class TestCertServerPortFallback:
    @pytest.fixture()
    def fake_ca(self, tmp_path, monkeypatch):
        """load_ca 只要求非空文件（DER 转换失败会降级为仅 PEM）。"""
        ca = tmp_path / "ca.pem"
        ca.write_bytes(b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n")
        monkeypatch.setattr(certserver, "CA_PEM_PATH", ca)
        monkeypatch.setattr(certserver, "_lan_ip", lambda: "127.0.0.1")
        return ca

    def test_occupied_port_falls_forward(self, fake_ca):
        s, port = _occupy_0_0_0_0()
        try:
            server = CertServer(port=port)
            try:
                server.start()
                assert server.running
                # 请求端口被占，实际端口必须顺延到后面的可用端口
                assert server.port > port
                assert f":{server.port}" in server.url
            finally:
                server.stop()
        finally:
            s.close()

    def test_free_port_keeps_requested(self, fake_ca):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        server = CertServer(port=port)
        try:
            server.start()
            assert server.port == port
        finally:
            server.stop()
