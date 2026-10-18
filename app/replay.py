"""请求重放：原样重放 + 编辑后重放（对齐 Fiddler Replay / Edit and Replay）。

实现路线：副本 + mitmproxy 官方 ClientPlayback.addon。
- 不动原始会话：start_replay 会改 is_replay 并清 response，所以必须传副本
  （Fiddler 语义：原会话保留，重放产生新会话）；
- 副本走完整代理生命周期，响应会再次触发 CaptureAddon，自动出现在流量列表。
"""

from __future__ import annotations

import uuid

#: 各 scheme 的默认端口：authority 拼装时省略默认端口（`hq.yxzq.com` 而非
#: `hq.yxzq.com:443`），与 HTTP/2 的 `:authority` 惯例一致。
_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}


def new_flow_id() -> str:
    return "r_" + uuid.uuid4().hex[:8]


def _format_authority(host: str, port: int, scheme: str) -> str:
    """把 host/port 拼成 authority，IPv6 字面量加方括号。

    mitmproxy 的 ``Request.host`` 对 IPv6 返回不带方括号的裸地址（``::1``），
    直接拼 ``::1:8080`` 会得到畸形 authority，重放时 URL 变成
    ``http://::1:8080/x`` 无法解析。必须还原成 ``[::1]:8080``。
    """
    formatted = host.strip()
    if ":" in formatted and not formatted.startswith("["):
        formatted = f"[{formatted}]"
    default_port = _DEFAULT_PORTS.get(scheme, 80)
    return formatted if port == default_port else f"{formatted}:{port}"


def format_request_url(request) -> str:
    """请求的完整 URL，IPv6 主机带方括号。

    mitmproxy 的 ``pretty_url`` 由**裸 host** 拼装、不加方括号，IPv6 请求会得到
    ``http://::1:8080/x`` 这种无法再被解析的畸形 URL。三个实际后果：

    - 会话存档用它 → 恢复时 ``Request.make`` 抛 ``ValueError``（实测
      ``No hostname given`` / ``Port could not be cast to integer``），
      整份会话加载失败；
    - 导出 curl 是坏的，粘到终端连不上；
    - 「带入 API 调试」直接报 URL 非法。

    所以凡是把请求 URL 交给外部（存盘 / 导出 / 再解析）的地方都用它，
    不要直接用 ``pretty_url``。
    """
    url = getattr(request, "pretty_url", "") or ""
    host = getattr(request, "pretty_host", "") or ""
    # 非 IPv6（绝大多数情况）原样返回；带方括号说明 mitmproxy 已经拼对了
    if not url or ":" not in host or host.startswith("["):
        return url
    scheme = (request.scheme or "http").lower()
    prefix = f"{scheme}://"
    if url.startswith(prefix):
        netloc = url[len(prefix):].split("/", 1)[0]
        if netloc.startswith("["):
            return url
    netloc = _format_authority(host, request.port, scheme)
    path = request.path or "/"
    if path == "*":                       # CONNECT/OPTIONS * 不是真实路径
        path = "/"
    return f"{scheme}://{netloc}{path}"


def ensure_request_authority(request) -> None:
    """为重放补齐 ``request.authority``（HTTP/2 的 ``:authority`` / HTTP/1 绝对形式目标）。

    为什么必须补：mitmproxy 的 ``Request.make`` 只从 URL 填 host/port/path/scheme，
    **不填 authority**；而 HTTP/2 的 ``:authority`` 伪头既不在 ``headers`` 里，
    会话文件也没有单独保存。于是「会话恢复出来的 flow」和「用 URL 重建的请求」
    都是 authority 为空的裸请求——重放时既没有 Host 也没有 ``:authority``，
    上游网关会直接判 400（实测 hq.yxzq.com 返回 alibaba-ga 的 400 Bad Request）。

    只在该补的时候补：
    - ``authority`` 已有值 → 不动；
    - HTTP/1 且带 ``Host`` 头 → 保持 origin-form 原样（不改绝对形式）；
    - 其余（HTTP/2，或 HTTP/1 缺 Host）→ 按 host[:port] 补上。
    """
    if request.authority:
        return
    http_version = getattr(request, "http_version", "") or ""
    if not http_version.startswith("HTTP/2") and request.headers.get("host"):
        return
    host = getattr(request, "host", "") or ""
    if not host:
        return
    scheme = (request.scheme or "http").lower()
    request.authority = _format_authority(host, request.port, scheme)


def make_replay_copy(flow):
    """生成可重放的请求副本：深拷贝 + 新 id + 清响应/错误/标记。

    原 flow 完全不受影响。
    """
    copy = flow.copy()
    copy.id = new_flow_id()
    copy.response = None
    copy.error = None
    copy.marked = ""
    # 会话恢复 / 手工构造的 flow 可能缺 authority，直接重放会被上游判 400，
    # 见 ensure_request_authority 的说明。
    ensure_request_authority(copy.request)
    return copy


def apply_request_edits(
    flow,
    method: str | None = None,
    url: str | None = None,
    headers: dict | None = None,
    body: str | None = None,
) -> None:
    """把编辑结果应用到副本的 request 上。headers 为 None 表示不动；
    传 dict（含空 dict）表示整体替换。"""
    req = flow.request
    if method:
        req.method = method.upper()
    if url:
        req.url = url
        # 改 URL 会重设 host/port/path，但 authority 仍是旧的（甚至为空）——
        # 不同步的话重放会用陈旧/缺失的 :authority 发请求，上游照样 400。
        req.authority = ""
        ensure_request_authority(req)
    if headers is not None:
        req.headers.clear()
        for k, v in headers.items():
            if k:
                req.headers[k] = v
        # 用户可能把 Host 头删了：补回 authority，别让重放变成无 Host 的裸请求
        ensure_request_authority(req)
    if body is not None:
        req.content = body.encode("utf-8")
