"""弱网限速 + 域名映射（app/network.py、addons/throttle.py、mitmproxy 的 MapRemote）。

分两层：
1. 纯函数层：档位/换算/校验/规则→mitmproxy spec 的逐字断言；
2. 活体层：真代理上验证「延迟真的发生了」与「线上域名真的被转发到本地服务」。
"""

import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from addons.capture import CaptureAddon  # noqa: E402
from addons.throttle import ThrottleAddon  # noqa: E402
from app.network import (  # noqa: E402
    MAP_SPEC_SEP,
    MAX_DELAY_MS,
    THROTTLE_PRESETS,
    MapRule,
    ThrottleConfig,
    build_map_remote_spec,
    build_map_remote_specs,
    describe_rule,
    parse_target,
    preset_labels,
    preset_values,
    rules_from_dicts,
    rules_to_dicts,
    sanitize_int,
)
from app.proxy import ProxyService  # noqa: E402


class TestThrottleConfig:
    def test_off_is_disabled(self):
        cfg = ThrottleConfig()
        assert cfg.preset == "off"
        assert not cfg.enabled
        assert cfg.delay_ms(10_000) == 0.0

    def test_preset_table_shape(self):
        keys = [k for k, _, _, _ in THROTTLE_PRESETS]
        assert keys[0] == "off" and keys[-1] == "custom"
        assert preset_labels()[0] == ("off", "关闭")
        assert preset_values("3g")[2:] == (200, 400)
        assert preset_values("不存在的档位")[0] == "off"
        assert preset_values("custom")[0] == "custom"

    def test_delay_is_latency_plus_transfer_time(self):
        # 400 kbps → 400*1024/8 = 51200 B/s → 51200 字节正好 1 秒
        cfg = ThrottleConfig(preset="3g", latency_ms=200, rate_kbps=400)
        assert cfg.enabled
        assert cfg.delay_ms(0) == 200.0
        assert cfg.delay_ms(51_200) == pytest.approx(1200.0)
        assert cfg.delay_ms(25_600) == pytest.approx(700.0)

    def test_latency_only_when_rate_zero(self):
        cfg = ThrottleConfig(preset="custom", latency_ms=500, rate_kbps=0)
        assert cfg.delay_ms(10_000_000) == 500.0

    def test_rate_only_when_latency_zero(self):
        cfg = ThrottleConfig(preset="custom", latency_ms=0, rate_kbps=1024)
        # 1024 kbps → 131072 B/s
        assert cfg.delay_ms(131_072) == pytest.approx(1000.0)

    def test_delay_capped(self):
        cfg = ThrottleConfig(preset="custom", latency_ms=999_999, rate_kbps=1)
        assert cfg.delay_ms(10_000_000) == float(MAX_DELAY_MS)

    def test_roundtrip_dict(self):
        cfg = ThrottleConfig(preset="custom", latency_ms=333, rate_kbps=777)
        again = ThrottleConfig.from_dict(cfg.to_dict())
        assert (again.preset, again.latency_ms, again.rate_kbps) == ("custom", 333, 777)

    def test_from_dict_unknown_preset_falls_back(self):
        cfg = ThrottleConfig.from_dict({"preset": "5g-very-fast"})
        assert cfg.preset == "off"

    def test_from_dict_preset_wins_over_stale_numbers(self):
        """非自定义档位以档位表为准，避免手改 settings.json 后档位与参数不一致。"""
        cfg = ThrottleConfig.from_dict({"preset": "3g", "latency_ms": 9999, "rate_kbps": 1})
        assert (cfg.latency_ms, cfg.rate_kbps) == (200, 400)

    def test_from_dict_custom_keeps_numbers(self):
        cfg = ThrottleConfig.from_dict({"preset": "custom", "latency_ms": -5, "rate_kbps": "80"})
        assert cfg.preset == "custom"
        assert cfg.latency_ms == 0        # 负数被夹到 0
        assert cfg.rate_kbps == 80

    def test_from_dict_garbage(self):
        assert ThrottleConfig.from_dict(None).preset == "off"
        assert ThrottleConfig.from_dict({"latency_ms": "abc"}).latency_ms == 0

    def test_sanitize_int(self):
        assert sanitize_int(None, 100) == 0
        assert sanitize_int("12", 100) == 12
        assert sanitize_int(-3, 100) == 0
        assert sanitize_int(500, 100) == 100


class TestMapRuleSpec:
    def test_plain_host_is_escaped(self):
        spec = build_map_remote_spec(MapRule("api.prod.com", "127.0.0.1:8080"))
        parts = spec.split(MAP_SPEC_SEP)
        assert parts[0] == ""
        assert parts[1] == r"^https?://api\.prod\.com(?::\d+)?/"
        assert parts[2] == "http://127.0.0.1:8080/"

    def test_only_prefix_is_replaced(self):
        """路径与 query 必须原样保留（正则只吃 scheme+host+端口）。"""
        import re

        spec = build_map_remote_spec(MapRule("api.prod.com", "127.0.0.1:8080"))
        subject, replacement = spec.split(MAP_SPEC_SEP)[1:]
        url = "https://api.prod.com/v2/order?id=7&x=1"
        assert re.sub(subject, replacement, url) == "http://127.0.0.1:8080/v2/order?id=7&x=1"

    def test_regex_source_passthrough(self):
        spec = build_map_remote_spec(MapRule(r"(api|gw)\.prod\.com", "127.0.0.1:8080"))
        assert spec.split(MAP_SPEC_SEP)[1] == r"^https?://(api|gw)\.prod\.com(?::\d+)?/"

    def test_scheme_prefix_in_source_stripped(self):
        spec = build_map_remote_spec(MapRule("https://api.prod.com/", "127.0.0.1:8080"))
        assert spec.split(MAP_SPEC_SEP)[1] == r"^https?://api\.prod\.com(?::\d+)?/"

    def test_target_scheme_respected(self):
        assert parse_target("https://dev.local:8443") == ("https", "dev.local:8443")
        assert parse_target("dev.local:8443") == ("http", "dev.local:8443")
        assert parse_target("127.0.0.1") == ("http", "127.0.0.1")
        spec = build_map_remote_spec(MapRule("a.test", "https://dev.local:8443"))
        assert spec.split(MAP_SPEC_SEP)[2] == "https://dev.local:8443/"

    def test_target_with_path_keeps_netloc_only(self):
        assert parse_target("http://127.0.0.1:9000/prefix") == ("http", "127.0.0.1:9000")

    def test_bad_targets_rejected(self):
        for bad in ("", "   ", "http://", "/only/path", "127.0.0.1:99999"):
            assert parse_target(bad) is None, bad

    def test_disabled_or_incomplete_rule_rejected(self):
        assert build_map_remote_spec(MapRule("a.test", "127.0.0.1:1", enabled=False)) is None
        assert build_map_remote_spec(MapRule("", "127.0.0.1:1")) is None
        assert build_map_remote_spec(MapRule("a.test", "")) is None

    def test_specs_batch_reports_skipped(self):
        rules = [
            MapRule("api.prod.com", "127.0.0.1:8080"),
            MapRule("bad.test", "不是目标"),          # 目标无法解析 → 跳过
            MapRule("gw.prod.com", "127.0.0.1:8081", enabled=False),   # 未启用
        ]
        specs, skipped = build_map_remote_specs(rules)
        assert len(specs) == 1
        assert [r.source for r in skipped] == ["bad.test"]

    def test_specs_empty_when_nothing_usable(self):
        specs, skipped = build_map_remote_specs([MapRule()])
        assert specs == [] and len(skipped) == 1

    def test_bad_regex_reported_not_raised(self):
        specs, skipped = build_map_remote_specs([MapRule("api[.prod.com", "127.0.0.1:1")])
        assert specs == [] and len(skipped) == 1

    def test_rules_dict_roundtrip(self):
        rules = [MapRule("a.test", "127.0.0.1:1"), MapRule("b.test", "127.0.0.1:2", enabled=False)]
        again = rules_from_dicts(rules_to_dicts(rules))
        assert [(r.source, r.target, r.enabled) for r in again] == [
            ("a.test", "127.0.0.1:1", True),
            ("b.test", "127.0.0.1:2", False),
        ]

    def test_rules_from_dicts_skips_junk(self):
        assert rules_from_dicts([None, "x", {"source": "a.test"}]) == [MapRule("a.test", "", True)]

    def test_describe_rule(self):
        assert describe_rule(MapRule("api.prod.com", "127.0.0.1:8080")) == (
            "https?://api.prod.com/* → http://127.0.0.1:8080/*"
        )
        # local 形态：目录路径
        assert describe_rule(MapRule("static.prod.com", "./site")) == (
            "https?://static.prod.com/* → 本地目录 ./site"
        )
        # 两种形态都认不出时，提示里要同时给出两种写法
        unknown = describe_rule(MapRule("a.test", "??"))
        assert "无法识别" in unknown and "127.0.0.1:8080" in unknown and "/path/to/dir" in unknown
        assert "未填写" in describe_rule(MapRule("", "127.0.0.1:1"))


# ====================================================================== 活体层


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/big"):
            body = b"x" * 4096
        else:
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
    server = HTTPServer(("127.0.0.1", 18911), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _get_via_proxy(port: int, url: str, timeout: float = 20.0):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": f"127.0.0.1:{port}"})
    )
    try:
        with opener.open(url, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class TestThrottleLive:
    def test_latency_actually_delays_response(self, upstream):
        throttle = ThrottleAddon(ThrottleConfig(preset="custom", latency_ms=600, rate_kbps=0))
        proxy = ProxyService(host="127.0.0.1", port=18091, addons=[throttle])
        proxy.start()
        try:
            start = time.monotonic()
            status, body = _get_via_proxy(18091, "http://127.0.0.1:18911/api/real")
            elapsed_ms = (time.monotonic() - start) * 1000
            assert status == 200 and b'"from":"upstream"' in body
            assert elapsed_ms >= 550, f"延迟没生效: {elapsed_ms:.0f}ms"
            assert throttle.applied == 1
        finally:
            proxy.stop()

    def test_disabled_does_not_delay(self, upstream):
        throttle = ThrottleAddon(ThrottleConfig(preset="off"))
        proxy = ProxyService(host="127.0.0.1", port=18092, addons=[throttle])
        proxy.start()
        try:
            start = time.monotonic()
            _get_via_proxy(18092, "http://127.0.0.1:18911/api/real")
            elapsed_ms = (time.monotonic() - start) * 1000
            assert elapsed_ms < 500, f"关闭档位不该有延迟: {elapsed_ms:.0f}ms"
            assert throttle.applied == 0
        finally:
            proxy.stop()

    def test_config_can_be_changed_at_runtime(self, upstream):
        throttle = ThrottleAddon(ThrottleConfig(preset="off"))
        proxy = ProxyService(host="127.0.0.1", port=18093, addons=[throttle])
        proxy.start()
        try:
            # 运行中换成 500ms
            throttle.set_config(ThrottleConfig(preset="custom", latency_ms=500, rate_kbps=0))
            start = time.monotonic()
            _get_via_proxy(18093, "http://127.0.0.1:18911/api/real")
            assert (time.monotonic() - start) * 1000 >= 450
            # 再关掉
            throttle.set_config(ThrottleConfig(preset="off"))
            start = time.monotonic()
            _get_via_proxy(18093, "http://127.0.0.1:18911/api/real")
            assert (time.monotonic() - start) * 1000 < 500
        finally:
            proxy.stop()

    def test_bandwidth_delay_scales_with_body(self, upstream):
        """32 kbps → 4096 B/s，4KB 响应应额外等约 1 秒。"""
        throttle = ThrottleAddon(ThrottleConfig(preset="custom", latency_ms=0, rate_kbps=32))
        proxy = ProxyService(host="127.0.0.1", port=18094, addons=[throttle])
        proxy.start()
        try:
            start = time.monotonic()
            status, body = _get_via_proxy(18094, "http://127.0.0.1:18911/big")
            elapsed_ms = (time.monotonic() - start) * 1000
            assert status == 200 and len(body) == 4096
            assert elapsed_ms >= 900, f"按体积折算的延迟没生效: {elapsed_ms:.0f}ms"
            assert throttle.applied == 1
        finally:
            proxy.stop()


class TestMapRemoteLive:
    def test_fake_domain_routed_to_local(self, upstream):
        """核心承诺：请求 api.prod.com，实际落到本地 127.0.0.1:18911。"""
        capture = CaptureAddon()
        specs, skipped = build_map_remote_specs(
            [MapRule("api.prod.com", "127.0.0.1:18911")]
        )
        assert specs and not skipped
        proxy = ProxyService(
            host="127.0.0.1", port=18095, addons=[capture], options={"map_remote": specs}
        )
        proxy.start()
        try:
            status, body = _get_via_proxy(18095, "http://api.prod.com/v1/order?id=7")
            assert status == 200
            assert b'"from":"upstream"' in body

            deadline = time.time() + 5
            while time.time() < deadline and not capture.flows:
                time.sleep(0.05)
            flow = next(iter(capture.flows.values()))
            assert flow.request.pretty_host == "127.0.0.1"      # 已改写到本地
            assert flow.request.path == "/v1/order?id=7"         # 路径与 query 保留
        finally:
            proxy.stop()

    def test_unmatched_domain_passes_through_to_real_host(self, upstream):
        """没配映射的域名不受影响（这里让它命中本地上游以证明没被改写）。"""
        capture = CaptureAddon()
        proxy = ProxyService(
            host="127.0.0.1",
            port=18096,
            addons=[capture],
            options={"map_remote": [MAP_SPEC_SEP + r"^https?://other\.test(?::\d+)?/" + MAP_SPEC_SEP + "http://127.0.0.1:1/"]},
        )
        proxy.start()
        try:
            status, _ = _get_via_proxy(18096, "http://127.0.0.1:18911/api/real")
            assert status == 200
        finally:
            proxy.stop()

    def test_no_mapping_configured(self, upstream):
        proxy = ProxyService(host="127.0.0.1", port=18097, options={})
        proxy.start()
        try:
            status, body = _get_via_proxy(18097, "http://127.0.0.1:18911/api/real")
            assert status == 200 and b'"from":"upstream"' in body
        finally:
            proxy.stop()

    def test_option_can_be_updated_at_runtime(self, upstream):
        capture = CaptureAddon()
        proxy = ProxyService(host="127.0.0.1", port=18098, addons=[capture])
        proxy.start()
        try:
            # 先不加映射：请求本地地址本来就能通
            assert _get_via_proxy(18098, "http://127.0.0.1:18911/api/real")[0] == 200
            # 热更新加上映射
            specs, _ = build_map_remote_specs([MapRule("api.prod.com", "127.0.0.1:18911")])
            assert proxy.update_options(map_remote=specs) is True
            deadline = time.time() + 3
            while time.time() < deadline and not capture.flows:
                time.sleep(0.05)

            status, body = _get_via_proxy(18098, "http://api.prod.com/v1/x")
            assert status == 200 and b'"from":"upstream"' in body
            deadline = time.time() + 5
            while time.time() < deadline and len(capture.flows) < 2:
                time.sleep(0.05)
            hosts = {f.request.pretty_host for f in capture.flows.values()}
            assert "127.0.0.1" in hosts
        finally:
            proxy.stop()

    def test_update_options_before_start_is_remembered(self):
        proxy = ProxyService(host="127.0.0.1", port=18099)
        assert proxy.update_options(map_remote=["x"]) is False      # 未运行 → 只记录
        assert proxy._options["map_remote"] == ["x"]
