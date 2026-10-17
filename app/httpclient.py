"""API 调试的 HTTP 客户端（app/httpclient.py，纯函数层可单测）。

设计约束：
- 阻塞式、后台线程调用（UI 层用线程 + 信号回主线程，见 api_panel）；
- 独立于代理直发目标服务器——调试工具语义（像 Postman），响应不进流量列表；
- 默认跳过证书校验：调试对象常是自签 / 内网证书，校验失败是常态不是异常；
- body 全程按字节处理，文本编解码交 UI 层；
- 不跟随重定向（3xx 原样返回，调试要看到 302 本身而不是终点）。
"""

from __future__ import annotations

import http.client
import ssl
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from PySide6.QtCore import QCoreApplication

#: 响应体读取上限：调试工具不是下载器，500MB 兜底防把内存吃光
MAX_BODY_BYTES = 500 * 1024 * 1024


@dataclass
class ApiResponse:
    ok: bool
    status: int = 0
    reason: str = ""
    headers: list = field(default_factory=list)  # [(name, value)] 保序、保重复
    body: bytes = b""
    elapsed_ms: int = 0
    url: str = ""
    error: str = ""


def send_request(
    method: str,
    url: str,
    headers: dict | None = None,
    body: bytes = b"",
    timeout: float = 30.0,
    verify: bool = False,
) -> ApiResponse:
    """发送一个请求并读完响应。任何失败都收敛成 ApiResponse(ok=False)——
    异常往外抛就是把线程打死，UI 只会看到线程消失。"""
    start = time.monotonic()

    def fail(msg: str) -> ApiResponse:
        return ApiResponse(
            ok=False, url=url, error=msg,
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )

    method = (method or "GET").strip().upper() or "GET"
    url = (url or "").strip()
    if not url:
        return fail(QCoreApplication.translate("httpclient", "URL 不能为空"))
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return fail(QCoreApplication.translate("httpclient", "URL 必须以 http:// 或 https:// 开头"))
    host = parts.hostname
    if not host:
        return fail(QCoreApplication.translate("httpclient", "URL 缺少主机名"))
    port = parts.port or (443 if parts.scheme == "https" else 80)
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query

    try:
        if parts.scheme == "https":
            ctx = ssl.create_default_context()
            if not verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            conn: http.client.HTTPConnection = http.client.HTTPSConnection(
                host, port, timeout=timeout, context=ctx
            )
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)

        send_headers = {str(k): str(v) for k, v in (headers or {}).items() if k}
        # 非 GET/HEAD 即使 body 为空也要带 Content-Length: 0——body 传 None 时
        # http.client 不补这个头，严格服务器回 411，更多服务器干等直到超时
        if body or method not in ("GET", "HEAD"):
            send_body: bytes | None = body if body else b""
        else:
            send_body = None
        try:
            conn.request(method, target, body=send_body, headers=send_headers)
            resp = conn.getresponse()
            data = resp.read(MAX_BODY_BYTES + 1)
            if len(data) > MAX_BODY_BYTES:
                return fail(QCoreApplication.translate("httpclient", '响应体超过 {0}MB 上限').format(MAX_BODY_BYTES // (1024 * 1024)))
            return ApiResponse(
                ok=True,
                status=resp.status,
                reason=resp.reason or "",
                headers=list(resp.getheaders()),
                body=data,
                elapsed_ms=int((time.monotonic() - start) * 1000),
                url=url,
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except OSError as e:
        return fail(QCoreApplication.translate("httpclient", '连接失败: {0}').format(e))
    except Exception as e:  # ssl.SSLError / http.client 各类异常统一收敛
        return fail(QCoreApplication.translate("httpclient", '请求失败: {0}').format(e))
