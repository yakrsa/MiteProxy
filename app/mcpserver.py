"""MCP 接口：把最近的抓包记录暴露给 AI 客户端（JSON-RPC 2.0 over HTTP）。

为什么是 HTTP 而不是 stdio：数据在**正在跑的 GUI 进程内存里**（capture 缓存），
stdio 得另起进程、只能读落盘会话，拿不到实时流量。所以这里在 app 内起一个
本地 HTTP 服务，MCP 客户端把 URL 填进配置即可，也能直接 curl 调试。

协议：MCP 的 Streamable HTTP transport —— POST /mcp 收发 JSON-RPC 2.0，
支持 initialize / tools/list / tools/call。额外给了个 REST 端点
GET /api/flows 方便用浏览器或 curl 快速看数据（不是 MCP 标准，纯便利）。

安全：默认只绑 127.0.0.1，抓包内容可能带 cookie / token，不外泄出去。
需要在局域网里的另一台机器（或手机上的客户端）调用时，可把监听地址改成
0.0.0.0（全部网卡）或某个具体网卡 IP——但要清楚：那样局域网内任何人都能
读到完整抓包，包括鉴权头。默认关闭，要用在工具栏手动开（跟证书服务一个路子）。
"""

from __future__ import annotations

import base64
import errno
import json
import logging
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

# 耗时 / 服务器 IP 复用 capture 的口径：列表列、耗时页、MCP 三处必须同源，
# 各算一遍必然对不上（详见 addons/capture.py::request_span_ms 的注释）
from addons.capture import extract_server_ip, extract_timings, request_span_ms
# URL 匹配 / 拼串与统计聚合共用一份实现（stats 只依赖 capture + replay，
# 不依赖 Qt，MCP 与统计页不会各算各的）
from app.stats import DEFAULT_TOP_N, MAX_TOP_N, compute_stats, flow_url, match_url

log = logging.getLogger(__name__)

DEFAULT_MCP_PORT = 8899
#: 默认只监听本机；改成 0.0.0.0 才会对局域网开放
DEFAULT_MCP_HOST = "127.0.0.1"
#: 视为"对外暴露"的地址（绑这些=不再只服务于本机）
WILDCARD_HOSTS = ("0.0.0.0", "::", "")
#: 端口被占用时向上顺延的尝试次数
PORT_SCAN_TRIES = 20
#: body 预览长度（完整 body 可能几 MB，默认只给开头）
BODY_PREVIEW_LIMIT = 2000
#: 详情工具单个 body 的上限（默认给全量，超过才截断并标注）
DETAIL_BODY_LIMIT = 2 * 1024 * 1024
#: 详情里最多带多少条 WebSocket 消息
DETAIL_WS_MESSAGES = 100
#: 单次最多返回条数（防止一次吐几千条把客户端噎死）
MAX_LIMIT = 200

PROTOCOL_VERSION = "2025-03-26"
SERVER_NAME = "MiteProxy"

#: 工具描述文案：模块级用 NOOP 打标（import 期不能调 translate，翻译器还没装），
#: 运行时在 _tools() 里才真正翻译。
_DESC_TOOL = QT_TRANSLATE_NOOP(
    "McpServer",
    "返回最近的抓包记录。可按 URL、请求参数（query 或 body）、"
    "Header 关键字过滤，也支持按方法 / 状态码筛选。",
)
_DESC_URL = QT_TRANSLATE_NOOP("McpServer", "URL 关键字（匹配方法、域名、IP、路径）")
_DESC_PARAM = QT_TRANSLATE_NOOP("McpServer", "请求参数关键字（匹配 query 或请求体）")
_DESC_HEADER = QT_TRANSLATE_NOOP("McpServer", "Header 关键字（匹配请求/响应的头名或值）")
_DESC_METHOD = QT_TRANSLATE_NOOP("McpServer", "HTTP 方法，如 GET / POST")
_DESC_STATUS = QT_TRANSLATE_NOOP("McpServer", "响应状态码精确匹配，如 404")
_DESC_BODY = QT_TRANSLATE_NOOP("McpServer", "是否返回完整请求/响应体，默认只给预览")
_DESC_LIMIT = QT_TRANSLATE_NOOP("McpServer", "最多返回条数，默认 20，上限 {0}")

# -- get_flow_detail
_DESC_DETAIL_TOOL = QT_TRANSLATE_NOOP(
    "McpServer",
    "按 id 取单条会话的完整报文（含全量请求/响应体）。"
    "先用 get_recent_flows 缩小范围拿到 id，再用它展开细节——"
    "比一次性拉全量列表省 token。",
)
_DESC_ID = QT_TRANSLATE_NOOP("McpServer", "会话 id（get_recent_flows 返回的 id；给前几位前缀也行）")
_DESC_DETAIL_BODY = QT_TRANSLATE_NOOP("McpServer", "是否返回完整 body，默认 true")
# -- get_stats
_DESC_STATS_TOOL = QT_TRANSLATE_NOOP(
    "McpServer",
    "对抓包记录做整体统计：总数、错误率、平均/P95/最大耗时、上下行流量，"
    "按域名 / 状态码 / 方法聚合，慢请求 Top N，以及按时间分桶的请求分布。"
    "回答「刚才哪些请求挂了」「哪个域名最慢」这类问题用它。",
)
_DESC_STATS_URL = QT_TRANSLATE_NOOP("McpServer", "可选 URL 关键字（只统计命中方法+URL 的会话）")
_DESC_TOP_N = QT_TRANSLATE_NOOP("McpServer", "域名 / 慢请求各取前多少条，默认 {0}，上限 {1}")
# -- 写操作（add_mock_rule / replay_flow / set_breakpoint）。默认不暴露：
#    写操作能改流量行为，只在设置里显式打开后才进 tools/list
_DESC_ADD_RULE_TOOL = QT_TRANSLATE_NOOP(
    "McpServer",
    "新增一条 Mock 规则：URL 命中的请求不发往上游，直接返回指定的"
    "状态码 / Headers / Body。用来快速造接口数据。",
)
_DESC_RULE_URL = QT_TRANSLATE_NOOP("McpServer", "URL 或匹配模式（按 match_type 解释）")
_DESC_RULE_MATCH = QT_TRANSLATE_NOOP(
    "McpServer",
    "匹配方式：exact 全等 / contains 包含 / wildcard 通配符 / regex 正则，默认 contains")
_DESC_RULE_METHOD = QT_TRANSLATE_NOOP("McpServer", "只匹配该 HTTP 方法（留空 = 任意方法）")
_DESC_RULE_STATUS = QT_TRANSLATE_NOOP("McpServer", "返回的状态码，默认 200")
_DESC_RULE_HEADERS = QT_TRANSLATE_NOOP(
    "McpServer", "返回的响应头（JSON 对象，如 {\"content-type\": \"application/json\"}）")
_DESC_RULE_BODY = QT_TRANSLATE_NOOP("McpServer", "返回的响应体文本")
_DESC_RULE_NAME = QT_TRANSLATE_NOOP("McpServer", "规则名称（留空自动起名）")
_DESC_RULE_ENABLED = QT_TRANSLATE_NOOP("McpServer", "是否立即启用，默认 true")
_DESC_REPLAY_TOOL = QT_TRANSLATE_NOOP(
    "McpServer",
    "按 id 重放一条已抓包的会话（发副本，原会话不变）。需要代理正在运行。",
)
_DESC_BP_TOOL = QT_TRANSLATE_NOOP(
    "McpServer",
    "开关断点调试，或修改拦截阶段（请求前 / 响应前）与 URL 关键词。"
    "即时生效，无需重启代理。",
)
_DESC_BP_ENABLED = QT_TRANSLATE_NOOP("McpServer", "是否启用断点")
_DESC_BP_ON_REQ = QT_TRANSLATE_NOOP("McpServer", "请求发往服务器前暂停")
_DESC_BP_ON_RES = QT_TRANSLATE_NOOP("McpServer", "响应返回客户端前暂停")
_DESC_BP_KEYWORDS = QT_TRANSLATE_NOOP(
    "McpServer", "只拦 URL 含这些关键词的会话（字符串数组，留空 = 全部拦截）")
# -- 工具级错误文案（返回在 content 里，不是协议错误）
_ERR_NO_ID = QT_TRANSLATE_NOOP("McpServer", "缺少 id 参数")
_ERR_NOT_FOUND = QT_TRANSLATE_NOOP("McpServer", "找不到 id 为 {0} 的会话（可能已被清理）")
_ERR_AMBIGUOUS = QT_TRANSLATE_NOOP("McpServer", "前缀 {1} 匹配到 {0} 条会话，请给出更完整的 id")

#: 只读工具（始终暴露）
READ_TOOLS = ("get_recent_flows", "get_flow_detail", "get_stats")
#: 写工具（仅设置里打开 mcp_write_enabled 后暴露）
WRITE_TOOLS = ("add_mock_rule", "replay_flow", "set_breakpoint")


# ================================================================ 监听地址


def local_ips() -> list[str]:
    """本机非回环 IPv4 地址（绑 0.0.0.0 时告诉用户该连哪个）。

    ① 先查默认路由出口（connect UDP 不发任何包，只查路由表）——最可能是
       局域网地址；② 再用主机名解析兜底，两者去重后返回。
    """
    found: list[str] = []

    def add(ip: str) -> None:
        if not ip or ip.startswith("127.") or ip.startswith("169.254."):
            return
        if ip not in found:
            found.append(ip)

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        add(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except OSError:
        pass
    return found


def _host_display(host: str) -> str:
    """展示用主机：通配符换成实际局域网 IP，IPv6 补方括号。"""
    host = (host or "").strip()
    if host in WILDCARD_HOSTS:
        return local_ips()[0] if local_ips() else "127.0.0.1"
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def is_exposed(host: str) -> bool:
    """该监听地址是否会对外（局域网）暴露接口。"""
    host = (host or "").strip()
    if host in WILDCARD_HOSTS:
        return True
    return host not in ("127.0.0.1", "::1", "localhost")


def _tools(write_enabled: bool = False, write_ops=None) -> list[dict]:
    """MCP 工具清单（运行时翻译，别在 import 期求 translate）。

    写工具默认不进清单：客户端只能看到并调用显式授权过的能力。
    """
    t = lambda s: QCoreApplication.translate("McpServer", s)  # noqa: E731
    tools = [
        {
            "name": "get_recent_flows",
            "description": t(_DESC_TOOL),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": t(_DESC_URL)},
                    "param": {"type": "string", "description": t(_DESC_PARAM)},
                    "header": {"type": "string", "description": t(_DESC_HEADER)},
                    "method": {"type": "string", "description": t(_DESC_METHOD)},
                    "status": {"type": "integer", "description": t(_DESC_STATUS)},
                    "limit": {
                        "type": "integer",
                        # 上限是运行时常量，用 {0} 占位再 format，别写死在译文里
                        "description": t(_DESC_LIMIT).format(MAX_LIMIT),
                    },
                    "include_body": {
                        "type": "boolean",
                        "description": t(_DESC_BODY),
                    },
                },
            },
        },
        {
            "name": "get_flow_detail",
            "description": t(_DESC_DETAIL_TOOL),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": t(_DESC_ID)},
                    "include_body": {
                        "type": "boolean",
                        "description": t(_DESC_DETAIL_BODY),
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "get_stats",
            "description": t(_DESC_STATS_TOOL),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": t(_DESC_STATS_URL)},
                    "top_n": {
                        "type": "integer",
                        "description": t(_DESC_TOP_N).format(
                            DEFAULT_TOP_N, MAX_TOP_N),
                    },
                },
            },
        },
    ]
    if not write_enabled:
        return tools
    tools.extend([
        {
            "name": "add_mock_rule",
            "description": t(_DESC_ADD_RULE_TOOL),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": t(_DESC_RULE_URL)},
                    "match_type": {"type": "string",
                                   "description": t(_DESC_RULE_MATCH)},
                    "method": {"type": "string", "description": t(_DESC_RULE_METHOD)},
                    "status": {"type": "integer", "description": t(_DESC_RULE_STATUS)},
                    "headers": {"type": "object",
                                "description": t(_DESC_RULE_HEADERS)},
                    "body": {"type": "string", "description": t(_DESC_RULE_BODY)},
                    "name": {"type": "string", "description": t(_DESC_RULE_NAME)},
                    "enabled": {"type": "boolean", "description": t(_DESC_RULE_ENABLED)},
                },
                "required": ["url"],
            },
        },
        {
            "name": "replay_flow",
            "description": t(_DESC_REPLAY_TOOL),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": t(_DESC_ID)},
                },
                "required": ["id"],
            },
        },
        {
            "name": "set_breakpoint",
            "description": t(_DESC_BP_TOOL),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean", "description": t(_DESC_BP_ENABLED)},
                    "on_request": {"type": "boolean", "description": t(_DESC_BP_ON_REQ)},
                    "on_response": {"type": "boolean", "description": t(_DESC_BP_ON_RES)},
                    "url_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": t(_DESC_BP_KEYWORDS),
                    },
                },
                "required": ["enabled"],
            },
        },
    ])
    return tools


# ================================================================ 过滤（纯逻辑，好测）


def _safe_text(value, limit: int = 65536) -> str:
    """把 bytes / str 统一成用于匹配的文本，超长截断（只做关键字匹配用）。"""
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="replace")
        except Exception:
            return ""
    return str(value)[:limit]


def _flow_query(flow) -> str:
    """请求参数（query string）。"""
    url = flow_url(flow)
    try:
        return urlparse(url).query or ""
    except Exception:
        return ""


def _flow_body(flow, request: bool = True) -> str:
    msg = flow.request if request else getattr(flow, "response", None)
    if msg is None:
        return ""
    try:
        content = msg.get_content(strict=False)
    except Exception:
        content = None
    return _safe_text(content)


def _flow_headers_text(flow) -> str:
    """请求 + 响应的 `名: 值` 拼在一起，供 header 关键字匹配。"""
    parts = []
    for msg in (flow.request, getattr(flow, "response", None)):
        if msg is None:
            continue
        try:
            items = msg.headers.items()
        except Exception:
            continue
        for k, v in items:
            parts.append(f"{k}: {v}")
    return "\n".join(parts)


def match_flow(flow, url: str = "", param: str = "", header: str = "",
               method: str = "", status=None) -> bool:
    """一条会话是否命中全部给定条件（空条件视为不过滤）。"""
    if method:
        if str(getattr(flow.request, "method", "") or "").upper() != method.strip().upper():
            return False
    if status is not None:
        res = getattr(flow, "response", None)
        if res is None or getattr(res, "status_code", None) != status:
            return False
    # URL 匹配与统计页 / get_stats 共用 app.stats.match_url（一份实现）
    if url and not match_url(flow, url):
        return False
    if param:
        needle = param.lower()
        hay = f"{_flow_query(flow)} {_flow_body(flow, request=True)}".lower()
        if needle not in hay:
            return False
    if header:
        needle = header.lower()
        if needle not in _flow_headers_text(flow).lower():
            return False
    return True


def filter_flows(flows, url: str = "", param: str = "", header: str = "",
                 method: str = "", status=None, limit: int = 20):
    """按条件过滤并**取最近的 N 条**（flows 是按到达顺序的，故从末尾取）。"""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, MAX_LIMIT))

    hits = [f for f in flows if match_flow(f, url, param, header, method, status)]
    return hits[-limit:]


# ================================================================ 序列化


def flow_to_dict(flow, include_body: bool = False) -> dict:
    """会话 → 可 JSON 化的字典（body 默认只给预览）。"""
    req = getattr(flow, "request", None)
    res = getattr(flow, "response", None)
    url = flow_url(flow)

    def headers_of(msg) -> dict:
        if msg is None:
            return {}
        try:
            return {str(k): str(v) for k, v in msg.headers.items()}
        except Exception:
            return {}

    def body_of(msg) -> tuple[str, bool]:
        """返回 (文本, 是否被截断)。"""
        text = _flow_body(flow, request=(msg is req)) if msg is not None else ""
        if not text:
            return "", False
        if include_body:
            return text, False
        return text[:BODY_PREVIEW_LIMIT], len(text) > BODY_PREVIEW_LIMIT

    req_body, req_cut = body_of(req)
    res_body, res_cut = body_of(res)

    req_ts = getattr(req, "timestamp_start", None)
    res_ts = getattr(res, "timestamp_end", None)
    duration_ms = None
    if req_ts and res_ts:
        duration_ms = round((res_ts - req_ts) * 1000, 1)

    return {
        "id": getattr(flow, "id", "") or "",
        "method": getattr(req, "method", "") or "",
        "url": url,
        "status": getattr(res, "status_code", None),
        "duration_ms": duration_ms,
        "request_headers": headers_of(req),
        "response_headers": headers_of(res),
        "request_body": req_body,
        "response_body": res_body,
        "body_truncated": req_cut or res_cut,
    }


def _decode_body(msg, full: bool):
    """把一条消息体解成 (文本, 编码, 是否截断)。

    文本类 utf-8 直出；二进制（图片 / protobuf / 压缩后仍乱码）回落 base64，
    并在 encoding 里说明——不给编码的话客户端拿到一堆乱码无从判断。
    注意不能复用 `_safe_text`：它有 64KB 截断，那是为**关键字匹配**做的
    保护，详情工具要的是全量。
    """
    if msg is None:
        return "", "utf-8", False
    try:
        raw = msg.get_content(strict=False)
    except Exception:
        raw = None
    if not raw:
        return "", "utf-8", False
    if isinstance(raw, str):
        text, enc = raw, "utf-8"
    else:
        try:
            text, enc = raw.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            text, enc = base64.b64encode(raw).decode("ascii"), "base64"

    if not full:
        # 二进制不给半截 base64（解不开也没意义）：标 encoding + truncated 即可
        if enc == "base64":
            return "", enc, True
        return text[:BODY_PREVIEW_LIMIT], enc, len(text) > BODY_PREVIEW_LIMIT
    if len(text) > DETAIL_BODY_LIMIT:
        return text[:DETAIL_BODY_LIMIT], enc, True
    return text, enc, False


def _iso(ts) -> str:
    """时间戳 → 本地 ISO 字符串（给人看；机器要算用 duration_ms）。"""
    try:
        return datetime.fromtimestamp(float(ts)).isoformat(timespec="milliseconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def flow_detail(flow, include_body: bool = True) -> dict:
    """单条会话的完整报文（详情工具 / REST 详情端点共用）。

    耗时与服务器 IP 走 capture 的函数，跟列表列、耗时页同源。
    """
    req = getattr(flow, "request", None)
    res = getattr(flow, "response", None)
    ws = getattr(flow, "websocket", None)

    req_text, req_enc, req_cut = _decode_body(req, include_body)
    res_text, res_enc, res_cut = _decode_body(res, include_body)

    ws_payload = None
    if ws is not None:
        messages = list(getattr(ws, "messages", None) or [])
        shown = messages[:DETAIL_WS_MESSAGES]
        ws_payload = {
            "total": len(messages),
            "shown": len(shown),
            "closed": bool(getattr(ws, "timestamp_end", None)),
            "messages": [
                {
                    "from_client": bool(getattr(m, "from_client", None)),
                    "timestamp": _iso(getattr(m, "timestamp", None)),
                    "content": _safe_text(getattr(m, "content", b"") or b"",
                                         BODY_PREVIEW_LIMIT if not include_body else 20000),
                }
                for m in shown
            ],
        }

    # 只带 mproxy_* 的自定义元数据（弱网延迟等），别把 mitmproxy 内部字段漏出去
    meta = {}
    try:
        for k, v in (getattr(flow, "metadata", None) or {}).items():
            if str(k).startswith("mproxy_"):
                meta[str(k)] = v
    except Exception:
        pass

    err = getattr(flow, "error", None)
    return {
        "id": getattr(flow, "id", "") or "",
        "method": getattr(req, "method", "") or "",
        "url": flow_url(flow),
        "http_version": getattr(req, "http_version", "") or "",
        "host": getattr(req, "pretty_host", "") or "",
        "path": getattr(req, "path", "") or "",
        "server_ip": extract_server_ip(flow),
        "status": getattr(res, "status_code", None),
        "reason": getattr(res, "reason", "") or "",
        "duration_ms": round(request_span_ms(flow), 1),
        "timings": extract_timings(flow),
        "request_started_at": _iso(getattr(req, "timestamp_start", None)),
        "response_finished_at": _iso(getattr(res, "timestamp_end", None)),
        "request_headers": _headers_of(flow, req),
        "response_headers": _headers_of(flow, res),
        "request_body": req_text,
        "response_body": res_text,
        "request_body_encoding": req_enc,
        "response_body_encoding": res_enc,
        "body_truncated": req_cut or res_cut,
        "request_size": len(getattr(req, "raw_content", None) or b""),
        "response_size": len(getattr(res, "raw_content", None) or b""),
        "error": getattr(err, "msg", "") or "" if err is not None else "",
        "is_replay": bool(getattr(flow, "is_replay", None)),
        "is_websocket": ws is not None,
        "websocket": ws_payload,
        "marked": getattr(flow, "marked", "") or "",
        "comment": getattr(flow, "comment", "") or "",
        "metadata": meta,
    }


def _headers_of(flow, msg) -> dict:
    if msg is None:
        return {}
    try:
        return {str(k): str(v) for k, v in msg.headers.items()}
    except Exception:
        return {}


def resolve_flow(flows, flow_id: str, flow_by_id=None):
    """按 id 取会话，返回 (flow, 错误文案)。

    优先走注入的 `flow_by_id`（capture.get_flow，口径一致）；没注入就在
    列表里找——精确命中优先，否则允许**唯一**前缀（完整 uuid 太长，AI
    抄一半也该能工作）。
    """
    fid = (flow_id or "").strip()
    if not fid:
        return None, QCoreApplication.translate("McpServer", _ERR_NO_ID)
    if flow_by_id is not None:
        try:
            got = flow_by_id(fid)
        except Exception:
            got = None
        if got is not None:
            return got, None
    for f in flows:
        if str(getattr(f, "id", "")) == fid:
            return f, None
    hits = [f for f in flows if str(getattr(f, "id", "")).startswith(fid)]
    if len(hits) == 1:
        return hits[0], None
    if len(hits) > 1:
        return None, QCoreApplication.translate(
            "McpServer", _ERR_AMBIGUOUS).format(len(hits), fid)
    return None, QCoreApplication.translate(
        "McpServer", _ERR_NOT_FOUND).format(fid)


# ================================================================ JSON-RPC


def _ok(req_id, result) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": code, "message": message}}


def _tool_result(payload, is_error: bool = False) -> dict:
    """MCP 的 tool 结果：文本块里放 JSON（客户端好解析，也便于人读）。

    `is_error=True` 是 MCP 规定的**工具执行**错误标记（如 id 没找到）——
    协议层错误（方法不存在 / 参数非法）才走 JSON-RPC 的 error 字段。
    """
    result = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ]
    }
    if is_error:
        result["isError"] = True
    return result


def _dispatch_write(req_id, name: str, args, write_ops) -> dict:
    """写工具分发：回调由主窗口注入（add_mock_rule / replay_flow / set_breakpoint）。

    约定：回调返回 dict；返回体里带 `error` 键即视为**工具执行失败**
    （isError，内容照常回给客户端），成功则整体作为结果 payload。
    回调抛异常 = 服务端问题，走 JSON-RPC -32603。
    """
    op = (write_ops or {}).get(name)
    if op is None:
        return _err(req_id, -32603, f"Write operation unavailable: {name}")
    try:
        payload = op(args if isinstance(args, dict) else {})
    except Exception as e:
        log.warning("MCP 写操作 %s 失败：%s", name, e)
        return _err(req_id, -32603, f"Write operation failed: {e}")
    is_error = isinstance(payload, dict) and bool(payload.get("error"))
    return _ok(req_id, _tool_result(payload, is_error=is_error))


def handle_rpc(flow_provider, payload, flow_by_id=None,
               write_enabled: bool = False, write_ops=None) -> dict | None:
    """处理一条 JSON-RPC 请求；通知（无 id）返回 None。

    `write_enabled` / `write_ops`：写工具门控。关闭时写工具等同不存在
    （客户端调它会拿到与未知工具相同的 -32602）——默认关闭，见 settings
    的 `mcp_write_enabled`。
    """
    if not isinstance(payload, dict):
        return _err(None, -32600, "Invalid Request")
    req_id = payload.get("id")
    method = payload.get("method") or ""
    params = payload.get("params") or {}

    if method == "initialize":
        return _ok(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": _app_version()},
        })
    if method == "tools/list":
        return _ok(req_id, {"tools": _tools(write_enabled, write_ops)})
    if method == "tools/call":
        name = params.get("name") or ""
        args = params.get("arguments") or {}
        allowed = READ_TOOLS + (WRITE_TOOLS if write_enabled else ())
        if name not in allowed:
            # 以下错误文案是 JSON-RPC 协议层消息（和 Parse error / Invalid
            # Request 一样走英文），不是界面文案，故不做翻译。
            return _err(req_id, -32602, f"Unknown tool: {name}")
        if name in WRITE_TOOLS:
            return _dispatch_write(req_id, name, args, write_ops)
        try:
            flows = list(flow_provider())
        except Exception as e:
            log.warning("MCP 取会话失败：%s", e)
            return _err(req_id, -32603, f"Failed to read flows: {e}")
        if name == "get_flow_detail":
            flow, err = resolve_flow(flows, args.get("id"), flow_by_id)
            if flow is None:
                # 没找到属于"工具执行结果"，不是协议错误：走 isError
                return _ok(req_id, _tool_result({"error": err}, is_error=True))
            return _ok(req_id, _tool_result(
                flow_detail(flow, bool(args.get("include_body", True)))
            ))
        if name == "get_stats":
            # 统计走 capture 全量快照（不吃 filter_flows 的 200 条上限）——
            # 「整体情况」被悄悄截断比多算几毫秒更糟糕
            return _ok(req_id, _tool_result(compute_stats(
                flows,
                top_n=args.get("top_n", DEFAULT_TOP_N),
                url=str(args.get("url") or ""),
            )))
        picked = filter_flows(
            flows,
            url=str(args.get("url") or ""),
            param=str(args.get("param") or ""),
            header=str(args.get("header") or ""),
            method=str(args.get("method") or ""),
            status=args.get("status"),
            limit=args.get("limit", 20),
        )
        include_body = bool(args.get("include_body", False))
        return _ok(req_id, _tool_result({
            "total": len(picked),
            "flows": [flow_to_dict(f, include_body) for f in picked],
        }))
    if method in ("notifications/initialized", "initialized"):
        return None
    return _err(req_id, -32601, f"Method not found: {method}")


def _app_version() -> str:
    try:
        from app.version import __version__
        return str(__version__)
    except Exception:
        return "unknown"


# ================================================================ HTTP 服务


class _McpHTTPServer(ThreadingHTTPServer):
    """按 host 自动选 IPv4 / IPv6。

    基类写死 AF_INET，填 ::1 这类 IPv6 地址会直接绑不上；另外打开
    allow_reuse_address，关掉再开（或改端口重启）不会被 TIME_WAIT 卡住。
    """

    def __init__(self, server_address, handler):
        host = server_address[0]
        if ":" in host and not host.startswith("["):
            self.address_family = socket.AF_INET6
        self.allow_reuse_address = True
        super().__init__(server_address, handler)


class McpServer:
    """本地 MCP 服务（后台线程跑 ThreadingHTTPServer）。"""

    def __init__(self, flow_provider, port: int = DEFAULT_MCP_PORT,
                 host: str = DEFAULT_MCP_HOST, flow_by_id=None,
                 write_enabled: bool = False, write_ops=None):
        #: () -> list[flow]；由主窗口注入，避免服务反向依赖 Qt 对象
        self.flow_provider = flow_provider
        #: (flow_id) -> flow | None；可选，按 id 取单条（详情工具用）
        self.flow_by_id = flow_by_id
        #: 写操作总开关（设置里的「MCP 写操作」，默认关）。可变属性——
        #    运行中改设置时直接赋值即可，无需重启服务
        self.write_enabled = bool(write_enabled)
        #: {工具名: callable(args) -> dict}；写操作的实际执行体（主窗口注入）
        self.write_ops = dict(write_ops or {})
        self.port = port
        self.host = (host or DEFAULT_MCP_HOST).strip() or DEFAULT_MCP_HOST
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._bound_port: int = port

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def url(self) -> str:
        return f"http://{_host_display(self.host)}:{self._bound_port}/mcp"

    @property
    def exposed(self) -> bool:
        """当前监听地址是否对外暴露（局域网可见）。"""
        return is_exposed(self.host)

    def urls(self) -> list[str]:
        """所有可以访问到的地址（绑 0.0.0.0 时会列出每张网卡的 IP）。"""
        port = self._bound_port
        if (self.host or "") in WILDCARD_HOSTS:
            hosts = ["127.0.0.1"] + local_ips()
        else:
            hosts = [_host_display(self.host)]
        return [f"http://{h}:{port}/mcp" for h in hosts]

    def start(self) -> bool:
        """启动；端口被占用就顺延。成功返回 True。

        注意：地址本身绑不上（比如填了个本机没有的 IP）换端口也没用，
        这种情况直接失败返回 False，不再空转 20 次。
        """
        if self.running:
            return True
        # handler 通过 owner 引用反向拿 write_enabled / write_ops：这两个
        # 是运行中可变的（设置里即时开关），启动时快照一份会过期
        owner = self
        handler = type(
            "BoundHandler", (_Handler,), {
                "flow_provider": staticmethod(self.flow_provider),
                "flow_by_id": staticmethod(self.flow_by_id or (lambda _id: None)),
                "owner": staticmethod(lambda: owner),
            }
        )
        last_err: OSError | None = None
        for offset in range(PORT_SCAN_TRIES):
            candidate = self.port + offset
            if candidate > 65535:
                break
            try:
                server = _McpHTTPServer((self.host, candidate), handler)
            except OSError as e:
                last_err = e
                # 地址不可用（不是端口冲突）：换端口也一样失败，别再试
                # EADDRNOTAVAIL(49) / EADDRINUSE(48)：前者换端口也没用
                if e.errno == errno.EADDRNOTAVAIL:
                    break
                continue
            server.daemon_threads = True
            self._server = server
            self._bound_port = candidate
            self._thread = threading.Thread(
                target=server.serve_forever, name="mcp-server", daemon=True
            )
            self._thread.start()
            if self.exposed:
                log.warning(
                    "MCP 服务对外暴露: %s（局域网内可读取完整抓包，含鉴权头）",
                    ", ".join(self.urls()),
                )
            else:
                log.info("MCP 服务已启动: %s", self.url)
            return True
        log.warning("MCP 服务启动失败（%s:%s 起均不可用）: %s",
                    self.host, self.port, last_err)
        return False

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
            try:
                self._server.server_close()
            except Exception:
                pass
        self._server = None
        self._thread = None
        log.info("MCP 服务已停止")


class _Handler(BaseHTTPRequestHandler):
    """只服务 /mcp（JSON-RPC）和 /api/flows（REST 便利端点）。"""

    flow_provider = staticmethod(lambda: [])
    flow_by_id = staticmethod(lambda _id: None)
    #: McpServer 实例（BoundHandler 由 start() 注入）。写工具门控要读
    #: 运行时可变的 write_enabled，不能快照
    owner = staticmethod(lambda: None)

    # ------------------------------------------------------------ 工具

    def _send_json(self, code: int, payload) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_empty(self, code: int) -> None:
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:  # 静音默认访问日志
        log.debug("mcp http: " + fmt, *args)

    # ------------------------------------------------------------ GET

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/flows":
            self._serve_rest()
        elif path.startswith("/api/flows/"):
            self._serve_rest_detail(path[len("/api/flows/"):])
        elif path == "/api/stats":
            self._serve_rest_stats()
        elif path in ("/mcp", "/", "/health"):
            owner = self.owner()
            self._send_json(200, {
                "service": SERVER_NAME,
                "endpoint": "/mcp",
                "transport": "streamable-http (JSON-RPC 2.0)",
                "tools": [t["name"] for t in _tools(
                    getattr(owner, "write_enabled", False),
                    getattr(owner, "write_ops", None),
                )],
            })
        else:
            self._send_json(404, {"error": "not found"})

    def _serve_rest(self) -> None:
        q = parse_qs(urlparse(self.path).query)

        def one(key: str) -> str:
            return (q.get(key) or [""])[0]

        status_raw = one("status")
        try:
            status = int(status_raw) if status_raw else None
        except ValueError:
            self._send_json(400, {"error": "status must be an integer"})
            return
        try:
            flows = list(self.flow_provider())
        except Exception as e:
            self._send_json(500, {"error": f"Failed to read flows: {e}"})
            return
        picked = filter_flows(
            flows,
            url=one("url"), param=one("param"), header=one("header"),
            method=one("method"), status=status,
            limit=one("limit") or 20,
        )
        self._send_json(200, {
            "total": len(picked),
            "flows": [flow_to_dict(f, bool(one("include_body"))) for f in picked],
        })

    def _serve_rest_detail(self, flow_id: str) -> None:
        from urllib.parse import unquote

        try:
            flows = list(self.flow_provider())
        except Exception as e:
            self._send_json(500, {"error": f"Failed to read flows: {e}"})
            return
        flow, err = resolve_flow(flows, unquote(flow_id or ""), self.flow_by_id)
        if flow is None:
            self._send_json(404, {"error": err})
            return
        include_body = (parse_qs(urlparse(self.path).query).get("include_body")
                        or [""])[0] not in ("0", "false", "False")
        self._send_json(200, flow_detail(flow, include_body))

    def _serve_rest_stats(self) -> None:
        """GET /api/stats?url=&top_n= —— 与 get_stats 工具同一份聚合。"""
        q = parse_qs(urlparse(self.path).query)
        try:
            flows = list(self.flow_provider())
        except Exception as e:
            self._send_json(500, {"error": f"Failed to read flows: {e}"})
            return
        top_n_raw = (q.get("top_n") or [""])[0]
        try:
            top_n = int(top_n_raw) if top_n_raw else DEFAULT_TOP_N
        except ValueError:
            self._send_json(400, {"error": "top_n must be an integer"})
            return
        self._send_json(200, compute_stats(
            flows, top_n=top_n, url=(q.get("url") or [""])[0],
        ))

    # ------------------------------------------------------------ POST

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/mcp":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(200, _err(None, -32700, "Parse error"))
            return

        # 批量（数组）逐条处理：MCP 允许客户端打包发
        if isinstance(payload, list):
            results = [r for r in (self._handle(p) for p in payload)
                       if r is not None]
            self._send_json(200, results)
            return

        result = self._handle(payload)
        if result is None:
            self._send_empty(202)     # 通知：无响应体
            return
        self._send_json(200, result)

    def _handle(self, payload):
        owner = self.owner()
        return handle_rpc(
            self.flow_provider, payload, self.flow_by_id,
            write_enabled=getattr(owner, "write_enabled", False),
            write_ops=getattr(owner, "write_ops", None),
        )
