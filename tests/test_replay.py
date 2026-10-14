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
        proxy.start()
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
        proxy.start()
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
