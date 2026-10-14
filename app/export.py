"""会话导出与复制（DESIGN.md 3.2.3）：cURL 命令、原始报文、完整响应、HAR 1.2、响应 Body。

本模块只做**纯函数**（不依赖 Qt、不弹窗、不写文件），
弹窗与写盘由 UI 层负责——这样导出内容能被单测逐字断言。

所有构建函数都接受「单条 flow」或「flow 列表」：多选批量导出时，HAR 落成多 entry，
原始报文/完整响应按会话分段拼接（单条时的输出与以前逐字节一致）。
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.textutil import decode_body

APP_NAME = "MiteProxy"
APP_VERSION = "0.1"

FORMAT_HAR = "har"
FORMAT_RAW = "raw"
FORMAT_RESPONSE = "response"
FORMAT_BODY = "body"
EXPORT_FORMATS = (FORMAT_HAR, FORMAT_RAW, FORMAT_RESPONSE, FORMAT_BODY)

#: 这些格式必须有响应才有内容可导出（UI 层据此给出友好提示）
REQUIRES_RESPONSE = (FORMAT_RESPONSE, FORMAT_BODY)

FORMAT_LABELS = {
    FORMAT_HAR: "HAR 归档 (*.har)",
    FORMAT_RAW: "原始 HTTP 报文：请求+响应 (*.txt)",
    FORMAT_RESPONSE: "完整响应：Headers+Body (*.txt)",
    FORMAT_BODY: "仅响应 Body (*.*)",
}

# content-type → 扩展名（响应 Body 导出时推断文件名）
CONTENT_TYPE_EXT = {
    "application/json": ".json",
    "application/xml": ".xml",
    "application/javascript": ".js",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/octet-stream": ".bin",
    "text/html": ".html",
    "text/plain": ".txt",
    "text/css": ".css",
    "text/xml": ".xml",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
}

_TEXTUAL_TYPES = (
    "text/",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-www-form-urlencoded",
    "application/graphql",
    "application/x-ndjson",
    "application/ld+json",
)


# ====================================================================== 多会话（批量导出）

#: 多选导出时不允许的格式（一个文件装不下多份裸 body）
SINGLE_ONLY_FORMATS = (FORMAT_BODY,)


def as_flow_list(flows) -> list:
    """把「单条 flow」或「flow 列表」统一成列表（过滤 None）。"""
    if flows is None:
        return []
    if isinstance(flows, (list, tuple)):
        return [f for f in flows if f is not None]
    return [flows]


def session_banner(index: int, total: int, flow) -> str:
    """多条会话拼接时的分隔标题，例如 `########## 会话 2/3 · GET https://a/b ##########`。"""
    return f"########## 会话 {index}/{total} · {session_banner_labels(flow)} ##########"


# ====================================================================== 通用取值


def _headers_items(msg) -> list[tuple[str, str]]:
    if msg is None:
        return []
    try:
        return [(str(k), str(v)) for k, v in msg.headers.items(multi=True)]
    except Exception:
        return []


def _header_value(msg, name: str) -> str:
    if msg is None:
        return ""
    try:
        return str(msg.headers.get(name, "") or "")
    except Exception:
        return ""


def content(msg) -> bytes:
    """消息 body 原始字节（取不到返回空）。"""
    if msg is None:
        return b""
    try:
        return msg.get_content(strict=False) or b""
    except Exception:
        try:
            return msg.raw_content or b""
        except Exception:
            return b""


def content_type_of(msg) -> str:
    return _header_value(msg, "content-type")


def is_textual(content_type: str) -> bool:
    ct = (content_type or "").lower()
    if not ct:
        return False
    return any(ct.startswith(t) for t in _TEXTUAL_TYPES)


def decode_text(msg) -> str | None:
    """body 解码为文本；二进制返回 None。"""
    data = content(msg)
    if not data:
        return ""
    text = decode_body(data, content_type_of(msg))
    if text is None:
        return None
    if not is_textual(content_type_of(msg)):
        # 未声明文本类型但能按 UTF-8 解出来（如无 content-type 的 JSON），
        # 只要没有控制字符就当作文本，否则转 base64 更安全
        if any(ch < " " and ch not in "\r\n\t" for ch in text):
            return None
    return text


# ====================================================================== cURL


def _quote(value: str, style: str) -> str:
    """shell 引号：posix 用单引号（' 转义为 '\\''），cmd 用双引号（" 转义为 \\"）。"""
    if style == "cmd":
        return '"' + value.replace('"', '\\"') + '"'
    return "'" + value.replace("'", "'\\''") + "'"


BINARY_BODY_PLACEHOLDER = "payload.bin"


def build_curl(flow, style: str = "posix") -> str:
    """把选中会话的**请求**拼成一条可直接执行的 curl 命令。

    - 跳过 HTTP/2 伪头（`:method` 等）与 `Host`（curl 自己带）；
    - 非 GET 才输出 `-X`，避免冗余；
    - body 用 `--data-binary`：保留原始字节，不会像 `-d` 那样吞换行/把 `@` 当文件；
    - 文本 body 内联，二进制 body 退化为 `@payload.bin`（配合「仅响应 Body」导出用）；
    - `style="cmd"` 生成 Windows cmd 单行版（值统一双引号）。
    """
    req = getattr(flow, "request", None)
    if req is None:
        return ""
    parts = ["curl"]
    method = getattr(req, "method", "GET") or "GET"
    if method.upper() != "GET":
        parts += ["-X", method]
    parts.append(_quote(getattr(req, "pretty_url", "") or "", style))

    for k, v in _headers_items(req):
        if k.startswith(":") or k.lower() == "host":
            continue
        parts += ["-H", _quote(f"{k}: {v}", style)]

    body = content(req)
    if body:
        text = decode_text(req)
        if text is None:
            parts += ["--data-binary", _quote(f"@{BINARY_BODY_PLACEHOLDER}", style)]
        else:
            parts += ["--data-binary", _quote(text, style)]
    return " ".join(parts)


def build_curl_many(flows, style: str = "posix") -> str:
    """批量复制：每条会话一行 curl，前面加一行注释标出是哪条会话。

    注释符按 shell 走（bash `#` / cmd `REM`）。多行贴进终端不会自动连续执行，
    这份产物主要是给缺陷单、文档、脚本用的；单条时输出与 `build_curl` 一致。
    """
    items = as_flow_list(flows)
    if not items:
        return ""
    if len(items) == 1:
        return build_curl(items[0], style)
    prefix = "REM" if style == "cmd" else "#"
    lines: list[str] = []
    for i, f in enumerate(items, 1):
        cmd = build_curl(f, style)
        if not cmd:
            continue
        lines.append(f"{prefix} 会话 {i}/{len(items)} · {session_banner_labels(f)}")
        lines.append(cmd)
    return "\n".join(lines)


def session_banner_labels(flow) -> str:
    """`GET https://a/b` 形式的会话标识（批量注释用）。"""
    req = getattr(flow, "request", None)
    method = getattr(req, "method", "") or ""
    return f"{method} {getattr(req, 'pretty_url', '') or ''}".strip()


# ====================================================================== 原始报文


def _raw_message(start_line: str, msg, body: bytes) -> list[str]:
    lines = [start_line]
    lines += [f"{k}: {v}" for k, v in _headers_items(msg)]
    text = decode_text(msg)
    if body:
        if text is None:
            lines.append("")
            lines.append(f"<二进制 body：{len(body)} 字节，未内联；请用「仅响应 Body」导出>")
        else:
            lines.append("")
            lines.append(text)
    return lines


def build_raw(flow) -> str:
    """Fiddler「Save → Raw」风格：请求与响应两段完整报文（含 body）。

    传入列表时按会话分段拼接，每段前面加一行分隔标题。
    """
    items = as_flow_list(flow)
    if len(items) == 1:
        return _build_raw_one(items[0])
    if not items:
        return ""
    blocks = []
    for i, f in enumerate(items, 1):
        one = _build_raw_one(f)
        if one:
            blocks.append(session_banner(i, len(items), f) + "\n" + one.rstrip("\n"))
    return "\n\n".join(blocks) + "\n" if blocks else ""


def _build_raw_one(flow) -> str:
    req = getattr(flow, "request", None)
    res = getattr(flow, "response", None)
    blocks: list[str] = []

    if req is not None:
        path = getattr(req, "path", "") or ""
        version = getattr(req, "http_version", "") or "HTTP/1.1"
        req_body = content(req)
        blocks.append(
            "\n".join(
                _raw_message(
                    f"{getattr(req, 'method', '')} {path} {version}".strip(),
                    req,
                    req_body,
                )
            )
        )
    if res is not None:
        version = getattr(res, "http_version", "") or "HTTP/1.1"
        status = getattr(res, "status_code", 0)
        reason = getattr(res, "reason", "") or ""
        blocks.append(
            "\n".join(
                _raw_message(f"{version} {status} {reason}".strip(), res, content(res))
            )
        )

    divider_req = "===== 请求 ====="
    divider_res = "===== 响应 ====="
    text = ""
    if req is not None:
        text += divider_req + "\n" + blocks[0] + "\n\n"
    if res is not None:
        text += divider_res + "\n" + blocks[-1] + "\n"
    if not text:
        return ""
    return text.rstrip("\n") + "\n"


# ====================================================================== 完整响应
#
# 对齐 Fiddler 的「Save → Response → Entire Response」：响应起始行 + 全部 headers
# + 空行 + body。与「原始 HTTP 报文」的区别是**只含响应、不含请求**；
# 与「仅响应 Body」的区别是**带 header**。

RESPONSE_LINE_SEP = b"\r\n"


def build_response(flow) -> bytes:
    """响应完整报文（bytes）。

    以 bytes 而非 str 返回：header 是 ASCII 文本，body 直接拼**原始字节**，
    二进制响应不会被重新编码或损坏。

    - 头部按 HTTP 线格式用 CRLF 分隔，末尾空行后紧跟 body；
    - 无响应（会话进行中 / 连接被中断）返回 `b""`；
    - body 为空时文件以头部的结束空行收尾；
    - 传入列表时按会话分段拼接，每段前加一行 CRLF 分隔标题。
    """
    items = as_flow_list(flow)
    if len(items) <= 1:
        return _build_response_one(items[0]) if items else b""
    blocks = []
    for i, f in enumerate(items, 1):
        one = _build_response_one(f)
        if one:
            banner = session_banner(i, len(items), f).encode("utf-8")
            blocks.append(banner + RESPONSE_LINE_SEP * 2 + one)
    return (RESPONSE_LINE_SEP * 2).join(blocks)


def _build_response_one(flow) -> bytes:
    res = getattr(flow, "response", None)
    if res is None:
        return b""

    version = getattr(res, "http_version", "") or "HTTP/1.1"
    status = getattr(res, "status_code", 0)
    reason = getattr(res, "reason", "") or ""
    start_line = f"{version} {status} {reason}".strip()

    lines = [start_line] + [f"{k}: {v}" for k, v in _headers_items(res)]
    head = RESPONSE_LINE_SEP.join(line.encode("utf-8") for line in lines)
    return head + RESPONSE_LINE_SEP * 2 + content(res)


# ====================================================================== HAR


def _iso_time(ts: float | None) -> str:
    if not ts:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _har_timings(req, res) -> dict:
    """send / wait / receive 三段耗时（ms）。

    mitmproxy 有完整时间戳：请求上传、服务端思考、响应下载。合成会话
    （Request.make 造的）没有这些值，退化为「全部算 wait」。
    """

    def ms(a, b):
        if a and b and b >= a:
            return round((b - a) * 1000, 1)
        return None

    send = ms(getattr(req, "timestamp_start", None), getattr(req, "timestamp_end", None))
    wait = ms(getattr(req, "timestamp_end", None), getattr(res, "timestamp_start", None))
    receive = ms(getattr(res, "timestamp_start", None), getattr(res, "timestamp_end", None))
    if send is None or wait is None or receive is None:
        total = ms(getattr(req, "timestamp_start", None), getattr(res, "timestamp_end", None))
        return {"send": 0, "wait": total if total is not None else 0, "receive": 0}
    return {"send": send, "wait": wait, "receive": receive}


def _har_cookies(msg) -> list[dict]:
    out = []
    try:
        for name, value in msg.cookies.items():
            out.append({"name": str(name), "value": str(value)})
    except Exception:
        return []
    return out


def _har_headers(msg) -> list[dict]:
    return [{"name": k, "value": v} for k, v in _headers_items(msg)]


def _har_query(req) -> list[dict]:
    out = []
    try:
        for name, value in req.query.items():
            out.append({"name": str(name), "value": str(value)})
    except Exception:
        return []
    return out


def build_har_entry(flow) -> dict:
    """单条会话的 HAR 1.2 entry。"""
    req = flow.request
    res = getattr(flow, "response", None)
    req_body = content(req)
    timings = _har_timings(req, res)
    total = round(sum(timings.values()), 1)

    request: dict = {
        "method": req.method,
        "url": getattr(req, "pretty_url", "") or "",
        "httpVersion": getattr(req, "http_version", "") or "HTTP/1.1",
        "cookies": _har_cookies(req),
        "headers": _har_headers(req),
        "queryString": _har_query(req),
        "headersSize": -1,
        "bodySize": len(req_body),
    }
    if req_body:
        text = decode_text(req)
        post_data: dict = {"mimeType": content_type_of(req) or "application/octet-stream"}
        if text is None:
            post_data["text"] = base64.b64encode(req_body).decode("ascii")
            post_data["encoding"] = "base64"
        else:
            post_data["text"] = text
        request["postData"] = post_data

    entry: dict = {
        "startedDateTime": _iso_time(getattr(req, "timestamp_start", None)),
        "time": total,
        "request": request,
    }

    if res is not None:
        res_body = content(res)
        ct = content_type_of(res)
        res_text = decode_text(res)
        res_content: dict = {"size": len(res_body), "mimeType": ct or ""}
        if res_body:
            if res_text is None:
                res_content["text"] = base64.b64encode(res_body).decode("ascii")
                res_content["encoding"] = "base64"
            else:
                res_content["text"] = res_text
        entry["response"] = {
            "status": getattr(res, "status_code", 0),
            "statusText": getattr(res, "reason", "") or "",
            "httpVersion": getattr(res, "http_version", "") or "HTTP/1.1",
            "cookies": _har_cookies(res),
            "headers": _har_headers(res),
            "content": res_content,
            "redirectURL": _header_value(res, "location"),
            "headersSize": -1,
            "bodySize": len(res_body),
        }
    else:
        entry["response"] = {
            "status": 0,
            "statusText": "",
            "httpVersion": "",
            "cookies": [],
            "headers": [],
            "content": {"size": 0, "mimeType": ""},
            "redirectURL": "",
            "headersSize": -1,
            "bodySize": 0,
        }

    entry["cache"] = {}
    entry["timings"] = timings
    if res is not None and getattr(res, "timestamp_end", None):
        entry["serverIPAddress"] = _server_ip(flow)
    if getattr(flow, "marked", ""):
        entry["comment"] = str(flow.marked)
    return entry


def _server_ip(flow) -> str:
    try:
        conn = getattr(flow, "server_conn", None)
        peername = getattr(conn, "peername", None)
        if isinstance(peername, (tuple, list)) and peername:
            return str(peername[0])
    except Exception:
        pass
    return ""


def build_har(flow) -> dict:
    """完整 HAR 1.2 文档。

    传入列表时落成多 entry（HAR 天然支持，浏览器 DevTools / Charles / Fiddler
    都能一次打开整包）；单条时行为与以前一致。
    """
    items = as_flow_list(flow)
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": APP_NAME, "version": APP_VERSION},
            "pages": [],
            "entries": [build_har_entry(f) for f in items],
        }
    }


def build_har_json(flow) -> str:
    return json.dumps(build_har(flow), ensure_ascii=False, indent=2)


# ====================================================================== 响应 Body


def _ext_from_content_type(content_type: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in CONTENT_TYPE_EXT:
        return CONTENT_TYPE_EXT[ct]
    # jsonp / vnd.api+json 之类：取 + 后缀
    if "+" in ct and ct.split("+")[-1] in ("json", "xml"):
        return "." + ct.split("+")[-1]
    if ct.startswith("text/"):
        return ".txt"
    if ct.startswith("image/"):
        return "." + ct.split("/")[-1]
    return ""


def body_filename(flow) -> str:
    """响应 Body 的建议文件名：URL 末段优先，无扩展名时按 content-type 补。"""
    res = getattr(flow, "response", None)
    req = getattr(flow, "request", None)
    path = urlparse(getattr(req, "pretty_url", "") or "").path
    name = path.rsplit("/", 1)[-1]
    name = re.sub(r"[^\w.\-]+", "_", name).strip("._")
    ext = _ext_from_content_type(content_type_of(res))
    if not name:
        return "body" + (ext or ".bin")
    if "." not in name:
        name += ext
    return name


def default_filename(flow, fmt: str) -> str:
    """导出对话框的默认文件名。传列表时按第一条起名并带上条数。"""
    items = as_flow_list(flow)
    first = items[0] if items else flow
    suffix = f"_{len(items)}条" if len(items) > 1 else ""

    if fmt == FORMAT_BODY:
        name = body_filename(first)
        if suffix:
            stem, dot, ext = name.rpartition(".")
            name = f"{stem}{suffix}.{ext}" if dot else name + suffix
        return name
    req = getattr(first, "request", None)
    host = getattr(req, "pretty_host", "") or "session"
    path = urlparse(getattr(req, "pretty_url", "") or "").path
    slug = re.sub(r"[^\w.\-]+", "_", f"{host}{path}").strip("_")
    slug = (slug[:60] or "session") + suffix
    if fmt == FORMAT_HAR:
        return slug + ".har"
    if fmt == FORMAT_RESPONSE:
        # 与「原始 HTTP 报文」的 .txt 区分开，避免同名覆盖
        return slug + ".response.txt"
    return slug + ".txt"


def ensure_suffix(path: str, fmt: str, flow) -> str:
    """补齐扩展名：HAR→.har，原始报文/完整响应→.txt，Body→按 content-type 推断。

    `flow` 可以是列表（取第一个推 content-type）。
    """
    items = as_flow_list(flow)
    first = items[0] if items else flow
    if fmt == FORMAT_HAR:
        ext = ".har"
    elif fmt in (FORMAT_RAW, FORMAT_RESPONSE):
        ext = ".txt"
    else:
        ext = _ext_from_content_type(content_type_of(getattr(first, "response", None)))
    base = path.rsplit("/", 1)[-1]
    if ext and not base.lower().endswith(ext):
        if base.lower().endswith((".har", ".txt", ".json", ".html", ".xml")) and fmt == FORMAT_BODY:
            return path          # 用户自己写了扩展名，尊重
        return path + ext
    return path


def name_filters() -> tuple[str, dict[str, str]]:
    """QFileDialog 的过滤器串 + 「过滤器 → 格式」映射（UI 层用）。"""
    items = [(FORMAT_LABELS[f], f) for f in EXPORT_FORMATS]
    return ";;".join(label for label, _ in items), {label: f for label, f in items}


def export_bytes(flow, fmt: str) -> bytes:
    """导出内容（bytes）；文本格式统一 UTF-8 编码。

    `flow` 传列表即为多选批量导出：HAR 落多 entry，原始报文/完整响应分段拼接；
    「仅响应 Body」只能单条（由 UI 提前拦下）。
    """
    if fmt == FORMAT_HAR:
        return build_har_json(flow).encode("utf-8")
    if fmt == FORMAT_RAW:
        return build_raw(flow).encode("utf-8")
    if fmt == FORMAT_RESPONSE:
        return build_response(flow)
    if fmt == FORMAT_BODY:
        items = as_flow_list(flow)
        if len(items) != 1:
            raise ValueError("「仅响应 Body」只支持导出单条会话")
        return content(getattr(items[0], "response", None))
    raise ValueError(f"未知导出格式: {fmt}")
