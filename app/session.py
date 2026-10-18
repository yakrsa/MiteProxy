"""会话落盘与恢复（对齐 Fiddler 的 Save All Sessions / Load Sessions）。

设计要点：

- **纯函数、无 Qt 依赖**：只在 UI 层做弹窗，文件读写在这里，单测可逐字断言。
- **JSONL 一行一条会话**：流式追加即可保存、半截文件也能读（坏行跳过计数），
  不必把整包会话读进内存再解析。
- **body 有预算**：单条上限 + 整包上限（预算只约束响应体），超预算就只存元数据并置
  `body_dropped`，绝不因为一条大 body 把整个保存拖垮。请求体只受单条上限约束——
  保住 POST payload，恢复后才能原样重放。
- **恢复后仍是"活会话"**：重建 mitmproxy 的 Request/Response/HTTPFlow，
  所以恢复出来的会话照样能看详情、重放、导出。

文件结构（每行一个 JSON 对象）::

    {"v": 1, "summary": {...}, "request": {...}, "response": {...} | null,
     "ws_messages": {...} | null, "server_conn": {...} | null}

``summary`` 含 `timings``（分段耗时，耗时分析页用）；``server_conn`` 存三个
连接时间戳（恢复后详情页「耗时」签的连接/TLS 分段靠它们算）。两者缺省时
按 0 处理，旧文件不兼容也不炸。
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from mitmproxy.connection import Client, Server
from mitmproxy.http import HTTPFlow, Request, Response

from app.replay import ensure_request_authority, format_request_url
from app.rules import CONFIG_DIR
from PySide6.QtCore import QCoreApplication
# （decode_body 已不用于保存路径：text 分支只认 UTF-8，见 _encode_body 注释）

log = logging.getLogger(__name__)

SESSION_VERSION = 1
SESSION_EXT = ".jsonl"

DEFAULT_BODY_LIMIT = 512 * 1024          # 单条 body 上限，与抓包索引策略一致
DEFAULT_TOTAL_LIMIT = 512 * 1024 * 1024  # 整包 body 总预算 512MB（显式保存）
AUTOSAVE_BODY_LIMIT = 64 * 1024          # 自动快照：单条 64KB
AUTOSAVE_TOTAL_LIMIT = 32 * 1024 * 1024  # 自动快照：整包 32MB（保证退出时秒级完成）

AUTOSAVE_PATH = CONFIG_DIR / "last-session.jsonl"
AUTOSAVE_META_PATH = CONFIG_DIR / "last-session.meta.json"
ARCHIVE_PATH = CONFIG_DIR / "last-session.previous.jsonl"
SESSIONS_DIR = CONFIG_DIR / "sessions"

#: 单条 WS 会话最多存多少条消息（与详情面板表格上限一致，超出只存前 N 条并标记）
WS_MESSAGE_LIMIT = 2000


@dataclass
class SessionLimits:
    """body 存储预算。"""

    body_limit: int = DEFAULT_BODY_LIMIT
    total_limit: int = DEFAULT_TOTAL_LIMIT


DEFAULT_LIMITS = SessionLimits()
AUTOSAVE_LIMITS = SessionLimits(AUTOSAVE_BODY_LIMIT, AUTOSAVE_TOTAL_LIMIT)


@dataclass
class SaveResult:
    path: Path
    count: int = 0
    bytes_written: int = 0
    bodies_dropped: int = 0
    bodies_truncated: int = 0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class LoadResult:
    path: Path
    flows: list = field(default_factory=list)        # 重建出的 HTTPFlow
    summaries: list = field(default_factory=list)    # 与 flows 同序，供列表直接用
    skipped: int = 0            # 坏行 / 版本不符
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def count(self) -> int:
        return len(self.flows)


# ====================================================================== 写出


def _encode_body(
    data: bytes, content_type: str, limits: SessionLimits, remaining: int
) -> tuple[dict, int]:
    """把 body 编成可 JSON 化的字段，返回 (字段, 实际占用字节数)。

    预算耗尽（remaining <= 0）时不存内容，只留大小与 `dropped` 标记。
    """
    if not data:
        return {}, 0
    if remaining <= 0:
        return {"dropped": True, "size": len(data)}, 0

    payload = data
    truncated = False
    if len(payload) > limits.body_limit:
        payload = payload[: limits.body_limit]
        truncated = True
    if len(payload) > remaining:
        payload = payload[:remaining]
        truncated = True

    base64_used = False
    # 只有 **UTF-8 能无损往返**的 body 才走 text 分支：decode_body 会按
    # Content-Type 声明的 charset（如 gbk）解码，那个 str 恢复时只能按
    # UTF-8 重新编码——字节就被篡改了（详情乱码 / 重放 payload 变形）。
    # 非 UTF-8 内容直接 base64 落盘，字节级可逆。
    try:
        text = payload.decode("utf-8")
        out: dict = {"encoding": "text", "data": text}
    except UnicodeDecodeError:
        out = {"encoding": "base64", "data": base64.b64encode(payload).decode("ascii")}
        base64_used = True
    out["size"] = len(data)
    if truncated:
        out["truncated"] = True

    # 预算按**落盘字符数**扣：base64 膨胀 4/3，文本按 UTF-8 字节算
    cost = len(out["data"]) if base64_used else len(out["data"].encode("utf-8"))
    return out, cost


def _encode_message(
    msg, limits: SessionLimits, remaining: int
) -> tuple[dict, int]:
    """消息 → dict（headers 用 [[k, v]] 保留重复头与顺序），返回 (dict, 剩余预算)。"""
    if msg is None:
        return {}, remaining
    try:
        headers = [[str(k), str(v)] for k, v in msg.headers.items(multi=True)]
    except Exception:
        log.debug("读取 headers 失败", exc_info=True)
        headers = []
    try:
        content_type = str(msg.headers.get("content-type", "") or "")
    except Exception:
        content_type = ""
    try:
        body = msg.get_content(strict=False) or b""
    except Exception:
        body = b""

    encoded, cost = _encode_body(body, content_type, limits, remaining)
    return {
        "http_version": getattr(msg, "http_version", "") or "HTTP/1.1",
        "headers": headers,
        "body": encoded,
        "timestamp_start": getattr(msg, "timestamp_start", None),
        "timestamp_end": getattr(msg, "timestamp_end", None),
    }, remaining - cost


def _encode_websocket(
    ws, limits: SessionLimits, remaining: int
) -> tuple[dict, int, bool]:
    """WebSocket 连接 → dict。

    消息逐条编（文本/base64 与 body 同一套编码），共用同一份剩余预算——
    WS 消息可能极大，不能让一条吵闹的连接把整包保存撑爆。
    超出条数上限或预算耗尽即停，`truncated` 记下来，`total` 保留真实条数。
    返回 (dict, 剩余预算, 是否有消息被丢弃)。
    """
    messages = list(getattr(ws, "messages", []) or [])
    stored: list[dict] = []
    dropped = False
    for index, msg in enumerate(messages):
        if index >= WS_MESSAGE_LIMIT:
            dropped = True
            break
        if remaining <= 0:
            dropped = True
            break
        try:
            content = getattr(msg, "content", b"") or b""
        except Exception:
            content = b""
        mtype = getattr(msg, "type", None)
        try:
            type_value = int(mtype)
        except (TypeError, ValueError):
            type_value = str(getattr(mtype, "name", "") or "")
        encoded, cost = _encode_body(content, "", limits, remaining)
        remaining -= cost
        stored.append(
            {
                "from_client": bool(getattr(msg, "from_client", False)),
                "type": type_value,
                "content": encoded,
                "timestamp": getattr(msg, "timestamp", None),
            }
        )
    close_code = getattr(ws, "close_code", None)
    out = {
        "messages": stored,
        "total": len(messages),
        "closed_by_client": getattr(ws, "closed_by_client", None),
        "close_code": int(close_code) if isinstance(close_code, int) else None,
        "close_reason": str(getattr(ws, "close_reason", "") or ""),
        "timestamp_end": getattr(ws, "timestamp_end", None),
    }
    if dropped or len(stored) < len(messages):
        out["truncated"] = True
    return out, remaining, dropped


def flow_to_record(
    flow, limits: SessionLimits, remaining: int
) -> tuple[dict, int, bool]:
    """单条 flow → 可 JSON 化的记录，返回 (record, 剩余预算, 是否有 body 被丢弃)。"""
    from addons.capture import CaptureAddon

    summary = dict(CaptureAddon.summarize(flow))
    req = getattr(flow, "request", None)
    res = getattr(flow, "response", None)
    ws = getattr(flow, "websocket", None)

    # 共享预算只约束**响应体**（响应体才是大头）。请求体只受单条上限约束：
    # 把 POST 的 payload 保住，恢复出来的会话才能原样重放。
    req_dict, _ = _encode_message(req, limits, limits.body_limit)
    if req is not None:
        req_dict["method"] = req.method
        req_dict["url"] = format_request_url(req)

    res_dict, remaining = _encode_message(res, limits, remaining)
    if res is not None:
        res_dict["status_code"] = getattr(res, "status_code", 0)
        res_dict["reason"] = getattr(res, "reason", "") or ""

    dropped = bool((res_dict or {}).get("body", {}).get("dropped"))
    ws_dict = None
    if ws is not None:
        ws_dict, remaining, ws_dropped = _encode_websocket(ws, limits, remaining)
        dropped = dropped or ws_dropped
    record = {
        "v": SESSION_VERSION,
        "summary": summary,
        "request": req_dict or None,
        "response": res_dict or None,
    }
    if ws_dict is not None:
        record["ws_messages"] = ws_dict
    # 服务端连接时间戳：耗时分析页（Fiddler Statistics 口径）的连接/TLS
    # 分段要靠它们算；不存的话恢复的会话只剩发送/等待/接收三段
    conn = getattr(flow, "server_conn", None)
    if conn is not None:
        record["server_conn"] = {
            "timestamp_start": getattr(conn, "timestamp_start", None),
            "timestamp_tcp_setup": getattr(conn, "timestamp_tcp_setup", None),
            "timestamp_tls_setup": getattr(conn, "timestamp_tls_setup", None),
        }
    return record, remaining, dropped


def save_session(path, flows, limits: SessionLimits | None = None) -> SaveResult:
    """把会话写成 JSONL（UTF-8）。原子替换：先写 .tmp 再 rename。

    `flows` 可为 flow 列表或任何可迭代对象；没有有效会话不落文件。
    """
    limits = limits or DEFAULT_LIMITS
    path = Path(path)
    result = SaveResult(path=path)

    items = [f for f in (flows or []) if f is not None]
    if not items:
        result.error = QCoreApplication.translate("session", "没有可保存的会话")
        return result

    tmp = path.with_name(path.name + ".tmp")
    remaining = limits.total_limit
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as fh:
            for flow in items:
                record, remaining, dropped = flow_to_record(flow, limits, remaining)
                if dropped:
                    result.bodies_dropped += 1
                if _is_truncated(record):
                    result.bodies_truncated += 1
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                result.count += 1
        os.replace(tmp, path)
        result.bytes_written = path.stat().st_size
    except (OSError, TypeError, ValueError) as e:
        # TypeError/ValueError：flow 里混进了非 JSON 序列化对象——
        # 不捕的话异常穿透 Qt slot，且 .tmp 文件留在磁盘上
        result.error = QCoreApplication.translate("session", '写入失败: {0}').format(e)
        _silent_unlink(tmp)
    except BaseException:
        _silent_unlink(tmp)
        raise
    return result


def _is_truncated(record: dict) -> bool:
    for key in ("request", "response"):
        if ((record.get(key) or {}).get("body") or {}).get("truncated"):
            return True
    ws = record.get("ws_messages")
    if isinstance(ws, dict) and ws.get("truncated"):
        return True
    for item in (ws or {}).get("messages") or []:
        if isinstance(item, dict) and (item.get("content") or {}).get("truncated"):
            return True
    return False


def _silent_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# ====================================================================== 读回


def _decode_body(body: dict) -> bytes:
    if not body or body.get("dropped"):
        return b""
    data = body.get("data") or ""
    if body.get("encoding") == "base64":
        try:
            return base64.b64decode(data)
        except (ValueError, TypeError):
            return b""
    return data.encode("utf-8")


def _header_fields(items) -> list[tuple[bytes, bytes]]:
    """[[k, v]] → [(bytes, bytes)]。

    `Request.make`/`Response.make` 的 `headers` 传 list 时要求**必须是 bytes**
    （传 dict 才会自动编码），所以这里显式编。用 latin-1 编解码：mitmproxy 的
    header 就是按 latin-1 呈现字节的，因此这条路对原始字节是无损可逆的；
    极端情况（header 里真有非 latin-1 字符）退回 UTF-8。
    """
    out: list[tuple[bytes, bytes]] = []
    for pair in items or []:
        try:
            k, v = pair
        except (TypeError, ValueError):
            continue
        try:
            out.append((str(k).encode("latin-1"), str(v).encode("latin-1")))
        except UnicodeEncodeError:
            out.append((str(k).encode("utf-8"), str(v).encode("utf-8")))
    return out


def _build_connections(url: str, summary: dict):
    """恢复会话的合成连接对象。

    为什么必须给：`Flow.copy()`（重放的根本）在 `get_state()` 里直接访问
    `self.client_conn.get_state()` 与 `self.server_conn.get_state()`，
    传 None 会 AttributeError——恢复出来的会话就重放不了。

    地址只是占位（真实对端早已断开），但 server_conn.peername 用会话里保存的
    服务端 IP，这样「服务器 IP」列语义与抓包时一致。
    """
    try:
        parsed = urlparse(url)
        scheme = (parsed.scheme or "http").lower()
        host = parsed.hostname or ""
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError:
        scheme, host, port = "http", "", 80

    ip = str(summary.get("server_ip") or "").strip()
    peer = (ip, port) if ip else ((host, port) if host else None)
    client = Client(peername=("127.0.0.1", 0), sockname=("127.0.0.1", 0))
    server = Server(
        address=peer,
        peername=peer,
        sockname=("127.0.0.1", 0),
        tls=(scheme == "https"),
    )
    return client, server


def _rebuild_websocket(ws_dict: dict):
    """记录里的 ws_messages → mitmproxy WebSocketData（消息逐条重建）。

    `type` 存的是 Opcode 的整数值（IntEnum，可直接 int→Opcode 还原）；
    老记录里若是字符串则回落 TEXT。`is_text` 等属性由 mitmproxy 自己从
    type 推导，重建后详情面板的 WebSocket 页与抓包时表现一致。
    """
    from mitmproxy.websocket import WebSocketData, WebSocketMessage

    messages = []
    for item in ws_dict.get("messages") or []:
        if not isinstance(item, dict):
            continue
        mtype = item.get("type")
        try:
            mtype = int(mtype)
        except (TypeError, ValueError):
            mtype = 1          # Opcode.TEXT
        messages.append(
            WebSocketMessage(
                type=mtype,
                from_client=bool(item.get("from_client")),
                content=_decode_body(item.get("content") or {}),
                timestamp=item.get("timestamp"),
            )
        )
    close_code = ws_dict.get("close_code")
    return WebSocketData(
        messages=messages,
        closed_by_client=ws_dict.get("closed_by_client"),
        close_code=int(close_code) if isinstance(close_code, int) else None,
        close_reason=str(ws_dict.get("close_reason") or "") or None,
        timestamp_end=ws_dict.get("timestamp_end"),
    )


def _record_to_flow(record: dict):
    """记录 → 重建的 HTTPFlow（可直接用于详情/重放/导出）。"""
    req_dict = record.get("request")
    if not isinstance(req_dict, dict):
        return None
    method = str(req_dict.get("method") or "GET")
    url = str(req_dict.get("url") or "")
    if not url:
        return None
    summary = record.get("summary") or {}
    req = Request.make(
        method,
        url,
        content=_decode_body(req_dict.get("body") or {}),
        headers=_header_fields(req_dict.get("headers")),
    )
    req.http_version = str(req_dict.get("http_version") or "HTTP/1.1")
    # 还原 authority（HTTP/2 的 :authority / HTTP/1 绝对形式目标）。
    # 会话只存了 headers，而 HTTP/2 的 :authority 既不在 headers 里、也没单独存；
    # Request.make 又不会从 URL 填 authority。结果恢复出来的请求成了「无 Host、
    # 无 :authority」的裸请求，重放时被上游网关直接判 400（实测 hq.yxzq.com
    # 返回 alibaba-ga 的 400 Bad Request）。补上后重放才与抓包时一致。
    ensure_request_authority(req)
    req.timestamp_start = req_dict.get("timestamp_start")
    req.timestamp_end = req_dict.get("timestamp_end")

    res_dict = record.get("response")
    res = None
    if isinstance(res_dict, dict):
        res = Response.make(
            int(res_dict.get("status_code") or 0),
            content=_decode_body(res_dict.get("body") or {}),
            headers=_header_fields(res_dict.get("headers")),
        )
        res.reason = str(res_dict.get("reason") or "")
        res.http_version = str(res_dict.get("http_version") or "HTTP/1.1")
        res.timestamp_start = res_dict.get("timestamp_start")
        res.timestamp_end = res_dict.get("timestamp_end")

    client, server = _build_connections(url, summary)
    # 服务端连接时间戳还原：耗时分析页的连接/TLS 分段需要（见 flow_to_record）
    conn_dict = record.get("server_conn")
    if isinstance(conn_dict, dict):
        for attr in ("timestamp_start", "timestamp_tcp_setup", "timestamp_tls_setup"):
            value = conn_dict.get(attr)
            if isinstance(value, (int, float)):
                setattr(server, attr, value)
    flow = HTTPFlow(client_conn=client, server_conn=server)
    flow.request = req
    flow.response = res
    # 标记与重放态一并还原：恢复出来的 mock 命中行照样是浅绿色 + MOCK 徽标
    try:
        flow.marked = str(summary.get("marked") or "")
        flow.is_replay = bool(summary.get("is_replay"))
        # 用户备注：mitmproxy 原生字段，保存/恢复天然一致
        flow.comment = str(summary.get("comment") or "")
    except Exception:
        log.debug("还原 flow 标记失败", exc_info=True)
    # WebSocket 消息重建：恢复出来的 WS 会话带完整消息列表（v1.11 前不入库）
    ws_dict = record.get("ws_messages")
    if isinstance(ws_dict, dict):
        try:
            flow.websocket = _rebuild_websocket(ws_dict)
        except Exception:
            log.debug("还原 WebSocket 消息失败", exc_info=True)
    return flow


def load_session(path) -> LoadResult:
    """读回会话；坏行跳过并计数，半截的最后一行不算错误。"""
    path = Path(path)
    result = LoadResult(path=path)
    if not path.exists():
        result.error = QCoreApplication.translate("session", "文件不存在")
        return result

    # 记录来自上一次保存的 summary：列表显示用（保证服务端 IP 等派生字段一致）
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    result.skipped += 1
                    continue
                if not isinstance(record, dict):
                    result.skipped += 1
                    continue
                if record.get("v") != SESSION_VERSION:
                    result.skipped += 1
                    continue
                # 单条记录重建失败（历史遗留的畸形 URL 等）只跳过这条：
                # 让它冒出去会把整份会话都打不开，用户看到的是「恢复失败」。
                try:
                    flow = _record_to_flow(record)
                except Exception:
                    log.debug("重建会话记录失败，跳过该条", exc_info=True)
                    result.skipped += 1
                    continue
                if flow is None:
                    result.skipped += 1
                    continue
                summary = record.get("summary")
                if not isinstance(summary, dict):
                    summary = {}
                # id 用重建后的 flow.id：详情面板/重放都靠 id 回查
                summary = dict(summary)
                summary["id"] = flow.id
                # WS 消息入库后（v1.11），行上的消息数要与**实际存下来的**一致：
                # 超条数/预算上限时 summary 记的是原始条数，直接显示会"点开没有"
                ws = getattr(flow, "websocket", None)
                if ws is not None:
                    stored = len(getattr(ws, "messages", []) or [])
                    summary["is_websocket"] = True
                    summary["ws_messages"] = stored
                    summary["ws_closed"] = bool(getattr(ws, "timestamp_end", None))
                result.flows.append(flow)
                result.summaries.append(summary)
    except OSError as e:
        result.error = QCoreApplication.translate("session", '读取失败: {0}').format(e)
        return result
    except UnicodeDecodeError as e:
        result.error = QCoreApplication.translate("session", '文件不是 UTF-8 文本会话文件: {0}').format(e)
        return result

    return result


# ====================================================================== 自动快照


def save_autosave(flows, limits: SessionLimits | None = None) -> SaveResult:
    """退出时写自动快照 + 元数据（元数据让下次启动不必读整包）。"""
    result = save_session(AUTOSAVE_PATH, flows, limits or AUTOSAVE_LIMITS)
    if result.ok:
        meta = {
            "v": SESSION_VERSION,
            "count": result.count,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "bytes": result.bytes_written,
        }
        try:
            AUTOSAVE_META_PATH.write_text(
                json.dumps(meta, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            log.debug("写快单元数据失败", exc_info=True)
    return result


def read_autosave_meta() -> dict | None:
    """读快单元数据；没有或损坏时返回 None。"""
    try:
        if not AUTOSAVE_META_PATH.exists():
            return None
        meta = json.loads(AUTOSAVE_META_PATH.read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or not meta.get("count"):
            return None
        if not AUTOSAVE_PATH.exists():
            return None
        return meta
    except (OSError, json.JSONDecodeError):
        return None


def archive_autosave() -> None:
    """不再恢复时归档快照，避免每次启动都弹询问。"""
    try:
        if AUTOSAVE_PATH.exists():
            os.replace(AUTOSAVE_PATH, ARCHIVE_PATH)
        AUTOSAVE_META_PATH.unlink(missing_ok=True)
    except OSError:
        log.debug("归档快照失败", exc_info=True)


def clear_autosave() -> None:
    """恢复成功后清掉快照。"""
    _silent_unlink(AUTOSAVE_PATH)
    _silent_unlink(AUTOSAVE_META_PATH)
    _silent_unlink(AUTOSAVE_PATH.with_name(AUTOSAVE_PATH.name + ".tmp"))
