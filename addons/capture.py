"""捕获 addon：response hook 收 flow，推送摘要给 UI（见 DESIGN.md 2.4 / 3.2）。

注意：本类的回调运行在 mitmproxy 的 asyncio 线程里，Qt 侧必须用
信号（跨线程队列连接）接收，不能在回调里直接碰控件。
"""

from __future__ import annotations

import ipaddress
import logging
import time
from typing import Callable, Optional

log = logging.getLogger(__name__)

MAX_FLOWS = 5000  # 默认保留条数（UI 可调，见 app/settings.FLOW_LIMIT_CHOICES）
BODY_INDEX_LIMIT = 512 * 1024  # body 索引/预览上限 512KB（见 3.2.2 大 body 策略）


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def extract_server_ip(flow) -> str:
    """服务端 IP（列表「服务器 IP」列）。

    优先 `server_conn.peername`——这是 mitmproxy 实际连上的对端，一定是
    已解析的 IP；退化用 `server_conn.address`，但它可能是域名（未建连时
    原样保留主机名），只在形如 IP 时采用。CONNECT 隧道请求、以及被 mock
    直接短路（从未连上游）的请求都取不到，返回空串由 UI 显示 `-`。
    """
    try:
        conn = getattr(flow, "server_conn", None)
    except Exception:
        return ""
    for attr in ("peername", "address"):
        try:
            addr = getattr(conn, attr, None)
        except Exception:
            continue
        if isinstance(addr, (tuple, list)) and addr:
            candidate = str(addr[0])
        else:
            candidate = str(addr or "")
        if candidate and _is_ip(candidate):
            return candidate
    return ""


class CaptureAddon:
    def __init__(
        self,
        on_flow: Optional[Callable[[dict], None]] = None,
        max_flows: int = MAX_FLOWS,
        on_update: Optional[Callable[[dict], None]] = None,
    ):
        self.flows: dict[str, object] = {}  # flow.id -> flow 对象（UI 按 id 回查）
        self._on_flow = on_flow
        self._on_update = on_update
        self._max_flows = max_flows

    # ------------------------------------------------------------ mitmproxy hook

    def response(self, flow) -> None:
        self.flows[flow.id] = flow
        self._evict()
        if self._on_flow is not None:
            try:
                self._on_flow(self.summarize(flow))
            except Exception:
                log.exception("flow 回调异常")

    def websocket_message(self, flow) -> None:
        """WebSocket 消息到达（DESIGN 3.9）。

        mitmproxy 12 没有 `websocket_start` 钩子：握手走 `response`（101），
        `flow.websocket` 在调用 `response` 之前就已挂上，所以首行由 `response`
        产出，之后每条消息在这里**增量更新同一行**。
        """
        self.flows.setdefault(flow.id, flow)
        self._emit_update(flow)

    def websocket_end(self, flow) -> None:
        """连接关闭：补上关闭码与最终耗时。"""
        self.flows.setdefault(flow.id, flow)
        self._emit_update(flow)

    def _emit_update(self, flow) -> None:
        if self._on_update is None:
            return
        try:
            self._on_update(self.summarize(flow))
        except Exception:
            log.exception("会话更新回调异常")

    # ------------------------------------------------------------ 摘要

    @staticmethod
    def summarize(flow) -> dict:
        req = flow.request
        res = flow.response
        ws = getattr(flow, "websocket", None)
        duration_ms = 0.0
        ws_messages = 0
        ws_closed = False
        # 弱网延迟（addons/throttle.py 写入 metadata 的实际睡眠毫秒数）
        try:
            throttle_ms = float(
                (getattr(flow, "metadata", None) or {}).get("mproxy_throttle_ms") or 0
            )
        except (TypeError, ValueError):
            throttle_ms = 0.0

        if ws is not None:
            messages = list(getattr(ws, "messages", None) or [])
            ws_messages = len(messages)
            ws_closed = bool(getattr(ws, "timestamp_end", None))
            # WS 的"大小"用消息体总和：101 响应本身没有 body，
            # 用响应长度的话这一列永远是 0，看不出连接传了多少数据
            size = sum(len(getattr(m, "content", b"") or b"") for m in messages)
            end = getattr(ws, "timestamp_end", None) or time.time()
            if req.timestamp_start:
                duration_ms = (end - req.timestamp_start) * 1000
        else:
            try:
                if res is not None and req.timestamp_start:
                    if res.timestamp_end:
                        # 上游真实响应：timestamp_end 在钩子执行前就定死了，
                        # 弱网延迟不在其中，单独加上
                        duration_ms = (
                            (res.timestamp_end - req.timestamp_start) * 1000
                            + throttle_ms
                        )
                    else:
                        # mock / map-local 在 request 阶段注入的响应没有
                        # timestamp_end；走到这里时 mock 延迟与弱网延迟都
                        # 已睡完，当前时间就是真实的结束时刻（自然含延迟，
                        # 不能再叠加 throttle_ms，否则重复计一次）
                        duration_ms = (time.time() - req.timestamp_start) * 1000
            except Exception:
                pass
            # raw_content 在流式响应期间为 None（mitmproxy 文档明确说明），
            # len(None) 抛 TypeError 会让整个 summarize 失败、该行永远进不了列表
            size = len(res.raw_content or b"") if res is not None else 0

        status = res.status_code if res is not None else 0
        content_type = ""
        if res is not None:
            content_type = res.headers.get("content-type", "") or ""
        # 请求体大小（v1.15，列表单独一列）；raw_content 为 None 时按 0
        try:
            req_size = len(req.raw_content or b"")
        except Exception:
            req_size = 0
        return {
            "id": flow.id,
            "method": req.method,
            "scheme": req.scheme,
            "host": req.pretty_host,
            "server_ip": extract_server_ip(flow),
            "path": req.path,
            "url": req.pretty_url,
            "status": status,
            "size": size,
            "req_size": req_size,
            "duration_ms": round(duration_ms, 1),
            "throttle_ms": round(throttle_ms, 1),
            "content_type": content_type,
            "marked": getattr(flow, "marked", "") or "",
            "is_replay": bool(getattr(flow, "is_replay", None)),
            #: 用户备注（flow.comment，mitmproxy 原生字段）——与 marked 分开：
            #: marked 给 MOCK/REPLAY 徽标用，comment 是用户自己写的
            "comment": getattr(flow, "comment", "") or "",
            "timestamp": req.timestamp_start or 0.0,
            "is_connect": req.method == "CONNECT",
            "is_websocket": ws is not None,
            "ws_messages": ws_messages,
            "ws_closed": ws_closed,
        }

    # ------------------------------------------------------------ 查询

    def get_flow(self, flow_id: str):
        return self.flows.get(flow_id)

    def clear(self) -> None:
        self.flows.clear()

    def load_flows(self, flows) -> int:
        """把恢复出来的会话放进缓存（供详情 / 重放 / 导出回查）。

        线程边界：`flows` 由 asyncio 线程在 `response()` 里写入，这里从 UI
        线程整体替换 dict——`self.flows = 新字典` 是原子的属性赋值，不会读到
        半成品；代价是替换瞬间正在途中的请求可能写进旧字典而丢失（极罕见，
        且只影响缓存，不影响抓包与列表）。

        返回实际装入条数（超出 max_flows 时只保留最新的一段）。
        """
        items = [f for f in (flows or []) if f is not None]
        if self._max_flows > 0 and len(items) > self._max_flows:
            items = items[-self._max_flows:]
        self.flows = {f.id: f for f in items}
        return len(self.flows)

    # ------------------------------------------------------------ 容量（保存条数）

    def set_max_flows(self, limit: int, trim_now: bool = False) -> None:
        """改保留条数上限。

        `response()` 跑在 mitmproxy 的 asyncio 线程，UI 线程只能改这个整数
        （赋值是原子的），真正的淘汰交给下次 `response()` 里的 `_evict()`；
        代理已停止时才允许 `trim_now=True` 直接裁——避免跨线程遍历 dict。
        """
        self._max_flows = max(1, int(limit))
        if trim_now:
            self._evict()

    # ------------------------------------------------------------ 内部

    def _evict(self) -> None:
        if len(self.flows) <= self._max_flows:
            return
        # dict 保序，删最旧
        for flow_id in list(self.flows.keys())[: len(self.flows) - self._max_flows]:
            del self.flows[flow_id]
