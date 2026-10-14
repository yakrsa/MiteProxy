"""RuleStore / Match / Action 单元测试。"""

import json

import pytest

from app import rules as R
from app.rules import (
    CONTAINS,
    EXACT,
    REGEX,
    WILDCARD,
    Action,
    Match,
    Rule,
    RuleStore,
)


class TestMatch:
    def test_exact(self):
        m = Match(type=EXACT, value="https://a.com/x")
        assert m.match_url("https://a.com/x") is not False
        assert m.match_url("https://a.com/y") is False

    def test_contains(self):
        m = Match(type=CONTAINS, value="/api/user")
        assert m.match_url("https://a.com/api/user/list?id=1") is not False
        assert m.match_url("https://a.com/api/order") is False

    def test_contains_empty_never_matches(self):
        m = Match(type=CONTAINS, value="")
        assert m.match_url("https://a.com/anything") is False

    def test_wildcard_single_segment(self):
        m = Match(type=WILDCARD, value="https://a.com/v1/*/detail")
        assert m.match_url("https://a.com/v1/123/detail") is not False
        assert m.match_url("https://a.com/v1/123/456/detail") is False

    def test_wildcard_double_star(self):
        m = Match(type=WILDCARD, value="https://a.com/**")
        assert m.match_url("https://a.com/v1/123/detail") is not False
        assert m.match_url("https://b.com/") is False

    def test_wildcard_special_chars_escaped(self):
        # 通配符里的正则特殊字符必须被转义
        m = Match(type=WILDCARD, value="https://a.com/x.y*z")
        assert m.match_url("https://a.com/x.yQz") is not False
        assert m.match_url("https://a.com/xAyz") is False

    def test_regex_with_groups(self):
        m = Match(type=REGEX, value=r"/v1/user/(\d+)/detail")
        result = m.match_url("https://a.com/v1/user/42/detail")
        assert result is not False
        assert result.group(1) == "42"

    def test_regex_invalid_never_matches(self):
        m = Match(type=REGEX, value="([unclosed")
        assert m.match_url("https://a.com/") is False

    def test_regex_invalid_compile_returns_none(self):
        m = Match(type=REGEX, value="([unclosed")
        assert m.compile() is None


class TestAction:
    def test_status_clamped(self):
        assert Action.from_dict({"status": 999}).status == 599
        assert Action.from_dict({"status": 10}).status == 100
        assert Action.from_dict({"status": "abc"}).status == 200

    def test_latency_clamped(self):
        assert Action.from_dict({"latency_ms": 999999}).latency_ms == 60_000
        assert Action.from_dict({"latency_ms": -5}).latency_ms == 0

    def test_body_source_fallback(self):
        assert Action.from_dict({"body_source": "weird"}).body_source == "inline"


class TestRuleStore:
    def test_add_find_order(self, store):
        r1 = Rule.create("r1")
        r1.match = Match(type=CONTAINS, value="a.com")
        r2 = Rule.create("r2")
        r2.match = Match(type=CONTAINS, value="a.com")
        store.add(r1)
        store.add(r2)
        rule, _ = store.find_rule("https://a.com/")
        assert rule.id == r1.id  # 先声明先匹配

    def test_disabled_skipped(self, store):
        r1 = Rule.create("r1")
        r1.enabled = False
        r1.match = Match(type=CONTAINS, value="a.com")
        store.add(r1)
        r2 = Rule.create("r2")
        r2.match = Match(type=CONTAINS, value="a.com")
        store.add(r2)
        rule, _ = store.find_rule("https://a.com/")
        assert rule.id == r2.id

    def test_save_load_roundtrip(self, store):
        r = Rule.create("持久化")
        r.match = Match(type=REGEX, value=r"/u/(\d+)")
        r.action = Action(status=503, headers={"X-A": "b"}, latency_ms=1200)
        store.add(r)
        store2 = RuleStore(path=store.path)
        store2.load()
        loaded = store2.all()[0]
        assert loaded.name == "持久化"
        assert loaded.match.type == REGEX
        assert loaded.action.status == 503
        assert loaded.action.latency_ms == 1200

    def test_corrupt_file_backed_up(self, store, caplog):
        store.path.write_text("{broken json", encoding="utf-8")
        store.load()
        assert store.all() == []
        assert store.path.with_suffix(".json.bak").exists()

    def test_merge_renames_duplicates(self, store):
        r = Rule.create("同名")
        store.add(r)
        n, ids = store.merge([Rule.create("同名")])
        assert n == 1
        names = {x.name for x in store.all()}
        assert names == {"同名", "同名 (2)"}
        assert ids[0] != r.id  # id 重新生成

    def test_reorder(self, store):
        a, b = Rule.create("a"), Rule.create("b")
        store.add(a)
        store.add(b)
        store.reorder([b.id, a.id])
        assert [r.id for r in store.all()] == [b.id, a.id]

    def test_update_rejects_unknown_field(self, store):
        r = store.add(Rule.create("x"))
        with pytest.raises(KeyError):
            store.update(r.id, bogus=1)

    def test_find_rule_returns_match_for_substitution(self, store):
        r = Rule.create("x")
        r.match = Match(type=REGEX, value=r"a\.com/(\w+)/detail")
        store.add(r)
        _, m = store.find_rule("https://a.com/user42/detail")
        assert m is not None and m.group(1) == "user42"

    def test_regex_miss_is_not_false_positive(self, store):
        """回归：正则未命中时 match_url 必须返回 False（不能是 re.search 的 None）。"""
        r = Rule.create("x")
        r.match = Match(type=REGEX, value=r"^https://a\.com/u/\d+$")
        store.add(r)
        rule, m = store.find_rule("https://a.com/other")
        assert rule is None and m is None
        # 命中时才返回 rule + match
        rule, m = store.find_rule("https://a.com/u/42")
        assert rule is not None

    def test_file_body_rule_persists(self, store):
        r = Rule.create("file rule")
        r.action = Action(body_source="file", file_path="/tmp/x.json")
        store.add(r)
        store2 = RuleStore(path=store.path)
        store2.load()
        assert store2.all()[0].action.file_path == "/tmp/x.json"


class TestMethodMatch:
    def test_empty_method_matches_anything(self):
        m = Match(type=CONTAINS, value="/api/")
        assert m.matches_method("GET")
        assert m.matches_method("POST")
        assert m.matches_method("")

    def test_method_exact_case_insensitive(self):
        m = Match(type=CONTAINS, value="/api/", method="post")
        assert m.matches_method("POST")
        assert m.matches_method("post")
        assert m.matches_method("GET") is False

    def test_method_from_dict_normalized_upper(self):
        m = Match.from_dict({"type": "contains", "value": "/x", "method": " get "})
        assert m.method == "GET"

    def test_method_field_roundtrip(self):
        m = Match(type=EXACT, value="https://a.com/", method="OPTIONS")
        assert Match.from_dict(m.to_dict()).method == "OPTIONS"

    def test_old_file_without_method_field(self):
        m = Match.from_dict({"type": "contains", "value": "/x"})
        assert m.method == ""  # 旧 rules.json 无该字段 → 任意方法，行为不变

    def test_find_rule_respects_method(self, store):
        r_get = Rule.create("只 GET")
        r_get.match = Match(type=CONTAINS, value="/api/", method="GET")
        r_get.action = Action(status=200, body="g")
        store.add(r_get)
        rule, _ = store.find_rule("https://a.com/api/x", "POST")
        assert rule is None  # 方法不符
        rule, _ = store.find_rule("https://a.com/api/x", "GET")
        assert rule is not None

    def test_find_rule_any_method_rule_still_hits_without_method_arg(self, store):
        """兼容路径：调用方不传 method 时，任意方法规则照常命中（存量测试/调用不破）。"""
        r = Rule.create("任意")
        r.match = Match(type=CONTAINS, value="/api/")
        store.add(r)
        rule, _ = store.find_rule("https://a.com/api/x")
        assert rule is not None

    def test_find_rule_method_rule_miss_when_caller_omits_method(self, store):
        r = Rule.create("只 POST")
        r.match = Match(type=CONTAINS, value="/api/", method="POST")
        store.add(r)
        rule, _ = store.find_rule("https://a.com/api/x")
        assert rule is None  # "不知道方法"按不匹配处理

    def test_find_rule_first_method_match_wins(self, store):
        r_post = Rule.create("POST 规则")
        r_post.match = Match(type=CONTAINS, value="/api/", method="POST")
        r_post.action = Action(status=201, body="p")
        store.add(r_post)
        r_any = Rule.create("任意规则")
        r_any.match = Match(type=CONTAINS, value="/api/")
        r_any.action = Action(status=202, body="a")
        store.add(r_any)
        rule, _ = store.find_rule("https://a.com/api/x", "POST")
        assert rule.id == r_post.id
        rule, _ = store.find_rule("https://a.com/api/x", "GET")
        assert rule.id == r_any.id


class TestRedirect:
    def test_redirect_url_roundtrip(self):
        a = Action(redirect_url="https://b.com/x")
        d = a.to_dict()
        assert d["redirect_url"] == "https://b.com/x"
        assert Action.from_dict(d).redirect_url == "https://b.com/x"

    def test_redirect_url_default_empty(self):
        assert Action.from_dict({"status": 200}).redirect_url == ""
        assert Action.from_dict({"redirect_url": None}).redirect_url == ""

    def test_rule_with_redirect_persists(self, store):
        r = Rule.create("转发")
        r.match = Match(type=CONTAINS, value="/api/")
        r.action = Action(redirect_url="https://staging.example.com/api/")
        store.add(r)
        store2 = RuleStore(path=store.path)
        store2.load()
        loaded = store2.all()[0]
        assert loaded.action.redirect_url == "https://staging.example.com/api/"
        assert loaded.action.status == 200  # 其他字段保持默认

    def test_update_accepts_redirect_dict(self, store):
        r = store.add(Rule.create("x"))
        updated = store.update(
            r.id,
            action=Action(redirect_url="https://b.com/").to_dict(),
        )
        assert updated.action.redirect_url == "https://b.com/"


class TestProxyLoopGuard:
    def test_points_at_proxy_rejected(self, store):
        """重定向目标指向本代理监听地址 → 拒绝执行（死循环保护）。"""
        from addons.mock import MockAddon
        from mitmproxy.test import tflow

        r = Rule.create("自指")
        r.match = Match(type=CONTAINS, value="/api/")
        r.action = Action(redirect_url="http://127.0.0.1:8080/api/loop")
        store.add(r)
        addon = MockAddon(store, proxy_addr=("127.0.0.1", 8080))
        flow = tflow.tflow()
        flow.request.url = "https://example.com/api/x"
        import asyncio
        asyncio.run(addon.request(flow))
        assert flow.request.pretty_url == "https://example.com/api/x"  # 未被改写
        assert flow.response is not None and flow.response.status_code == 502
        assert "死循环" in (store.get(r.id).error or "")

    def test_points_at_other_host_ok(self, store):
        from addons.mock import MockAddon
        from mitmproxy.test import tflow

        r = Rule.create("正常")
        r.match = Match(type=CONTAINS, value="/api/")
        r.action = Action(redirect_url="http://127.0.0.1:8080/api/loop")
        store.add(r)
        addon = MockAddon(store, proxy_addr=("127.0.0.1", 9999))  # 端口不同
        flow = tflow.tflow()
        flow.request.url = "https://example.com/api/x"
        import asyncio
        asyncio.run(addon.request(flow))
        assert flow.request.pretty_url == "http://127.0.0.1:8080/api/loop"

    def test_localhost_also_guarded(self):
        from addons.mock import MockAddon
        from app.rules import RuleStore

        addon = MockAddon(RuleStore(), proxy_addr=("127.0.0.1", 8080))
        assert addon._points_at_proxy("http://localhost:8080/x")
        assert not addon._points_at_proxy("http://127.0.0.1/x")  # 无端口 = 80 ≠ 8080
        assert not addon._points_at_proxy("http://127.0.0.1:9999/x")
        assert not addon._points_at_proxy("https://example.com:8080/x")  # 域名不同
        assert not addon._points_at_proxy("http://x")  # 无代理地址匹配

    def test_no_proxy_addr_no_guard(self):
        from addons.mock import MockAddon
        from app.rules import RuleStore

        addon = MockAddon(RuleStore())
        assert not addon._points_at_proxy("http://127.0.0.1:8080/x")
