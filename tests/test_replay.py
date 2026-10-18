"""重放测试：副本语义 + 端到端（真代理 + 真上游，验证重放真的发出请求）。

对齐 Fiddler：原会话保留，重放产生新会话（DESIGN.md 3.6）。
"""

import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.proxy import ProxyService
from app.replay import apply_request_edits, make_replay_copy
from addons.capture import CaptureAddon


class TestReplayCopy:
    def test_copy_does_not_mutate_original(self):
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        flow.request.url = "https://a.com/api/x"
        flow.request.method = "POST"
        flow.request.content = b'{"old":1}'

        copy = make_replay_copy(flow)
        assert copy.id != flow.id
        assert copy.request.method == "POST"
        assert copy.request.content == b'{"old":1}'
        # 原会话保留响应，未被污染
        assert flow.response is not None
        assert flow.response.status_code == 200
        assert not flow.is_replay if hasattr(flow, "is_replay") else True

        # 改副本不影响原会话
        apply_request_edits(copy, method="PUT", body='{"new":2}')
        assert copy.request.method == "PUT"
        assert flow.request.method == "POST"
        assert flow.request.content == b'{"old":1}'

    def test_copy_clears_response_and_marked(self):
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        flow.marked = "MOCK:旧"
        copy = make_replay_copy(flow)
        assert copy.response is None
        assert copy.marked == ""
        assert flow.marked == "MOCK:旧"  # 原会话标记保留

    def test_apply_edits_headers_replace(self):
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        flow.request.headers["X-Old"] = "1"
        copy = make_replay_copy(flow)
        apply_request_edits(copy, headers={"X-New": "2", "Content-Type": "text/plain"})
        assert copy.request.headers.get("X-New") == "2"
        assert copy.request.headers.get("X-Old") is None  # 整体替换
        # 原会话 headers 不受影响
        assert flow.request.headers.get("X-Old") == "1"

    def test_apply_edits_url_and_body(self):
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        copy = make_replay_copy(flow)
        apply_request_edits(
            copy, method="post", url="https://a.com/api/y", body="你好"
        )
        assert copy.request.method == "POST"  # 自动大写
        assert copy.request.url == "https://a.com/api/y"
        assert copy.request.content == "你好".encode("utf-8")


class TestEnsureAuthority:
    """回归：HTTP/2 的 :authority 不在 headers 里、会话也不落盘，构造/恢复出来
    的请求默认 authority 为空。不补的话重放出去「既无 Host 也无 :authority」，
    上游网关直接判 400（实测 hq.yxzq.com 返回 alibaba-ga 的 400 Bad Request）。"""

    def test_http2_without_host_gets_authority(self):
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        flow.request.url = "https://a.com/api/x"
        flow.request.http_version = "HTTP/2.0"
        flow.request.headers.pop("host", None)
        assert flow.request.authority == ""

        copy = make_replay_copy(flow)
        assert copy.request.authority == "a.com"
        assert copy.request.first_line_format == "absolute"

    def test_http2_non_default_port_kept(self):
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        flow.request.url = "https://a.com:8443/api/x"
        flow.request.http_version = "HTTP/2.0"
        flow.request.headers.pop("host", None)
        copy = make_replay_copy(flow)
        assert copy.request.authority == "a.com:8443"

    def test_http1_with_host_left_untouched(self):
        """HTTP/1 且带 Host 的请求保持 origin-form，不无谓改成绝对形式。"""
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        flow.request.url = "https://a.com/api/x"
        flow.request.http_version = "HTTP/1.1"
        flow.request.headers["host"] = "a.com"
        assert flow.request.authority == ""

        copy = make_replay_copy(flow)
        assert copy.request.authority == ""

    def test_edited_url_syncs_authority(self):
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        flow.request.url = "https://a.com/api/x"
        flow.request.http_version = "HTTP/2.0"
        flow.request.headers.pop("host", None)
        copy = make_replay_copy(flow)

        apply_request_edits(copy, url="https://b.com:8443/api/y")
        assert copy.request.authority == "b.com:8443"
        assert copy.request.pretty_url == "https://b.com:8443/api/y"

    def test_ipv6_authority_bracketed(self):
        """IPv6 字面量必须带方括号：裸拼会得到 `::1:8080` 这种畸形 authority。"""
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        flow.request.url = "http://[::1]:8080/api/x"
        flow.request.http_version = "HTTP/2.0"
        flow.request.headers.pop("host", None)

        copy = make_replay_copy(flow)
        assert copy.request.authority == "[::1]:8080"
        # 默认端口不写出来，IPv6 同样要带括号
        assert copy.request.host == "::1"

    def test_format_url_ipv6_roundtrips(self):
        """pretty_url 对 IPv6 不加方括号、无法再解析；format_request_url 必须可往返。

        存档用它，恢复时才不会 `Request.make` 抛 ValueError 把整份会话打不开。
        """
        from mitmproxy.http import Request

        from app.replay import format_request_url

        for url in ("http://[::1]:8080/x?a=1", "https://[2001:db8::1]/y", "http://[::1]/x"):
            req = Request.make("GET", url)
            got = format_request_url(req)
            assert got == url
            # 能再解析回来（不抛 ValueError）= 存盘/导出后不会坏。
            # 注意不能再断言 again.url：mitmproxy 的 url getter 本身就不加方括号。
            again = Request.make("GET", got)
            assert (again.host, again.port, again.path) == (req.host, req.port, req.path)


# ---------------------------------------------------------------- 端到端


class _CountingHandler(BaseHTTPRequestHandler):
    hits = 0
    bodies = []

    def do_GET(self):  # noqa: N802
        type(self).hits += 1
        body = b'{"ok":1}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length)
        type(self).hits += 1
        type(self).bodies.append(data)
        body = b'{"posted":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def upstream():
    _CountingHandler.hits = 0
    _CountingHandler.bodies = []
    server = HTTPServer(("127.0.0.1", 18899), _CountingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()  # 必须关 socket，否则端口不释放，下一个用例绑定失败
    thread.join(timeout=2)


def _start_proxy(proxy) -> None:
    """启动代理并等它真正就绪再返回。

    ``ProxyService.start()`` 只负责起线程，mitmproxy 是**异步绑定端口**的；
    紧接着就发请求会偶发 ``ConnectionRefused``（固定端口 + 线程调度，本地连跑
    几次能挂一次）。等 ``_master`` 建好再继续，测试才稳定。
    """
    proxy.start()
    deadline = time.time() + 10
    while time.time() < deadline and getattr(proxy, "_master", None) is None:
        time.sleep(0.02)


def _get_via_proxy(port: int, path: str) -> bytes:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": f"127.0.0.1:{port}"})
    )
    with opener.open(f"http://127.0.0.1:18899{path}", timeout=10) as resp:
        return resp.read()


class TestReplayEndToEnd:
    def test_replay_sends_second_request(self, upstream):
        """抓到的请求重放后，上游应收到第二次请求，且新会话带 REPLAY 标记。"""
        capture = CaptureAddon()
        proxy = ProxyService(host="127.0.0.1", port=18081, addons=[capture])
        _start_proxy(proxy)
        try:
            body = _get_via_proxy(18081, "/hello")
            assert b'"ok"' in body

            # 等 flow 落库
            deadline = time.time() + 5
            while time.time() < deadline and len(capture.flows) == 0:
                time.sleep(0.05)
            assert len(capture.flows) == 1
            flow = next(iter(capture.flows.values()))

            # 重放（副本）
            copy = make_replay_copy(flow)
            assert proxy.replay_flow(copy) is True

            # 上游收到第二次请求
            deadline = time.time() + 8
            while time.time() < deadline and _CountingHandler.hits < 2:
                time.sleep(0.05)
            assert _CountingHandler.hits == 2, "重放未真正发出请求"

            # 新会话进入捕获列表且带 is_replay
            deadline = time.time() + 5
            while time.time() < deadline and len(capture.flows) < 2:
                time.sleep(0.05)
            assert len(capture.flows) == 2
            replayed = [f for f in capture.flows.values() if f.is_replay]
            assert len(replayed) == 1
            assert replayed[0].id == copy.id
            # 原会话未被动过
            assert flow.is_replay in (None, "")
            assert flow.response is not None
        finally:
            proxy.stop()

    def test_edited_replay_sends_modified_request(self, upstream):
        """编辑 body 后重放：上游收到的应是修改后的 body。"""
        capture = CaptureAddon()
        proxy = ProxyService(host="127.0.0.1", port=18082, addons=[capture])
        _start_proxy(proxy)
        try:
            _get_via_proxy(18082, "/seed")
            deadline = time.time() + 5
            while time.time() < deadline and len(capture.flows) == 0:
                time.sleep(0.05)
            flow = next(iter(capture.flows.values()))

            copy = make_replay_copy(flow)
            apply_request_edits(
                copy,
                method="POST",
                url="http://127.0.0.1:18899/edited",
                headers={"Content-Type": "application/json"},
                body='{"edited":true}',
            )
            assert proxy.replay_flow(copy) is True

            deadline = time.time() + 8
            while time.time() < deadline and not _CountingHandler.bodies:
                time.sleep(0.05)
            assert _CountingHandler.bodies, "编辑后的请求未发出"
            assert b'"edited":true' in _CountingHandler.bodies[-1]
        finally:
            proxy.stop()
