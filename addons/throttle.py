"""弱网模拟 addon：在响应发回客户端前按配置等待（延迟 + 按体积折算的传输时间）。

为什么不在 request 钩子里等：request 阶段响应还没产生，拿不到体积；
放在 response 钩子里 await 才是"这条响应要慢多久才到客户端"。

实现方式是 `async def response` + `asyncio.sleep`——mitmproxy 的 addon 管理器会
await 协程钩子，且每个 flow 在各自的任务里，所以等这一条不会卡住其他连接。

配置对象是**整体替换**的（UI 线程 set_config 赋值一个新对象），不原地改字段，
避免跨线程读到半更新的状态。
"""

from __future__ import annotations

import asyncio
import logging

from app.network import MAX_DELAY_MS, ThrottleConfig

log = logging.getLogger(__name__)


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

    # ------------------------------------------------------------ mitmproxy hook

    async def response(self, flow) -> None:
        cfg = self._config
        if not cfg.enabled:
            return
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
        self.applied += 1

    def done(self) -> None:
        pass
