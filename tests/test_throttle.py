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
    """把 asyncio.sleep 换成只记录毫秒数、不真睡的桩，便于快速断言延迟。"""
    recorded = []

    async def _sleep(seconds):
        recorded.append(seconds * 1000.0)

    monkeypatch.setattr(asyncio, "sleep", _sleep)
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
