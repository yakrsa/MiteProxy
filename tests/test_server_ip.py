"""「服务器 IP」列：摘要提取 / 列表展示 / 搜索命中 / 真实代理活体。

覆盖点（见 DESIGN.md 3.2）：
- extract_server_ip 的取值优先级与退化路径（peername → address → 空）；
- summarize 产出 server_ip 字段；
- FlowStore 列位置 + 取不到时显示 `-`；
- Ctrl+F（URL 范围）能按 IP 过滤；
- 真实代理透传时确实记录到上游 IP。
"""

import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-serverip-test-home")

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

_app = None


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


from addons.capture import CaptureAddon, extract_server_ip  # noqa: E402
from app.proxy import ProxyService  # noqa: E402
from app.ui.filter_model import (  # noqa: E402
    SCOPE_URL,
    FlowFilterProxyModel,
    SearchConfig,
)
from app.ui.flow_store import COLUMNS, COL_SERVER_IP, FlowStore  # noqa: E402


def _conn(peername=None, address=None):
    return SimpleNamespace(peername=peername, address=address)


def _flow(peername=("1.2.3.4", 443), address=("api.example.com", 80)):
    req = SimpleNamespace(
        method="GET",
        scheme="http",
        pretty_host="api.example.com",
        path="/v1/user",
        pretty_url="http://api.example.com/v1/user",
        timestamp_start=1.0,
    )
    res = SimpleNamespace(
        status_code=200,
        timestamp_end=1.1,
        raw_content=b"ok",
        headers={"content-type": "text/plain"},
    )
    return SimpleNamespace(
        id="f1", request=req, response=res, server_conn=_conn(peername, address)
    )


def _row(**kw):
    return {
        "id": kw.get("id", "f1"),
        "method": "GET",
        "scheme": "http",
        "host": "api.example.com",
        "server_ip": kw.get("server_ip", ""),
        "path": "/v1/user",
        "url": "http://api.example.com/v1/user",
        "status": 200,
        "size": 1024,
        "duration_ms": 12.0,
        "content_type": "text/plain",
        "marked": "",
        "is_replay": False,
        "timestamp": 0.0,
        "is_connect": False,
    }


class TestExtractServerIp:
    def test_peername_ipv4(self):
        assert extract_server_ip(_flow()) == "1.2.3.4"

    def test_peername_ipv6(self):
        flow = _flow(peername=("2606:2800:220:1:248:1893:25c8:1946", 443))
        assert extract_server_ip(flow) == "2606:2800:220:1:248:1893:25c8:1946"

    def test_peername_wins_over_address(self):
        flow = _flow(peername=("9.9.9.9", 443), address=("10.0.0.1", 80))
        assert extract_server_ip(flow) == "9.9.9.9"

    def test_address_fallback_when_ip(self):
        flow = _flow(peername=None, address=("10.0.0.7", 8080))
        assert extract_server_ip(flow) == "10.0.0.7"

    def test_address_hostname_not_used(self):
        """address 可能是未解析的域名，不能当成 IP 显示。"""
        flow = _flow(peername=None, address=("api.example.com", 443))
        assert extract_server_ip(flow) == ""

    def test_no_server_conn_attribute(self):
        assert extract_server_ip(SimpleNamespace(id="f1")) == ""

    def test_server_conn_none(self):
        assert extract_server_ip(SimpleNamespace(server_conn=None)) == ""

    def test_server_conn_raises(self):
        """CONNECT 隧道等场景取 server_conn 可能抛异常，不能影响抓包。"""

        class Boom:
            @property
            def server_conn(self):
                raise RuntimeError("no connection")

        assert extract_server_ip(Boom()) == ""


class TestSummarize:
    def test_includes_server_ip(self):
        summary = CaptureAddon.summarize(_flow())
        assert summary["server_ip"] == "1.2.3.4"

    def test_empty_when_unresolved(self):
        flow = _flow(peername=None, address=None)
        assert CaptureAddon.summarize(flow)["server_ip"] == ""


class TestStoreColumn:
    def test_column_order(self):
        assert COL_SERVER_IP == 3
        assert COLUMNS == [
            "#", "方法", "主机", "服务器 IP", "路径",
            "状态", "请求体", "响应", "耗时(ms)", "标记",
        ]

    def test_display_ip_and_dash_fallback(self):
        store = FlowStore()
        store.append(_row(server_ip="1.2.3.4"))
        store.append(_row(id="f2", server_ip=""))
        assert store.data(store.index(0, COL_SERVER_IP)) == "1.2.3.4"
        assert store.data(store.index(1, COL_SERVER_IP)) == "-"

    def test_tooltip_mentions_ip(self):
        store = FlowStore()
        store.append(_row(server_ip="1.2.3.4"))
        tip = store.data(store.index(0, COL_SERVER_IP), Qt.ItemDataRole.ToolTipRole)
        assert "1.2.3.4" in tip

    def test_search_by_ip_in_url_scope(self):
        store = FlowStore()
        store.append(_row(id="a", server_ip="10.1.2.3"))
        store.append(_row(id="b", host="cdn.other.com", server_ip="8.8.8.8"))
        proxy = FlowFilterProxyModel()
        proxy.setSourceModel(store)

        cfg = SearchConfig()
        cfg.text = "10.1.2.3"
        cfg.scopes = {SCOPE_URL}
        proxy.set_search_config(cfg)
        assert proxy.rowCount() == 1

        cfg.text = "10.9.9.9"
        proxy.set_search_config(cfg)
        assert proxy.rowCount() == 0


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
    server = HTTPServer(("127.0.0.1", 18899), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


class TestServerIpThroughProxy:
    def test_passthrough_records_upstream_ip(self, upstream):
        capture = CaptureAddon()
        proxy = ProxyService(host="127.0.0.1", port=18086, addons=[capture])
        proxy.start()
        try:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": "127.0.0.1:18086"})
            )
            with opener.open("http://127.0.0.1:18899/api/real", timeout=10) as resp:
                assert resp.status == 200

            deadline = time.time() + 5
            while time.time() < deadline and not capture.flows:
                time.sleep(0.05)
            assert capture.flows, "流量未进入 CaptureAddon"

            flow = next(iter(capture.flows.values()))
            assert CaptureAddon.summarize(flow)["server_ip"] == "127.0.0.1"
        finally:
            proxy.stop()
