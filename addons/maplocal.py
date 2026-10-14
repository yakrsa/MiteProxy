"""Map Local addon：把域名映射到本地目录，按路径取文件直接响应。

与 mitmproxy 自带 map_local 的区别：那是**单文件**映射（一条规则一个文件），
这里是**目录**映射（`static.prod.com/*` → `./static/*`，按 URL 路径找文件），
用于「线上前端 + 本地静态资源」这类整站搬迁场景。

语义（对齐 Fiddler 的 Map Local 但更克制）：
- 只拦 GET / HEAD（写请求映射到本地文件没有意义，也危险）；
- URL 路径 → 目录下的相对路径，**查询串丢弃**；
- 文件不存在 / 是目录（且没有 index.html）→ 不拦，透传上游；
- 路径穿越（`..`）与符号链接逃逸：resolve 后必须仍在目录内，否则拒;
- 单文件大小上限 100MB，超过按不存在处理（透传上游），不读半截。

线程模型：request 钩子在 asyncio 线程；set_entries 由 UI 线程调用，
整体替换列表（赋值原子），代理线程永远读到完整配置。
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from pathlib import Path

from mitmproxy import http

log = logging.getLogger(__name__)

#: 单文件大小上限：与 Mock 的文件响应一致（见 addons/mock.py）
LOCAL_FILE_LIMIT = 100 * 1024 * 1024

#: 目录请求兜底文件名
INDEX_FILE = "index.html"


class MapLocalAddon:
    def __init__(self, entries=None):
        #: [(compiled 前缀正则, 本地目录 Path)]，见 app/network.map_local_entries
        self._entries: list[tuple, Path] = list(entries or [])

    def set_entries(self, entries) -> None:
        """整体替换映射表（UI 线程调用；代理线程无锁读，赋值即原子）。"""
        self._entries = list(entries or [])

    # ------------------------------------------------------------ mitmproxy hook

    async def request(self, flow) -> None:
        if not self._entries:
            return
        if flow.request.method.upper() not in ("GET", "HEAD"):
            return
        url = flow.request.pretty_url
        for pattern, directory in self._entries:
            if not pattern.match(url):
                continue
            local = self._resolve_local(directory, flow.request.path)
            if local is None:
                # 没命中本地文件：不拦，走正常上游流程
                return
            try:
                await self._serve(flow, local)
            except Exception as e:
                # 本地读失败不该把请求打死——记日志后透传上游
                log.warning("map local 读取失败 %s: %s", local, e)
            return

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _resolve_local(directory: Path, url_path: str) -> Path | None:
        """URL 路径 → 本地文件；拒载时返回 None（调用方透传上游）。

        查询串丢弃（文件系统里没有 `?`）；目录请求试 index.html；
        resolve + is_relative_to 双保险，挡掉 `..` 与符号链接逃逸。
        """
        try:
            rel = url_path.split("?", 1)[0].lstrip("/")
            candidate = (directory / rel).resolve()
            base = directory.resolve()
        except (OSError, ValueError):
            return None
        if not candidate.is_relative_to(base):
            log.warning("map local 拒绝路径穿越: %s", url_path)
            return None
        if candidate.is_dir():
            candidate = candidate / INDEX_FILE
        try:
            if not candidate.is_file():
                return None
            if candidate.stat().st_size > LOCAL_FILE_LIMIT:
                log.warning("map local 文件超过上限，透传上游: %s", candidate)
                return None
        except OSError:
            return None
        return candidate

    @staticmethod
    async def _serve(flow, local: Path) -> None:
        data = await asyncio.to_thread(local.read_bytes)
        content_type = mimetypes.guess_type(str(local))[0] or "application/octet-stream"
        headers = {"Content-Type": content_type}
        # 文本类补 charset，与 Mock 一致（否则按 HTTP 默认 latin-1 解码会乱码）
        ctype = content_type.split(";", 1)[0].lower()
        if ctype.startswith("text/") or ctype.endswith("+json") or ctype == "application/json":
            if "charset" not in content_type.lower():
                headers["Content-Type"] = f"{content_type}; charset=utf-8"
        if flow.request.method.upper() == "HEAD":
            data = b""
        flow.response = http.Response.make(200, data, headers)
        flow.marked = f"LOCAL:{local.name}"
        log.info("map local 命中: %s -> %s", flow.request.pretty_url, local)
