"""弱网模拟 addon：在响应发回客户端前按配置等待（延迟 + 按体积折算的传输时间）。

延迟要挂在两个钩子上：
- `response`：作用于**真实上游**响应（请求发到服务器、服务器回包后）。
- `request`：作用于被 mock / map-local 等**前置 addon 在 request 阶段直接注入**
  的响应。这类响应不会走到 response 钩子（或走到时语义已不对），所以在
  request 钩子里、且必须等前置 addon 先造好 response 之后（注册顺序保证：
  throttle 排在所有会造响应的 addon 之后）再补一次延迟。

实现方式是 `async def` 钩子 + `asyncio.sleep`——mitmproxy 的 addon 管理器会
await 协程钩子，且每个 flow 在各自的任务里，所以等这一条不会卡住其他连接。
用 flow.metadata 去重，避免 request 与 response 钩子对同一 flow 重复加延迟。

配置对象是**整体替换**的（UI 线程 set_config 赋值一个新对象），不原地改字段，
避免跨线程读到半更新的状态。
"""

from __future__ import annotations

import asyncio
import logging

from app.network import MAX_DELAY_MS, ThrottleConfig

log = logging.getLogger(__name__)

_META_KEY = "mproxy_throttled"   # 标记该 flow 已施加过延迟，防 request/response 重复


class ThrottleAddon:
    def __init__(self, config: ThrottleConfig | None = None):
        self._config = config or ThrottleConfig()
        self.applied = 0            # 已施加延迟的响应数（便于冒烟/自检观察）

    # ------------------------------------------------------------ 配置

    def set_config(self, config: ThrottleConfig) -> None:
        self._config = config

    @property
    def config(self) -> ThrottleConfig:
        return self._config

    # ------------------------------------------------------------ 核心延迟逻辑

    async def _maybe_delay(self, flow) -> None:
        cfg = self._config
        if not cfg.enabled:
            return
        if getattr(flow, "metadata", {}).get(_META_KEY):
            return  # 同一 flow 已延迟过（可能来自另一个钩子）
        res = getattr(flow, "response", None)
        if res is None:
            return
        try:
            size = len(res.raw_content or b"")
        except Exception:
            size = 0
        delay_ms = cfg.delay_ms(size)
        if delay_ms <= 0:
            return
        # 上界由 MAX_DELAY_MS 兜住（见 app/network.py），这里再保险一次
        await asyncio.sleep(min(delay_ms, float(MAX_DELAY_MS)) / 1000.0)
        try:
            flow.metadata[_META_KEY] = True
        except Exception:
            pass
        self.applied += 1

    # ------------------------------------------------------------ mitmproxy hook

    async def request(self, flow) -> None:
        # 覆盖被 mock / map-local 在 request 阶段注入的响应：它们不会走到
        # response 钩子，必须在这里补延迟。注册顺序保证走到此时响应已造好。
        await self._maybe_delay(flow)

    async def response(self, flow) -> None:
        await self._maybe_delay(flow)

    def done(self) -> None:
        pass
