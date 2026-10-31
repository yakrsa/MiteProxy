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
    add_domains,
    host_matches,
    normalize_domain,
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
            FilterConfig(blacklist=["example.com"], enabled=True)
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
            FilterConfig(whitelist=["example.com"], enabled=True,
                         active_list="whitelist")
        )
        assert model.rowCount() == 1

    def test_disabled_switch_shows_all(self, qapp):
        """启用开关关掉 → 两个列表都写满也不过问。"""
        model, _ = _make_model(
            [
                _row(id="a", host="api.example.com"),
                _row(id="b", host="cdn.other.com"),
            ]
        )
        model.set_filter_config(
            FilterConfig(blacklist=["example.com"], whitelist=["other.com"])
        )
        assert model.rowCount() == 2

    def test_whitelist_empty_shows_all(self, qapp):
        """空白名单不过滤：防止启用后把全部流量藏起来。"""
        model, _ = _make_model([_row(id="a"), _row(id="b")])
        model.set_filter_config(FilterConfig(whitelist=[], enabled=True,
                                             active_list="whitelist"))
        assert model.rowCount() == 2

    def test_multiple_entries(self, qapp):
        model, _ = _make_model(
            [
                _row(id="a", host="api.example.com"),
                _row(id="b", host="cdn.other.com"),
                _row(id="c", host="third.net"),
            ]
        )
        model.set_filter_config(
            FilterConfig(whitelist=["example.com", "other.com"], enabled=True,
                         active_list="whitelist")
        )
        assert model.rowCount() == 2

    def test_domain_entry_matches_subdomain_only(self, qapp):
        """带点条目 = 域名语义：命中子域，不命中同后缀无关域名。"""
        model, _ = _make_model(
            [
                _row(id="a", host="example.com"),
                _row(id="b", host="api.example.com"),
                _row(id="c", host="notexample.com"),
                _row(id="d", host="example.com.evil.net"),
            ]
        )
        model.set_filter_config(
            FilterConfig(blacklist=["example.com"], enabled=True)
        )
        assert model.rowCount() == 2  # 只藏 a/b，c/d 保留

    def test_keyword_entry_keeps_substring_semantics(self, qapp):
        """不带点条目 = 老的关键字语义（子串）。"""
        model, _ = _make_model(
            [
                _row(id="a", host="www.google.com"),
                _row(id="b", host="api.example.com"),
            ]
        )
        model.set_filter_config(FilterConfig(blacklist=["google"], enabled=True))
        assert model.rowCount() == 1

    def test_only_active_list_consulted(self, qapp):
        """只启用黑名单时，白名单内容不参与判定。"""
        model, _ = _make_model(
            [
                _row(id="a", host="api.example.com"),
                _row(id="b", host="cdn.other.com"),
            ]
        )
        model.set_filter_config(
            FilterConfig(whitelist=["example.com"], enabled=True,
                         active_list="blacklist")
        )
        assert model.rowCount() == 2

    def test_blacklist_wildcard_hides_subdomains(self, qapp):
        """黑名单写 *.apple.com，把所有 apple.com 子域（含根域）藏起来。"""
        model, _ = _make_model(
            [
                _row(id="a", host="ocsp2.apple.com"),
                _row(id="b", host="api.apple.com"),
                _row(id="c", host="apple.com"),
                _row(id="d", host="example.com"),
            ]
        )
        model.set_filter_config(
            FilterConfig(blacklist=["*.apple.com"], enabled=True)
        )
        assert model.rowCount() == 1  # 只剩 example.com

    def test_whitelist_wildcard_shows_only_match(self, qapp):
        """白名单写 *.apple.*，只显示 apple 任意 TLD 的子域。"""
        model, _ = _make_model(
            [
                _row(id="a", host="ocsp2.apple.com"),
                _row(id="b", host="ocsp2.apple.org"),
                _row(id="c", host="example.com"),
            ]
        )
        model.set_filter_config(
            FilterConfig(whitelist=["*.apple.*"], enabled=True,
                         active_list="whitelist")
        )
        assert model.rowCount() == 2


class TestDomainHelpers:
    def test_host_matches_subdomain(self):
        assert host_matches("api.example.com", "example.com")
        assert host_matches("example.com", "example.com")
        assert not host_matches("notexample.com", "example.com")
        assert not host_matches("example.com.evil.net", "example.com")

    def test_host_matches_case_and_trailing_dot(self):
        assert host_matches("API.Example.COM.", "example.com")
        assert host_matches("example.com", "EXAMPLE.com.")

    def test_host_matches_keyword(self):
        assert host_matches("www.google.com", "google")
        assert not host_matches("example.com", "google")

    def test_host_matches_wildcard_subdomains(self):
        """*.apple.com 命中所有 apple.com 子域，并额外涵盖根域。"""
        assert host_matches("ocsp2.apple.com", "*.apple.com")
        assert host_matches("api.foo.apple.com", "*.apple.com")
        assert host_matches("apple.com", "*.apple.com")  # 根域也命中
        assert not host_matches("api.apple.com.evil.net", "*.apple.com")
        assert not host_matches("notapple.com", "*.apple.com")

    def test_host_matches_wildcard_variants(self):
        """api.*.com / *.apple.* / *foo.com 等通配符整串匹配。"""
        assert host_matches("api.foo.com", "api.*.com")
        assert host_matches("ocsp2.apple.org", "*.apple.*")
        assert host_matches("evilfoo.com", "*foo.com")
        assert host_matches("foo.com", "*foo.com")
        assert not host_matches("myapi.foo.net", "api.*.com")

    def test_normalize_domain(self):
        assert normalize_domain("  Example.com.  ") == "example.com"
        assert normalize_domain("") == ""

    def test_add_domains_incremental_dedup(self):
        out = add_domains(["a.test"], ["b.test", "A.TEST", " ", "c.test."])
        assert out == ["a.test", "b.test", "c.test"]

    def test_add_domains_empty_returns_copy(self):
        assert add_domains([], []) == []


class TestFilterConfigPersistence:
    def test_round_trip(self):
        cfg = FilterConfig(
            blacklist=["a.test"], whitelist=["b.test"], enabled=True,
            active_list="whitelist", hide_connect=True, hide_image=True,
        )
        restored = FilterConfig.from_dict(cfg.to_dict())
        assert restored.blacklist == ["a.test"]
        assert restored.whitelist == ["b.test"]
        assert restored.enabled is True
        assert restored.active_list == "whitelist"
        assert restored.hide_connect is True
        assert restored.hide_image is True

    def test_legacy_migration_blacklist(self):
        """旧配置 host_mode=blacklist + host_keywords → 落入黑名单并启用。"""
        cfg = FilterConfig.from_dict(
            {"host_mode": "blacklist", "host_keywords": ["a.test"]}
        )
        assert cfg.blacklist == ["a.test"]
        assert cfg.whitelist == []
        assert cfg.enabled is True
        assert cfg.active_list == "blacklist"

    def test_legacy_migration_whitelist(self):
        cfg = FilterConfig.from_dict(
            {"host_mode": "whitelist", "host_keywords": ["a.test"]}
        )
        assert cfg.whitelist == ["a.test"]
        assert cfg.blacklist == []
        assert cfg.active_list == "whitelist"

    def test_legacy_empty_keywords_not_enabled(self):
        cfg = FilterConfig.from_dict({"host_mode": "blacklist", "host_keywords": []})
        assert cfg.enabled is False

    def test_legacy_bad_mode_falls_back(self):
        cfg = FilterConfig.from_dict({"host_mode": "nope", "host_keywords": ["x"]})
        assert cfg.active_list == "blacklist"
        assert cfg.blacklist == ["x"]

    def test_new_schema_takes_priority(self):
        cfg = FilterConfig.from_dict(
            {"blacklist": ["a.test"], "host_keywords": ["ignored"]}
        )
        assert cfg.blacklist == ["a.test"]

    def test_is_active_requires_enabled_and_entries(self):
        assert FilterConfig(enabled=True, blacklist=["a.test"]).is_active()
        assert not FilterConfig(enabled=True, blacklist=[]).is_active()
        assert not FilterConfig(enabled=False, blacklist=["a.test"]).is_active()

    def test_active_entries_follows_active_list(self):
        cfg = FilterConfig(blacklist=["a"], whitelist=["b"])
        assert cfg.active_entries == ["a"]
        cfg.active_list = "whitelist"
        assert cfg.active_entries == ["b"]


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
            FilterConfig(whitelist=["example.com"], enabled=True,
                         active_list="whitelist")
        )
        cfg = SearchConfig()
        cfg.text = "user"
        model.set_search_config(cfg)
        assert model.rowCount() == 1  # 只有 a 同时满足两个条件
