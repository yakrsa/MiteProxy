"""请求重放：原样重放 + 编辑后重放（对齐 Fiddler Replay / Edit and Replay）。

实现路线：副本 + mitmproxy 官方 ClientPlayback.addon。
- 不动原始会话：start_replay 会改 is_replay 并清 response，所以必须传副本
  （Fiddler 语义：原会话保留，重放产生新会话）；
- 副本走完整代理生命周期，响应会再次触发 CaptureAddon，自动出现在流量列表。
"""

from __future__ import annotations

import uuid


def new_flow_id() -> str:
    return "r_" + uuid.uuid4().hex[:8]


def make_replay_copy(flow):
    """生成可重放的请求副本：深拷贝 + 新 id + 清响应/错误/标记。

    原 flow 完全不受影响。
    """
    copy = flow.copy()
    copy.id = new_flow_id()
    copy.response = None
    copy.error = None
    copy.marked = ""
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
    if headers is not None:
        req.headers.clear()
        for k, v in headers.items():
            if k:
                req.headers[k] = v
    if body is not None:
        req.content = body.encode("utf-8")
