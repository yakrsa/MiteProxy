"""端到端：真实代理上验证 mock 命中/透传 + HTTPS 解密（Gate 2 / Gate 3 活体部分）。"""

import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from addons.capture import CaptureAddon
from addons.mock import MockAddon
from app.proxy import ProxyService
from app.rules import CONTAINS, REGEX, Action, Match, Rule, RuleStore


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = b'{"from":"upstream"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def upstream():
    server = HTTPServer(("127.0.0.1", 18898), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _get_via_proxy(port: int, url: str) -> tuple[int, bytes]:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": f"127.0.0.1:{port}"})
    )
    try:
        with opener.open(url, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.fixture()
def store(tmp_path):
    s = RuleStore(path=tmp_path / "rules.json")
    return s


class TestMockThroughProxy:
    def test_mock_hit_and_passthrough(self, upstream, store):
        # 两条规则：inline mock + 文件 mock
        r1 = Rule.create("inline")
        r1.match = Match(type=CONTAINS, value="/api/mock/inline")
        r1.action = Action(
            status=200,
            headers={"Content-Type": "application/json"},
            body='{"mocked":true}',
        )
        store.add(r1)

        data_file = store.path.parent / "mockdata.json"
        data_file.write_text('{"from":"file"}', encoding="utf-8")
        r2 = Rule.create("file")
        r2.match = Match(type=REGEX, value=r"/api/mock/file")
        r2.action = Action(status=201, body_source="file", file_path=str(data_file))
        store.add(r2)

        capture = CaptureAddon()
        proxy = ProxyService(
            host="127.0.0.1",
            port=18083,
            addons=[MockAddon(store), capture],
        )
        proxy.start()
        try:
            # 命中 inline mock
            status, body = _get_via_proxy(18083, "http://127.0.0.1:18898/api/mock/inline")
            assert status == 200
            assert b'"mocked":true' in body

            # 命中文件 mock（201 + 文件内容）
            status, body = _get_via_proxy(18083, "http://127.0.0.1:18898/api/mock/file")
            assert status == 201
            assert b'"from":"file"' in body

            # 未命中 → 透传到上游
            status, body = _get_via_proxy(18083, "http://127.0.0.1:18898/api/real")
            assert status == 200
            assert b'"from":"upstream"' in body

            # 三条都进了流量列表
            deadline = time.time() + 5
            while time.time() < deadline and len(capture.flows) < 3:
                time.sleep(0.05)
            assert len(capture.flows) == 3
            marked = [f.marked for f in capture.flows.values() if f.marked]
            assert "MOCK:inline" in marked
            assert "MOCK:file" in marked
        finally:
            proxy.stop()

    def test_https_decryption(self):
        """HTTPS 经代理解密（curl -k 信任 mitmproxy CA）。"""
        proxy = ProxyService(host="127.0.0.1", port=18084)
        proxy.start()
        try:
            out = subprocess.run(
                ["curl", "-sk", "-x", "127.0.0.1:18084", "https://example.com"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert out.returncode == 0
            assert "Example Domain" in out.stdout
        finally:
            proxy.stop()


class TestImportedFarxRuleLive:
    def test_imported_farx_rule_actually_mocks(self, tmp_path):
        """Gate 4 活体：导入官方 FARX 样本 → 规则在真实代理上生效。"""
        from addons.importers import farx

        result = farx.parse_file(
            Path(__file__).parent / "fixtures" / "map-local-manual.farx"
        )
        assert result.ok_count == 1
        store = RuleStore(path=tmp_path / "rules.json")
        count, ids = store.merge(result.rules)
        assert count == 1
        # 官方样本规则默认 Enabled=false（忠实导入），模拟用户在界面上启用
        store.update(ids[0], enabled=True)

        capture = CaptureAddon()
        proxy = ProxyService(
            host="127.0.0.1", port=18085, addons=[MockAddon(store), capture]
        )
        proxy.start()
        try:
            # 该规则匹配 example.com，返回 FARX 里的 HTML
            out = subprocess.run(
                ["curl", "-s", "-x", "127.0.0.1:18085", "http://example.com/"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert out.returncode == 0
            assert "Fiddler Everywhere - Example Domain" in out.stdout
            assert "<!doctype html>" in out.stdout.lower()
        finally:
            proxy.stop()


class TestStopReleasesPort:
    def test_stop_releases_listening_port(self):
        """stop() 后端口必须真正释放（mitmproxy ProxyServer 无 done 钩子，
        master.run() 返回不关监听 socket——ProxyService._amain 兜底关闭）。
        释放失败的话「停止代理→再启动同端口」会 EADDRINUSE。"""
        import socket

        # 找一个空闲端口
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        proxy = ProxyService(host="127.0.0.1", port=port)
        proxy.start()
        deadline = time.monotonic() + 5.0
        while not proxy.running and time.monotonic() < deadline:
            time.sleep(0.05)
        assert proxy.running

        proxy.stop(timeout=5.0)
        assert not proxy.running

        # 端口必须能立刻重新绑定（旧实现 stop 后 socket 仍 LISTEN，此处失败）
        rebind = socket.socket()
        try:
            rebind.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            rebind.bind(("127.0.0.1", port))
            rebind.listen(1)
        finally:
            rebind.close()


class TestBindAllInterfaces:
    def test_default_host_binds_all_and_serves_loopback(self):
        """默认监听 0.0.0.0（全部网卡）：手机/局域网设备可通过内网 IP 连代理，
        本机 127.0.0.1 照常工作。只绑 127.0.0.1 会导致「本机能用手机连不上」。"""
        import socket as _socket

        assert ProxyService(port=18099).host == "0.0.0.0"

        probe = _socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        proxy = ProxyService(port=port)   # 默认 host
        proxy.start()
        deadline = time.monotonic() + 5.0
        while not proxy.running and time.monotonic() < deadline:
            time.sleep(0.05)
        assert proxy.running
        try:
            # running=True 后 server socket 就绪有微小延迟，重试连接
            deadline = time.monotonic() + 5.0
            while True:
                try:
                    conn = _socket.create_connection(("127.0.0.1", port), timeout=3)
                    conn.close()
                    break
                except ConnectionRefusedError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.1)
        finally:
            proxy.stop(timeout=5.0)
