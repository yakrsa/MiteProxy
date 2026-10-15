"""弱网模拟 addon 的单元测试（不依赖真实 mitmproxy 运行）。

覆盖：
- 关闭时不延迟
- request 钩子对"被 mock/map-local 注入的响应"生效（用户最常踩的点：开启弱网
  但 mock 出来的接口秒回）
- response 钩子对真实上游响应生效
- metadata 去重：同一 flow 不会在 request 与 response 钩子里被加两次延迟
"""

import asyncio

import pytest

from addons.throttle import ThrottleAddon
from app.network import ThrottleConfig


class _FakeResponse:
    def __init__(self, raw):
        self.raw_content = raw


class _FakeFlow:
    def __init__(self, response=None):
        self.response = response
        self.metadata = {}


@pytest.fixture
def fake_sleep(monkeypatch):
    """把 asyncio.sleep 换成只记录毫秒数、不真睡的桩，便于快速断言延迟。

    同时给 throttle 用的 time.monotonic 配一个跟随 sleep 前进的假时钟，
    这样"实际延迟毫秒数"（throttle 写进 metadata 的值）才能被断言。
    """
    recorded = []
    clock = {"t": 100.0}

    async def _sleep(seconds):
        recorded.append(seconds * 1000.0)
        clock["t"] += seconds

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    monkeypatch.setattr("addons.throttle.time.monotonic", lambda: clock["t"])
    return recorded


def _cfg(preset="weak", latency=2000, rate=50):
    return ThrottleConfig(preset=preset, latency_ms=latency, rate_kbps=rate)


def test_disabled_no_delay(fake_sleep):
    addon = ThrottleAddon(_cfg(preset="off"))
    flow = _FakeFlow(_FakeResponse(b"x" * 100))

    async def _r():
        await addon.request(flow)
        await addon.response(flow)

    asyncio.run(_r())
    assert fake_sleep == []
    assert addon.applied == 0


def test_request_hook_delays_injected_response(fake_sleep):
    """mock/map-local 在 request 阶段注入的响应，必须被弱网延迟。"""
    addon = ThrottleAddon(_cfg(latency=2000, rate=0))
    flow = _FakeFlow(_FakeResponse(b"hi"))

    async def _r():
        await addon.request(flow)

    asyncio.run(_r())
    assert fake_sleep == [2000.0]
    assert addon.applied == 1
    assert flow.metadata.get("mproxy_throttled") is True


def test_response_hook_delays_real_response(fake_sleep):
    """真实上游响应在 response 钩子被延迟。"""
    addon = ThrottleAddon(_cfg(latency=2000, rate=0))
    flow = _FakeFlow(_FakeResponse(b"hi"))

    async def _r():
        await addon.response(flow)

    asyncio.run(_r())
    assert fake_sleep == [2000.0]
    assert addon.applied == 1


def test_no_double_delay_on_same_flow(fake_sleep):
    """request 已延迟过的 flow，response 钩子不应再延迟。"""
    addon = ThrottleAddon(_cfg(latency=2000, rate=0))
    flow = _FakeFlow(_FakeResponse(b"hi"))

    async def _r():
        await addon.request(flow)
        await addon.response(flow)

    asyncio.run(_r())
    assert fake_sleep == [2000.0]
    assert addon.applied == 1


def test_rate_adds_transfer_time(fake_sleep):
    """50 kbps 下 50 KiB 响应应叠加约 8192ms 传输时间（50*1024/ (50*1024/8)*1000）。"""
    addon = ThrottleAddon(_cfg(latency=100, rate=50))
    flow = _FakeFlow(_FakeResponse(b"x" * (50 * 1024)))

    async def _r():
        await addon.request(flow)

    asyncio.run(_r())
    assert len(fake_sleep) == 1
    assert fake_sleep[0] > 8000.0  # 100ms 固定 + ~8192ms 传输


def test_no_response_no_delay(fake_sleep):
    addon = ThrottleAddon(_cfg(latency=2000, rate=0))
    flow = _FakeFlow(None)  # request 阶段还没有响应（真实流程）

    async def _r():
        await addon.request(flow)

    asyncio.run(_r())
    assert fake_sleep == []  # request 钩子不延迟；延迟留给后续 response 钩子


# ------------------------------------------------------------ 弱网可见性
# 用户反馈：启用了网络延迟体验不明显——延迟要能体现在流量列表的耗时里，
# 且流量行要有「弱网Xms」标记（capture.summarize 读 metadata 里的实际延迟）


def test_metadata_records_actual_delay_ms(fake_sleep):
    """延迟过的 flow 要把实际毫秒数写进 metadata（capture 计入耗时用）。"""
    addon = ThrottleAddon(_cfg(latency=1500, rate=0))
    flow = _FakeFlow(_FakeResponse(b"hi"))

    async def _r():
        await addon.request(flow)

    asyncio.run(_r())
    assert flow.metadata.get("mproxy_throttle_ms", 0) >= 0
    assert flow.metadata["mproxy_throttle_ms"] == pytest.approx(1500.0, abs=200.0)


def test_no_delay_no_metadata(fake_sleep):
    """没被延迟的 flow 不写 throttle_ms（避免 UI 误标弱网）。"""
    addon = ThrottleAddon(_cfg(preset="off"))
    flow = _FakeFlow(_FakeResponse(b"hi"))

    async def _r():
        await addon.request(flow)

    asyncio.run(_r())
    assert "mproxy_throttle_ms" not in flow.metadata


def test_summarize_duration_includes_throttle_ms():
    """真实上游响应：耗时 = timestamp_end - start + 弱网实际延迟。"""
    import time as _time

    from addons.capture import CaptureAddon

    class _Req:
        method = "GET"
        scheme = "http"
        pretty_host = "x.test"
        pretty_url = "http://x.test/a"
        path = "/a"
        raw_content = b""
        timestamp_start = 1000.0

    class _Res:
        status_code = 200
        timestamp_end = 1000.5  # 上游耗时 500ms（不含弱网）
        raw_content = b"ok"
        headers = {}

    class _Flow:
        id = "cap1"
        request = _Req()
        response = _Res()
        websocket = None
        server_conn = None
        metadata = {"mproxy_throttled": True, "mproxy_throttle_ms": 800.0}
        marked = ""
        comment = ""
        is_replay = False

    s = CaptureAddon.summarize(_Flow())
    assert s["duration_ms"] == pytest.approx(1300.0, abs=1.0)
    assert s["throttle_ms"] == pytest.approx(800.0, abs=0.1)


def test_summarize_mocked_response_duration_uses_now():
    """mock 注入的响应没有 timestamp_end：耗时按当前时间算（此时弱网/mock
    延迟已睡完），且不能再叠加 throttle_ms（否则重复计一次）。"""
    import time as _time

    from addons.capture import CaptureAddon

    class _Req:
        method = "GET"
        scheme = "http"
        pretty_host = "x.test"
        pretty_url = "http://x.test/a"
        path = "/a"
        raw_content = b""
        timestamp_start = _time.time() - 2.0  # 2 秒前发起（含 mock+弱网睡眠）

    class _Res:
        status_code = 200
        timestamp_end = 0.0  # 注入的响应没有结束时间戳
        raw_content = b"ok"
        headers = {}

    class _Flow:
        id = "cap2"
        request = _Req()
        response = _Res()
        websocket = None
        server_conn = None
        metadata = {"mproxy_throttled": True, "mproxy_throttle_ms": 1000.0}
        marked = ""
        comment = ""
        is_replay = False

    s = CaptureAddon.summarize(_Flow())
    assert s["duration_ms"] == pytest.approx(2000.0, abs=300.0)
    assert s["duration_ms"] < 4000.0  # 没有叠加 throttle_ms


def test_main_window_throttle_before_capture():
    """capture 排在 throttle 之后才能读到延迟 metadata（顺序回归防护）。"""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent / "app" / "ui" / "main_window.py"
    ).read_text(encoding="utf-8")
    order_line = [l for l in src.splitlines() if "addons=[self." in l]
    assert order_line, "找不到 addon 注册行"
    line = order_line[0]
    assert line.index("self.throttle") < line.index("self.capture"), (
        f"throttle 必须排在 capture 之前: {line.strip()}"
    )
    assert line.index("self.mock") < line.index("self.throttle"), (
        f"mock 必须排在 throttle 之前: {line.strip()}"
    )
    assert line.index("self.maplocal") < line.index("self.throttle"), (
        f"maplocal 必须排在 throttle 之前: {line.strip()}"
    )
