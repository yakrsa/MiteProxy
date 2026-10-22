"""断点调试 addon：在请求发出前 / 响应返回前暂停会话（Fiddler 的 Breakpoint）。

机制走 mitmproxy 原生拦截：request / response 钩子里调 ``flow.intercept()``，
代理就会挂住这条 flow，直到 ``flow.resume()``（放行）或 ``flow.kill()``（中止）。
钩子里**不阻塞**——intercepted 只是打标记，真正的等待由 mitmproxy 内核在钩子
跑完后 await ``flow.wait_for_resume()`` 完成，所以挂在断点上时整个代理线程
不会被卡死，其它会话照常走。

⚠ 放行必须从 UI 线程经 ``ProxyService`` 的 ``call_soon_threadsafe`` 投递：
``Flow.resume()`` 内部是 ``asyncio.Event.set()``，跨线程直接调不安全
（参照 ``app/proxy.py::replay_flow`` 的同样处理）。

配置是活对象（``Settings.breakpoint``）：用户在界面上开关断点即时生效，
不必重启代理。
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class BreakpointAddon:
    """按阶段 + URL 关键词暂停会话，交给 UI 改完再放行。"""

    name = "miteproxy.breakpoint"

    def __init__(self, config, on_intercept=None) -> None:
        #: 活的 BreakpointConfig（Settings.breakpoint），每次钩子现读
        self.config = config
        #: 拦截回调 (flow, phase) —— 跑在 asyncio 线程，必须走 pyqtSignal
        self.on_intercept = on_intercept
        #: 正在断点中的 flow id，避免同一条被重复上报
        self.paused: set[str] = set()

    # ------------------------------------------------------------ 判定

    def _should_pause(self, flow, phase: str) -> bool:
        cfg = self.config
        if not getattr(cfg, "enabled", False):
            return False
        if phase == "request" and not getattr(cfg, "on_request", True):
            return False
        if phase == "response" and not getattr(cfg, "on_response", False):
            return False
        # 重放的请求不拦（用户主动发的，再拦一次很烦）
        if getattr(flow, "is_replay", False):
            return False
        url = getattr(getattr(flow, "request", None), "pretty_url", "") or ""
        return cfg.matches(url)

    # ------------------------------------------------------------ 钩子

    def request(self, flow) -> None:
        if self._should_pause(flow, "request"):
            self._pause(flow, "request")

    def response(self, flow) -> None:
        if self._should_pause(flow, "response"):
            self._pause(flow, "response")

    # ------------------------------------------------------------ 内部

    def _pause(self, flow, phase: str) -> None:
        fid = getattr(flow, "id", None) or str(id(flow))
        if fid in self.paused:
            return
        self.paused.add(fid)
        try:
            flow.intercept()
        except Exception as e:          # 拦不住也不能拖垮整条请求
            log.warning("断点拦截失败：%s", e)
            self.paused.discard(fid)
            return
        log.info("断点暂停（%s）：%s", phase,
                 getattr(getattr(flow, "request", None), "pretty_url", ""))
        if self.on_intercept is not None:
            # 失败只记日志：UI 收不到就没人放行，但至少不打崩代理线程
            try:
                self.on_intercept(flow, phase)
            except Exception as e:
                log.warning("断点回调失败：%s", e)

    def forget(self, flow) -> None:
        """放行/中止后清掉标记（同一条会话再次经过时可重新拦截）。"""
        fid = getattr(flow, "id", None) or str(id(flow))
        self.paused.discard(fid)
