"""过滤/搜索管线测试（offscreen Qt，覆盖 3.2.1 / 3.2.2 的判定逻辑）。"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-filter-test-home")

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

_app = None


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


from app.ui.filter_model import (  # noqa: E402
    FilterConfig,
    FlowFilterProxyModel,
    SearchConfig,
)
from app.ui.flow_store import FlowStore  # noqa: E402


def _row(**kw):
    base = {
        "id": kw.get("id", "f1"),
        "method": "GET",
        "scheme": "https",
        "host": "api.example.com",
        "path": "/v1/user/list",
        "url": "https://api.example.com/v1/user/list",
        "status": 200,
        "size": 1024,
        "duration_ms": 12.0,
        "content_type": "application/json",
        "marked": "",
        "is_replay": False,
        "timestamp": 0.0,
        "is_connect": False,
    }
    base.update(kw)
    return base


class _FakeFlow:
    def __init__(self, headers="", body=b""):
        self._headers = headers
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")

    class _Msg:
        def __init__(self, headers, body):
            self.headers = _Headers(headers)
            self._body = body

        def get_content(self, strict=False):
            return self._body

    @property
    def request(self):
        return self._Msg(self._headers, b"")

    @property
    def response(self):
        return self._Msg(self._headers, self._body)


class _Headers:
    def __init__(self, text):
        self._items = []
        for line in text.split("\n"):
            if ":" in line:
                k, _, v = line.partition(":")
                self._items.append((k.strip(), v.strip()))

    def items(self, multi=False):
        return list(self._items)

    def get(self, key, default=""):
        for k, v in self._items:
            if k.lower() == key.lower():
                return v
        return default


def _make_model(rows, flow_lookup=None):
    store = FlowStore()
    for r in rows:
        store.append(r)
    model = FlowFilterProxyModel()
    model.setSourceModel(store)
    if flow_lookup:
        model.flow_lookup = flow_lookup
    return model, store


class TestDomainFilter:
    def test_blacklist_hides_matching_host(self, qapp):
        model, _ = _make_model(
            [
                _row(id="a", host="api.example.com"),
                _row(id="b", host="cdn.other.com"),
            ]
        )
        model.set_filter_config(
            FilterConfig(host_mode="blacklist", host_keywords=["example.com"])
        )
        assert model.rowCount() == 1  # other.com 保留

    def test_whitelist_shows_only_matching(self, qapp):
        model, _ = _make_model(
            [
                _row(id="a", host="api.example.com"),
                _row(id="b", host="cdn.other.com"),
            ]
        )
        model.set_filter_config(
            FilterConfig(host_mode="whitelist", host_keywords=["example.com"])
        )
        assert model.rowCount() == 1

    def test_whitelist_empty_keywords_shows_all(self, qapp):
        model, _ = _make_model([_row(id="a"), _row(id="b")])
        model.set_filter_config(FilterConfig(host_mode="whitelist", host_keywords=[]))
        assert model.rowCount() == 2  # 空白名单不过滤

    def test_multiple_keywords(self, qapp):
        model, _ = _make_model(
            [
                _row(id="a", host="api.example.com"),
                _row(id="b", host="cdn.other.com"),
                _row(id="c", host="third.net"),
            ]
        )
        model.set_filter_config(
            FilterConfig(host_mode="whitelist", host_keywords=["example.com", "other.com"])
        )
        assert model.rowCount() == 2


class TestTypeHide:
    def test_hide_connect(self, qapp):
        model, _ = _make_model(
            [_row(id="a"), _row(id="b", method="CONNECT", is_connect=True)]
        )
        model.set_filter_config(FilterConfig(hide_connect=True))
        assert model.rowCount() == 1

    def test_hide_image_by_content_type(self, qapp):
        model, _ = _make_model(
            [
                _row(id="a"),
                _row(id="b", path="/logo.png", content_type="image/png"),
            ]
        )
        model.set_filter_config(FilterConfig(hide_image=True))
        assert model.rowCount() == 1

    def test_hide_image_by_extension(self, qapp):
        model, _ = _make_model(
            [_row(id="a"), _row(id="b", path="/pic.jpg", content_type="")]
        )
        model.set_filter_config(FilterConfig(hide_image=True))
        assert model.rowCount() == 1

    def test_hide_image_does_not_hide_json(self, qapp):
        model, _ = _make_model([_row(id="a", content_type="application/json")])
        model.set_filter_config(FilterConfig(hide_image=True))
        assert model.rowCount() == 1


class TestSearch:
    def test_search_url(self, qapp):
        model, _ = _make_model(
            [_row(id="a", path="/v1/user/list"), _row(id="b", path="/v1/order")]
        )
        cfg = SearchConfig()
        cfg.text = "user"
        model.set_search_config(cfg)
        assert model.rowCount() == 1

    def test_search_case_insensitive_default(self, qapp):
        model, _ = _make_model([_row(id="a", path="/v1/User/List")])
        cfg = SearchConfig()
        cfg.text = "user"
        model.set_search_config(cfg)
        assert model.rowCount() == 1

    def test_search_headers_via_flow_lookup(self, qapp):
        flow = _FakeFlow(headers="x-token: abc123\ncontent-type: application/json")
        model, _ = _make_model([_row(id="a")], flow_lookup=lambda fid: flow)
        cfg = SearchConfig()
        cfg.text = "abc123"
        cfg.scopes = {"headers"}
        model.set_search_config(cfg)
        assert model.rowCount() == 1

    def test_search_body_via_flow_lookup(self, qapp):
        flow = _FakeFlow(headers="content-type: application/json", body="敏感数据xyz")
        model, _ = _make_model([_row(id="a")], flow_lookup=lambda fid: flow)
        cfg = SearchConfig()
        cfg.text = "敏感数据"
        cfg.scopes = {"body"}
        model.set_search_config(cfg)
        assert model.rowCount() == 1

    def test_search_body_utf8_default(self, qapp):
        """body 搜索默认 UTF-8 解码（中文可命中）。"""
        flow = _FakeFlow(
            headers="content-type: text/plain", body="中文内容".encode("utf-8")
        )
        model, _ = _make_model([_row(id="a")], flow_lookup=lambda fid: flow)
        cfg = SearchConfig()
        cfg.text = "中文"
        cfg.scopes = {"body"}
        model.set_search_config(cfg)
        assert model.rowCount() == 1

    def test_search_and_filter_combined(self, qapp):
        """过滤 + 搜索 AND 组合。"""
        model, _ = _make_model(
            [
                _row(id="a", host="api.example.com", path="/v1/user"),
                _row(id="b", host="api.example.com", path="/v1/order"),
                _row(id="c", host="cdn.other.com", path="/v1/user"),
            ]
        )
        model.set_filter_config(
            FilterConfig(host_mode="whitelist", host_keywords=["example.com"])
        )
        cfg = SearchConfig()
        cfg.text = "user"
        model.set_search_config(cfg)
        assert model.rowCount() == 1  # 只有 a 同时满足两个条件
