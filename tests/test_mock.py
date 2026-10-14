"""MockAddon 集成测试：request hook 命中即造 response、阻断上游（DESIGN.md 3.3）。

不依赖 Qt；mitmproxy 的 flow 用真实对象构造。
"""

import asyncio
import time
from pathlib import Path

import pytest

from addons.mock import MockAddon
from app.rules import CONTAINS, REGEX, Action, Match, Rule, RuleStore
from mitmproxy.test import tflow


def _make_flow(url: str):
    flow = tflow.tflow()
    flow.request.url = url
    flow.request.method = "GET"
    return flow


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def store(tmp_path):
    s = RuleStore(path=tmp_path / "rules.json")
    return s


class TestMockBasics:
    def test_no_rule_passthrough(self, store):
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/x")
        _run(addon.request(flow))
        assert flow.response is None  # 不命中：不动 flow，正常透传

    def test_hit_returns_mock_and_blocks_upstream(self, store):
        r = Rule.create("空列表")
        r.match = Match(type=CONTAINS, value="/api/user/list")
        r.action = Action(
            status=200,
            headers={"Content-Type": "application/json"},
            body='{"total":0}',
        )
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/user/list?page=1")
        _run(addon.request(flow))
        assert flow.response is not None
        assert flow.response.status_code == 200
        assert flow.response.get_text() == '{"total":0}'
        assert flow.marked == "MOCK:空列表"

    def test_first_matching_rule_wins(self, store):
        r1 = Rule.create("r1")
        r1.match = Match(type=CONTAINS, value="a.com")
        r1.action = Action(status=201, body="first")
        store.add(r1)
        r2 = Rule.create("r2")
        r2.match = Match(type=CONTAINS, value="/api/")
        r2.action = Action(status=202, body="second")
        store.add(r2)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/x")
        _run(addon.request(flow))
        assert flow.response.status_code == 201  # 先声明先匹配

    def test_disabled_rule_skipped(self, store):
        r = Rule.create("disabled")
        r.match = Match(type=CONTAINS, value="/api/")
        r.action = Action(status=200, body="x")
        r.enabled = False
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/x")
        _run(addon.request(flow))
        assert flow.response is None

    def test_abnormal_status(self, store):
        r = Rule.create("503")
        r.match = Match(type=CONTAINS, value="/api/down")
        r.action = Action(
            status=503, headers={"Retry-After": "30"}, body="maintenance"
        )
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/down")
        _run(addon.request(flow))
        assert flow.response.status_code == 503
        assert flow.response.headers.get("Retry-After") == "30"
        assert flow.response.get_text() == "maintenance"


class TestMockSubstitution:
    def test_regex_group_substitution_in_body_and_headers(self, store):
        r = Rule.create("动态")
        r.match = Match(type=REGEX, value=r"/v1/user/(\d+)/detail")
        r.action = Action(
            status=200,
            headers={"X-User-Id": "$1", "Content-Type": "application/json"},
            body='{"id":"$1"}',
        )
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/v1/user/42/detail")
        _run(addon.request(flow))
        assert flow.response.get_text() == '{"id":"42"}'
        assert flow.response.headers.get("X-User-Id") == "42"


class TestMockFile:
    def test_file_body_read_at_request_time(self, store, tmp_path):
        """请求时读取：改文件内容，不动规则，mock 输出跟随变化。"""
        data_file = tmp_path / "mock.json"
        data_file.write_text('{"v":1}', encoding="utf-8")
        r = Rule.create("文件")
        r.match = Match(type=CONTAINS, value="/api/config")
        r.action = Action(status=200, body_source="file", file_path=str(data_file))
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/config")
        _run(addon.request(flow))
        assert flow.response.get_text() == '{"v":1}'

        # 改文件 → 再请求，输出立即变
        data_file.write_text('{"v":2}', encoding="utf-8")
        flow2 = _make_flow("https://a.com/api/config")
        _run(addon.request(flow2))
        assert flow2.response.get_text() == '{"v":2}'

    def test_file_content_type_inferred(self, store, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<h1>hi</h1>", encoding="utf-8")
        r = Rule.create("html")
        r.match = Match(type=CONTAINS, value="/page")
        r.action = Action(status=200, body_source="file", file_path=str(f))
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/page")
        _run(addon.request(flow))
        # 文本类自动补 charset=utf-8（防 latin-1 乱码）
        assert flow.response.headers.get("Content-Type") == "text/html; charset=utf-8"

    def test_text_body_gets_charset(self, store):
        """内联文本 body：text/* 未声明 charset 时自动补 utf-8。"""
        r = Rule.create("中文")
        r.match = Match(type=CONTAINS, value="/cn")
        r.action = Action(
            status=200, headers={"Content-Type": "text/plain"}, body="你好"
        )
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/cn")
        _run(addon.request(flow))
        assert flow.response.headers.get("Content-Type") == "text/plain; charset=utf-8"
        assert flow.response.get_text() == "你好"

    def test_file_explicit_content_type_wins(self, store, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02")
        r = Rule.create("bin")
        r.match = Match(type=CONTAINS, value="/bin")
        r.action = Action(
            status=200,
            headers={"Content-Type": "application/octet-stream"},
            body_source="file",
            file_path=str(f),
        )
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/bin")
        _run(addon.request(flow))
        assert flow.response.headers.get("Content-Type") == "application/octet-stream"

    def test_missing_file_returns_502_and_marks_rule(self, store, tmp_path):
        r = Rule.create("缺失")
        r.match = Match(type=CONTAINS, value="/api/gone")
        r.action = Action(
            status=200, body_source="file", file_path=str(tmp_path / "nope.json")
        )
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/gone")
        _run(addon.request(flow))
        assert flow.response.status_code == 502
        assert "不存在" in flow.response.get_text()
        assert store.get(r.id).error is not None  # 规则被标红

    def test_binary_file_passthrough(self, store, tmp_path):
        f = tmp_path / "pixel.png"
        f.write_bytes(bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]))
        r = Rule.create("png")
        r.match = Match(type=CONTAINS, value="/pixel")
        r.action = Action(status=200, body_source="file", file_path=str(f))
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/pixel")
        _run(addon.request(flow))
        assert flow.response.raw_content == bytes(
            [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]
        )


class TestMockLatency:
    def test_latency_delays_response(self, store):
        r = Rule.create("慢")
        r.match = Match(type=CONTAINS, value="/slow")
        r.action = Action(status=200, body="ok", latency_ms=400)
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/slow")
        start = time.monotonic()
        _run(addon.request(flow))
        elapsed = time.monotonic() - start
        assert elapsed >= 0.35
        assert flow.response.status_code == 200

    def test_zero_latency_immediate(self, store):
        r = Rule.create("快")
        r.match = Match(type=CONTAINS, value="/fast")
        r.action = Action(status=200, body="ok", latency_ms=0)
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/fast")
        _run(addon.request(flow))
        assert flow.response is not None


class TestMethodFilter:
    def test_method_mismatch_passthrough(self, store):
        r = Rule.create("只 POST")
        r.match = Match(type=CONTAINS, value="/api/", method="POST")
        r.action = Action(status=200, body="x")
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/x")  # GET
        _run(addon.request(flow))
        assert flow.response is None  # 方法不符：透传

    def test_method_match_case_insensitive(self, store):
        r = Rule.create("只 OPTIONS")
        r.match = Match(type=CONTAINS, value="/api/", method="options")
        r.action = Action(status=200, body="ok", headers={"Allow": "GET,POST"})
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/x")
        flow.request.method = "OPTIONS"
        _run(addon.request(flow))
        assert flow.response is not None
        assert flow.response.headers["Allow"] == "GET,POST"

    def test_any_method_rule_hits_all_methods(self, store):
        r = Rule.create("任意")
        r.match = Match(type=CONTAINS, value="/api/")
        r.action = Action(status=200, body="x")
        store.add(r)
        addon = MockAddon(store)
        for method in ("GET", "POST", "DELETE", "OPTIONS"):
            flow = _make_flow("https://a.com/api/x")
            flow.request.method = method
            _run(addon.request(flow))
            assert flow.response is not None, method


class TestMockRedirect:
    def test_redirect_rewrites_url_and_passthrough(self, store):
        r = Rule.create("转发")
        r.match = Match(type=CONTAINS, value="/api/v1/")
        r.action = Action(redirect_url="https://staging.example.com/api/v2/")
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://prod.example.com/api/v1/user")
        _run(addon.request(flow))
        assert flow.response is None  # 不造响应，放行到新上游
        # redirect_url 是完整目标（不自动拼原路径；要拼路径用 $1 正则替换）
        assert flow.request.pretty_url == "https://staging.example.com/api/v2/"
        assert flow.marked == "MOCK:转发"

    def test_redirect_supports_substitution(self, store):
        r = Rule.create("按组转发")
        r.match = Match(type=REGEX, value=r"https://a\.com/v(\d+)/(.*)")
        r.action = Action(redirect_url="https://b.com/v$1/rewritten/$2")
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/v1/user/42")
        _run(addon.request(flow))
        assert flow.request.pretty_url == "https://b.com/v1/rewritten/user/42"

    def test_redirect_records_hit(self, store):
        r = Rule.create("转发")
        r.match = Match(type=CONTAINS, value="/api/")
        r.action = Action(redirect_url="https://b.com/")
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/x")
        _run(addon.request(flow))
        assert next(x for x in store.all()).hits == 1

    def test_redirect_invalid_target_returns_502(self, store):
        r = Rule.create("坏目标")
        r.match = Match(type=CONTAINS, value="/api/")
        r.action = Action(redirect_url="ftp://not-http")
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/x")
        _run(addon.request(flow))
        assert flow.response is not None
        assert flow.response.status_code == 502
        assert store.get(r.id).error and "http(s)" in store.get(r.id).error

    def test_redirect_loop_capped(self, store):
        """目标 URL 仍命中同一条 contains 规则 → 不能无限改写。"""
        r = Rule.create("自指")
        r.match = Match(type=CONTAINS, value="/api/")
        r.action = Action(redirect_url="https://a.com/api/loop")
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/start")
        for _ in range(12):
            _run(addon.request(flow))
            if flow.response is not None:
                break
        assert flow.response.status_code == 502
        assert "循环" in (store.get(r.id).error or "")

    def test_redirect_empty_after_substitution_returns_502(self, store):
        r = Rule.create("空目标")
        r.match = Match(type=REGEX, value=r"/api/(\w+)")
        r.action = Action(redirect_url="$9")  # 不存在的组 → 替换成空
        store.add(r)
        addon = MockAddon(store)
        flow = _make_flow("https://a.com/api/x")
        _run(addon.request(flow))
        assert flow.response.status_code == 502
