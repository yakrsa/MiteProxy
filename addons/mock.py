"""Mock addon：request hook 命中规则即造 response，请求不发给真实服务器。

实现路线与 mitmproxy 官方 map-local 一致：在 request 阶段设置 flow.response，
mitmproxy 发现 response 已存在便不再连接上游。

重定向模式（Action.redirect_url 非空）走另一条路：改写请求 URL 后**不造
response**，让 mitmproxy 继续把请求发到新上游，把真实响应原样带回——
规则级 Map Remote，对客户端透明。
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from mitmproxy import http

from app.rules import Rule, RuleStore

log = logging.getLogger(__name__)

FILE_SIZE_LIMIT = 100 * 1024 * 1024  # 本地文件大小上限 100MB（见 3.3.1）
REDIRECT_LOOP_LIMIT = 10  # 单请求最多重定向次数（防规则互指打死代理）


class MockAddon:
    def __init__(self, rule_store: RuleStore, proxy_addr: tuple[str, int] | None = None):
        self.rules = rule_store
        self.proxy_addr = proxy_addr  # (host, port)，用于拦"重定向指回本代理"的死循环

    def _mark(self, rule: Rule) -> str:
        """流量列表备注徽标：MOCK#序号:规则名（序号 = 规则列表当前顺序，1 起）。

        序号跟随拖拽排序实时变化，用户能直接对上规则页第几条。
        """
        seq = self.rules.index_of(rule.id)
        return f"MOCK#{seq}:{rule.name}" if seq else f"MOCK:{rule.name}"

    # ------------------------------------------------------------ mitmproxy hook

    async def request(self, flow) -> None:
        rule, m = self.rules.find_rule(
            flow.request.pretty_url, flow.request.method
        )
        if rule is None:
            return
        self.rules.record_hit(rule.id)  # 命中计数（轻量，供规则页显示）
        action = rule.action

        if action.latency_ms > 0:
            # 非阻塞 sleep：延迟期间其他连接不受影响（见 3.3.2）
            await asyncio.sleep(action.latency_ms / 1000.0)

        # ---- 重定向模式：改写 URL 放行到新上游（status/headers/body 不生效）
        if action.redirect_url:
            if self._apply_redirect(flow, rule, m):
                return
            # 改写失败（目标非法 / 循环）→ 明确的 502 说明，不用规则配置的 body 兜底
            flow.response = http.Response.make(
                502,
                b"mock redirect failed: target invalid or redirect loop",
                {"Content-Type": "text/plain; charset=utf-8"},
            )
            flow.marked = self._mark(rule)
            return

        try:
            status, headers, body = await self._build_response(rule, m, flow)
        except Exception as e:
            log.exception("mock 规则 %s 执行失败", rule.id)
            self.rules.set_rule_error(rule.id, f"执行失败: {e}")
            status, headers, body = (
                502,
                {"Content-Type": "text/plain; charset=utf-8"},
                f"mock rule error: {e}".encode("utf-8"),
            )
        else:
            self.rules.set_rule_error(rule.id, None)

        flow.response = http.Response.make(status, body, headers)
        flow.marked = self._mark(rule)
        log.info("mock 命中: %s -> %s %s", flow.request.pretty_url, rule.name, status)

    # ------------------------------------------------------------ 重定向

    def _apply_redirect(self, flow, rule: Rule, m: Optional[re.Match]) -> bool:
        """把请求改发到规则目标 URL。True = 已改写放行；False = 判定不能改写。

        目标 URL 支持 $1 命名/数字组替换（与 body 同一套语义）。
        两道循环保护：
        - 拦截指向**本代理监听地址**的目标——那会让每一跳都生成新 flow
          （request 钩子对同一条 flow 只跑一次，flow.metadata 计数管不到新 flow），
          请求将在代理里无限转圈；
        - flow.metadata 计数兜底（同 flow 内理论上只走一次，防御未来行为变化）。
        """
        target = self._substitute(rule.action.redirect_url, m).strip()
        if not target:
            self.rules.set_rule_error(rule.id, "重定向目标为空")
            return False
        if not (target.startswith("http://") or target.startswith("https://")):
            self.rules.set_rule_error(rule.id, f"重定向目标必须是 http(s) URL: {target}")
            return False
        if self._points_at_proxy(target):
            self.rules.set_rule_error(
                rule.id,
                f"重定向目标指向本代理 {self.proxy_addr[0]}:{self.proxy_addr[1]}，"
                "会造成死循环，已拒绝执行",
            )
            return False

        count = int(flow.metadata.get("mpf_redirect_count", 0)) + 1
        if count > REDIRECT_LOOP_LIMIT:
            self.rules.set_rule_error(
                rule.id, f"重定向循环（超过 {REDIRECT_LOOP_LIMIT} 次），已中断"
            )
            return False
        flow.metadata["mpf_redirect_count"] = count

        original = flow.request.pretty_url
        flow.request.url = target
        flow.marked = self._mark(rule)
        self.rules.set_rule_error(rule.id, None)
        log.info("mock 重定向: %s -> %s", original, target)
        return True

    def _points_at_proxy(self, target: str) -> bool:
        """目标的主机端口是否就是本代理（host 匹配 127.0.0.1/localhost/本机名）。"""
        if not self.proxy_addr:
            return False
        try:
            parts = urlsplit(target)
            port = parts.port or (443 if parts.scheme == "https" else 80)
            if port != self.proxy_addr[1]:
                return False
            return parts.hostname in ("127.0.0.1", "localhost", "::1", "0.0.0.0")
        except ValueError:
            return False

    # ------------------------------------------------------------ 响应构造

    async def _build_response(
        self, rule: Rule, m: Optional[re.Match], flow
    ) -> tuple[int, dict, bytes]:
        action = rule.action
        headers = dict(action.headers)

        if action.body_source == "file":
            file_path = self._substitute(action.file_path or "", m)
            body, detected_type = await self._read_file(rule, file_path)
        else:
            body = self._substitute(action.body or "", m).encode("utf-8")
            detected_type = None

        # Content-Type：规则显式指定优先；文件模式未指定时按扩展名推断（见 3.3.1）
        if detected_type and not _has_content_type(headers):
            headers["Content-Type"] = detected_type

        # 文本类响应补 charset=utf-8：否则 text/plain 会按 HTTP 默认 latin-1 解码，
        # 中文 body 在客户端/读取端出现乱码（mitmproxy get_text 即此行为）
        headers = _ensure_charset(headers)

        # headers 值也做 $1 替换（如 Location）
        headers = {k: self._substitute(v, m) for k, v in headers.items()}
        return action.status, headers, body

    async def _read_file(self, rule: Rule, file_path: str) -> tuple[bytes, Optional[str]]:
        if not file_path:
            raise FileNotFoundError("规则未配置文件路径")
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        size = path.stat().st_size
        if size > FILE_SIZE_LIMIT:
            raise ValueError(f"文件超过 100MB 上限: {file_path}")

        # 磁盘 IO 丢线程池，避免阻塞事件循环（见风险表）
        data = await asyncio.to_thread(path.read_bytes)
        detected = mimetypes.guess_type(str(path))[0]
        return data, detected

    @staticmethod
    def _substitute(template: str, m: Optional[re.Match]) -> str:
        """$1/$2 数字组与 ${name} 命名组替换（见 3.4.1）。"""
        if not template or m is None:
            return template

        def repl(match: re.Match) -> str:
            key = match.group(1) or match.group(2)
            try:
                if key.isdigit():
                    return m.group(int(key)) or ""
                return m.group(key) or ""
            except (IndexError, KeyError, re.error):
                return ""

        # ${name} 优先，再处理 $1
        return re.sub(r"\$\{(\w+)\}|\$(\d+)", repl, template)


def _has_content_type(headers: dict) -> bool:
    return any(k.lower() == "content-type" for k in headers)


def _ensure_charset(headers: dict) -> dict:
    """文本类 Content-Type 未声明 charset 时补 utf-8（见 _build_response 注释）。"""
    for key, value in list(headers.items()):
        if key.lower() != "content-type":
            continue
        ctype = value.split(";", 1)[0].strip().lower()
        needs = ctype.startswith("text/") or ctype.endswith("+json") or ctype == "application/json"
        if needs and "charset" not in value.lower():
            headers[key] = f"{value}; charset=utf-8"
    return headers
