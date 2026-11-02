"""端口被占用自动顺延：CertServer 与 ProxyService 的端口回退行为。"""

import socket
import sys

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


def _make_time_wait() -> int:
    """造一个处于 TIME_WAIT 的端口并返回它。

    服务端 accept 后由服务端主动 close，该连接所在的本地端口即进入
    TIME_WAIT。后续裸 bind 该端口会 EADDRINUSE，带 SO_REUSEADDR 才能绑。
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.listen(1)
    cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cli.connect(("127.0.0.1", port))
    conn, _ = srv.accept()
    conn.close()          # 服务端主动关闭 -> port 进入 TIME_WAIT
    srv.close()
    cli.close()
    return port


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows 上探测刻意不带 SO_REUSEADDR，TIME_WAIT 仍会被判占用（与 asyncio 口径一致）",
)
class TestTimeWaitNotMisjudged:
    """TIME_WAIT 残留不该被当成「端口被占用」。

    回归 v3.0.4 的严重体验 bug：``_port_bindable`` 用裸 socket 探测，
    TIME_WAIT 期间 bind 失败，被误判成占用，于是重启代理时自动切端口并
    弹「端口被占用」——用户看到的就是「上次的端口没释放」。
    """

    def test_time_wait_port_is_bindable(self):
        port = _make_time_wait()
        assert _port_bindable("127.0.0.1", port) is True

    def test_pick_port_keeps_requested_after_time_wait(self):
        port = _make_time_wait()
        svc = ProxyService(host="127.0.0.1", port=port)
        assert svc._pick_port() == port
