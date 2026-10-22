"""捕获 addon：response hook 收 flow，推送摘要给 UI（见 DESIGN.md 2.4 / 3.2）。

注意：本类的回调运行在 mitmproxy 的 asyncio 线程里，Qt 侧必须用
信号（跨线程队列连接）接收，不能在回调里直接碰控件。
"""

from __future__ import annotations

import ipaddress
import logging
import time
from typing import Callable, Optional

from app.replay import format_request_url

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


#: 计时分段 key → 展示名（详情页「耗时」签；i18n 在 UI 侧做）
TIMING_PHASES = ("connect", "tls", "send", "wait", "receive")

#: 分段 → (起点锚点, 终点锚点)。锚点都是 time.time() 域的绝对时间戳（秒）；
#: 耗时 = 终点 - 起点，「具体时刻」= 这两个值本身（Fiddler Statistics 的
#: Timer 表同样给绝对时钟）。extract_timings / extract_timing_marks 共用，
#: 保证「耗时」与「时刻」永远出自同一根轴。
TIMING_ANCHORS = {
    "connect": ("server_start", "tcp_setup"),
    "tls": ("tcp_setup", "tls_setup"),
    "send": ("req_start", "req_end"),
    "wait": ("req_end", "res_start"),
    "receive": ("res_start", "res_end"),
}


def _ts(obj, attr: str):
    """安全取时间戳（毫秒换算前的秒值）；取不到返回 None。"""
    try:
        value = getattr(obj, attr, None)
    except Exception:
        return None
    return value if isinstance(value, (int, float)) else None


def _timing_anchors(flow) -> dict:
    """时间轴上的所有锚点（绝对时间戳秒；缺失为 None）。

    同名锚点被相邻两段共用（如 tcp_setup 既是 connect 的终点、也是 tls 的
    起点），所以先一次性取出、再由各段按 TIMING_ANCHORS 组合——避免两处
    各自取时间戳、口径漂移。
    """
    req = getattr(flow, "request", None)
    res = getattr(flow, "response", None)
    server_conn = getattr(flow, "server_conn", None)
    return {
        "server_start": _ts(server_conn, "timestamp_start")
        if server_conn is not None
        else None,
        "tcp_setup": _ts(server_conn, "timestamp_tcp_setup")
        if server_conn is not None
        else None,
        "tls_setup": _ts(server_conn, "timestamp_tls_setup")
        if server_conn is not None
        else None,
        "req_start": _ts(req, "timestamp_start"),
        "req_end": _ts(req, "timestamp_end"),
        "res_start": _ts(res, "timestamp_start") if res is not None else None,
        "res_end": _ts(res, "timestamp_end") if res is not None else None,
    }


def extract_timings(flow) -> dict:
    """请求的分段耗时（毫秒），对齐 Fiddler Statistics 的计时口径。

    时间轴锚点（都是 time.time() 域的绝对时间戳）：
      server_conn.timestamp_start       连接建立开始（域名 = DNS 解析起点）
      server_conn.timestamp_tcp_setup  TCP 握手完成
      server_conn.timestamp_tls_setup  TLS 握手完成（HTTPS 才有）
      request.timestamp_start           开始接收客户端请求
      request.timestamp_end             请求发送完成
      response.timestamp_start          收到响应首字节（TTFB）
      response.timestamp_end            响应接收完成

    分段（缺锚点的段记 0.0——mock / map-local 注入的响应没有 server_conn，
    本就没走过网络；负值钳到 0，防时钟跳变把某一阶段算成负数）：
      connect  建连（含 DNS）   tcp_setup  - server_conn.timestamp_start
      tls      TLS 握手          tls_setup  - tcp_setup
      send     发送请求          request.timestamp_end - request.timestamp_start
      wait     等待响应（TTFB）  response.timestamp_start - request.timestamp_end
      receive  接收响应          response.timestamp_end - response.timestamp_start

    只要「具体时刻」不要耗时的场景（详情页每行的时间列），用
    :func:`extract_timing_marks`——同一根轴，不重复取时间戳。
    """
    def ms(later, earlier) -> float:
        if later is None or earlier is None:
            return 0.0
        return max(0.0, round((float(later) - float(earlier)) * 1000, 1))

    anchors = _timing_anchors(flow)
    conn_start = anchors["server_start"]
    tcp_setup = anchors["tcp_setup"]
    tls_setup = anchors["tls_setup"]
    req_start = anchors["req_start"]
    req_end = anchors["req_end"]
    res_start = anchors["res_start"]
    res_end = anchors["res_end"]

    return {
        "connect": ms(tcp_setup, conn_start),
        "tls": ms(tls_setup, tcp_setup) if tls_setup is not None else 0.0,
        "send": ms(req_end, req_start),
        "wait": ms(res_start, req_end),
        "receive": ms(res_end, res_start),
    }


def extract_timing_marks(flow) -> dict:
    """每个分段的「具体时刻」：``{phase: (开始秒, 结束秒)}``，缺失为 None。

    与 extract_timings 同一根时间轴（共用 _timing_anchors），所以
    「结束 - 开始」恒等于 extract_timings 里的毫秒值。详情页「耗时」签
    用它把绝对时间显示在每一行（对齐 Fiddler Statistics 的 Timer 表：
    光有耗时看不出「什么时候慢的」，有绝对时刻才能和日志/服务端对账）。
    """
    anchors = _timing_anchors(flow)
    return {
        phase: (anchors.get(start), anchors.get(end))
        for phase, (start, end) in TIMING_ANCHORS.items()
    }


def timing_span(flow) -> tuple[float | None, float | None]:
    """整条请求的时间窗口 ``(开始, 结束)``，用于耗时页顶部的「具体时间」行。

    起点取时间轴上**最早**的锚点（建连早于请求发送，取建连才能真正覆盖
    「这条请求什么时候开始」），终点取响应结束；响应未返回时退化为最后
    一个已知锚点。全无时间戳时返回 (None, None)。
    """
    anchors = _timing_anchors(flow)
    starts = [
        v
        for v in (
            anchors["server_start"],
            anchors["req_start"],
            anchors["tcp_setup"],
            anchors["tls_setup"],
        )
        if v
    ]
    end = anchors["res_end"] or anchors["res_start"] or anchors["req_end"]
    return (min(starts) if starts else None, end)


def request_span_ms(flow) -> float:
    """列表「耗时」列口径：请求开始 → 响应结束（毫秒），含弱网延迟。

    上游真实响应时等于 extract_timings 的 send+wait+receive 之和；mock /
    map-local 注入的响应没有 timestamp_end，退化为当前时间（mock 延迟与
    弱网延迟都已睡完，不能再叠加 throttle_ms，否则重复计一次）。

    summarize 的 duration_ms 与详情页耗时分析的对账行都用它——两处数字
    必须同源，否则用户对不上（见 DESIGN.md 3.2.8）。
    """
    req = getattr(flow, "request", None)
    res = getattr(flow, "response", None)
    if req is None or not getattr(req, "timestamp_start", None):
        return 0.0
    try:
        throttle_ms = float(
            (getattr(flow, "metadata", None) or {}).get("mproxy_throttle_ms") or 0
        )
    except (TypeError, ValueError):
        throttle_ms = 0.0
    try:
        if res is not None:
            if res.timestamp_end:
                return round(
                    (res.timestamp_end - req.timestamp_start) * 1000 + throttle_ms, 1
                )
            return round((time.time() - req.timestamp_start) * 1000, 1)
    except Exception:
        pass
    return 0.0


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

    def request(self, flow) -> None:
        """请求一发出就进列表（pending 可见）；响应回来再走 update 原地补完。

        配合 flow_store 的 append（请求）→ update（响应）语义：response 必晚于
        request，列表里已有同 id 的 pending 行，update 按 id 原地替换，不会重复。

        **插入端也要淘汰**：只有 `response()` 淘汰的话，永远收不到响应的
        会话（HTTPS 的 CONNECT 隧道、连接被重置/超时走 error 的请求）会
        永久驻留在这个 dict 里——列表那边有 5000 上限，这里没有，长时间
        抓 HTTPS 站点就是实打实的内存泄漏。
        """
        self.flows[flow.id] = flow
        self._evict()
        self._emit_flow(flow)

    def response(self, flow) -> None:
        self.flows[flow.id] = flow
        self._evict()
        # response 必晚于 request：列表里已有同 id 的 pending 行，这里走「更新」
        # 通道（flow_store.update 按 id 原地替换），不会新增重复行。
        if self._on_update is not None:
            try:
                self._on_update(self.summarize(flow))
            except Exception:
                log.exception("flow 更新回调异常")

    def _emit_flow(self, flow) -> None:
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
        self._evict()
        self._emit_update(flow)

    def websocket_end(self, flow) -> None:
        """连接关闭：补上关闭码与最终耗时。"""
        self.flows.setdefault(flow.id, flow)
        self._evict()
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
            # HTTP：耗时口径抽成 request_span_ms（与耗时分析对账行同源）
            duration_ms = request_span_ms(flow)
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
            # 用 format_request_url 而不是 pretty_url：后者对 IPv6 不加方括号
            # （`http://::1:8080/x`），这条 URL 会落进会话存档、显示在列表、
            # 参与过滤搜索和 tooltip——恢复出来的会话会带着一个解析不了的
            # 畸形 URL（详见 app/replay.py 的说明）
            "url": format_request_url(req),
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
            #: 分段耗时（毫秒，Fiddler Statistics 口径，见 extract_timings）；
            #: 随 summary 落盘，恢复的会话也能看耗时分析
            "timings": extract_timings(flow),
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

        `response()` / `request()` 跑在 mitmproxy 的 asyncio 线程，UI 线程只能
        改这个整数（赋值是原子的），真正的淘汰交给下次钩子里的 `_evict()`；
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
