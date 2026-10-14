"""过滤 / 搜索管线：QSortFilterProxyModel 子类（DESIGN.md 3.2.1 / 3.2.2）。

域名过滤（黑名单/白名单）+ 类型隐藏（CONNECT/Image）+ 关键字搜索
共用这一个模型，AND 组合——一套机制，不会出现多个过滤互相打架。
"""

from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt

from app.textutil import decode_for_search
from app.ui.flow_store import SORT_ROLE

IMAGE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp"
)

SCOPE_URL = "url"
SCOPE_HEADERS = "headers"
SCOPE_BODY = "body"

BODY_INDEX_LIMIT = 512 * 1024  # 与 CaptureAddon 的大 body 策略一致


class FilterConfig:
    """过滤配置（持久化进 settings.json 的部分）。"""

    def __init__(
        self,
        host_mode: str = "blacklist",  # blacklist | whitelist
        host_keywords: list[str] | None = None,
        hide_connect: bool = False,
        hide_image: bool = False,
    ):
        self.host_mode = host_mode
        self.host_keywords = list(host_keywords or [])
        self.hide_connect = hide_connect
        self.hide_image = hide_image

    def to_dict(self) -> dict:
        return {
            "host_mode": self.host_mode,
            "host_keywords": list(self.host_keywords),
            "hide_connect": self.hide_connect,
            "hide_image": self.hide_image,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FilterConfig":
        mode = data.get("host_mode", "blacklist")
        if mode not in ("blacklist", "whitelist"):
            mode = "blacklist"
        return cls(
            host_mode=mode,
            host_keywords=[str(k) for k in data.get("host_keywords", [])],
            hide_connect=bool(data.get("hide_connect", False)),
            hide_image=bool(data.get("hide_image", False)),
        )

    def is_active(self) -> bool:
        return bool(
            self.host_keywords or self.hide_connect or self.hide_image
        )


class SearchConfig:
    """搜索配置（临时动作，不持久化）。"""

    def __init__(self):
        self.text = ""
        self.scopes = {SCOPE_URL}
        self.case_sensitive = False

    def is_active(self) -> bool:
        return bool(self.text)


class FlowFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter_config = FilterConfig()
        self.search_config = SearchConfig()
        # 由外部注入：flow_id -> 完整 flow 对象（headers/body 搜索用）
        self.flow_lookup = lambda flow_id: None
        # 排序取原始数值（大小/耗时/状态码），而不是 DisplayRole 的格式化文本
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(True)

    # ------------------------------------------------------------ 排序

    def lessThan(self, left, right) -> bool:  # noqa: N802
        """按 SORT_ROLE 比较。

        不用默认实现的两个原因：① 默认走 DisplayRole，`1.3 MB` < `812 B`；
        ② 混类型（int/str）比较在 Python 里直接 TypeError。这里统一
        「数值 < 字符串 < 空值」，同类型正常比，异类型不抛异常。
        """
        a = left.data(SORT_ROLE)
        b = right.data(SORT_ROLE)

        ar, br = _rank(a), _rank(b)
        if ar != br:
            return ar < br
        if ar == 2:                      # 都是空值
            return False
        try:
            return a < b
        except TypeError:                # 兜底：类型不可比时按字符串
            return str(a) < str(b)

    # ------------------------------------------------------------ 配置入口

    def set_filter_config(self, config: FilterConfig) -> None:
        self.filter_config = config
        self.invalidateFilter()

    def set_search_config(self, config: SearchConfig) -> None:
        self.search_config = config
        self.invalidateFilter()

    # ------------------------------------------------------------ 核心判定

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:  # noqa: N802
        store = self.sourceModel()
        idx = store.index(source_row, 0, source_parent)
        row = store.data(idx, Qt.ItemDataRole.UserRole)
        if row is None:
            return False
        return self._accept_domain(row) and self._accept_type(row) and self._accept_search(row)

    # ---- 域名过滤（黑名单/白名单，空白名单不过滤）

    def _accept_domain(self, row: dict) -> bool:
        keywords = self.filter_config.host_keywords
        if not keywords:
            return True
        host = (row.get("host") or "").lower()
        hit = any(k.lower() in host for k in keywords if k)
        if self.filter_config.host_mode == "whitelist":
            return hit
        return not hit  # blacklist：含关键词的隐藏

    # ---- 类型隐藏

    def _accept_type(self, row: dict) -> bool:
        if self.filter_config.hide_connect and row.get("is_connect"):
            return False
        if self.filter_config.hide_image and _is_image(row):
            return False
        return True

    # ---- 关键字搜索

    def _accept_search(self, row: dict) -> bool:
        cfg = self.search_config
        if not cfg.text:
            return True
        scopes = cfg.scopes
        if not scopes:
            return True

        def haystack(text: str) -> str:
            return text if cfg.case_sensitive else text.lower()

        needle = haystack(cfg.text)

        if SCOPE_URL in scopes:
            target = (
                f"{row.get('method', '')} {row.get('host', '')} "
                f"{row.get('server_ip', '')} {row.get('path', '')}"
            )
            if needle in haystack(target):
                return True

        if scopes & {SCOPE_HEADERS, SCOPE_BODY}:
            flow = self.flow_lookup(row.get("id"))
            if flow is not None:
                if SCOPE_HEADERS in scopes:
                    if needle in haystack(_headers_text(flow)):
                        return True
                if SCOPE_BODY in scopes:
                    if needle in haystack(_body_text(flow)):
                        return True
        return False


def _rank(value) -> int:
    """排序分组：0=数值，1=字符串，2=None。

    只有 None 单独成组（沉底），空字符串按普通字符串参与比较——所以升序时
    `-`（无服务端 IP）与状态 0（无响应）会排在最前，与 Fiddler 一致；
    数值组永远排在字符串组之前，避免 int / str 直接比较抛 TypeError。
    """
    if value is None:
        return 2
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return 0
    return 1


def _is_image(row: dict) -> bool:
    """content-type image/* 或 URL 扩展名命中（双口径，见 3.2.1）。"""
    if (row.get("content_type") or "").lower().startswith("image/"):
        return True
    path = (row.get("path") or "").lower()
    return any(path.endswith(ext) for ext in IMAGE_EXTENSIONS)


def _headers_text(flow) -> str:
    parts = []
    for msg in (getattr(flow, "request", None), getattr(flow, "response", None)):
        if msg is None:
            continue
        try:
            for k, v in msg.headers.items():
                parts.append(f"{k}: {v}")
        except Exception:
            continue
    return "\n".join(parts)


def _body_text(flow) -> str:
    parts = []
    for msg in (getattr(flow, "request", None), getattr(flow, "response", None)):
        if msg is None:
            continue
        try:
            content = msg.get_content(strict=False) or b""
        except Exception:
            try:
                content = msg.raw_content or b""
            except Exception:
                content = b""
        if len(content) > BODY_INDEX_LIMIT:
            content = content[:BODY_INDEX_LIMIT]
        try:
            content_type = msg.headers.get("content-type", "") or ""
        except Exception:
            content_type = ""
        # 默认 UTF-8 解码（见 app/textutil.py）；mitmproxy 的 latin-1 默认会导致中文乱码
        parts.append(decode_for_search(content, content_type))
    return "\n".join(parts)
