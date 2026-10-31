"""过滤 / 搜索管线：QSortFilterProxyModel 子类（DESIGN.md 3.2.1 / 3.2.2）。

域名过滤（黑名单/白名单）+ 类型隐藏（CONNECT/Image）+ 关键字搜索
共用这一个模型，AND 组合——一套机制，不会出现多个过滤互相打架。
"""

from __future__ import annotations

import re
from functools import lru_cache

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


#: 域名过滤的「启用哪个列表」取值
LIST_BLACK = "blacklist"
LIST_WHITE = "whitelist"


def normalize_domain(text: str) -> str:
    """归一化用户输入的域名条目（去空白 / 去末尾点 / 小写）。"""
    return (text or "").strip().rstrip(".").lower()


def add_domains(entries: list[str], domains) -> list[str]:
    """增量追加域名并去重（大小写不敏感），保留原有顺序与写法。

    黑/白名单都是「追加」语义：右键加入、过滤页添加都不会覆盖已有内容。
    """
    result = list(entries or [])
    seen = {normalize_domain(e) for e in result}
    for d in domains:
        raw = (d or "").strip().rstrip(".")
        if not raw:
            continue
        key = raw.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(raw)
    return result


def host_matches(host: str, entry: str) -> bool:
    """判断 ``host`` 是否命中名单条目 ``entry``。

    三类语义，按条目形态分流：

    - 含 ``*``：通配符匹配（``*`` 匹配任意字符序列，含空、含点）。
      ``*.apple.com`` 命中 ``ocsp2.apple.com`` 等所有子域，**并额外涵盖根域**
      ``apple.com``（DNS 式 ``*.`` 前缀不要求前导子域）；``api.*.com``、
      ``*.apple.*``、``*foo.com`` 等也按通配符整串匹配。
    - 带点、不含 ``*``（``example.com``）：域名语义，命中自身或其子域
      （``example.com`` → ``api.example.com``），但不命中
      ``notexample.com`` / ``example.com.evil.net``。
    - 不带点（``google``）：关键字语义，退化为子串匹配，兼容老版本
      手输片段词的行为。
    """
    h = (host or "").strip().rstrip(".").lower()
    e = (entry or "").strip().rstrip(".").lower()
    if not h or not e:
        return False
    if "*" in e:
        return _wildcard_match(h, e)
    if "." in e:
        return h == e or h.endswith("." + e)
    return e in h


@lru_cache(maxsize=512)
def _wildcard_pattern(pattern: str) -> "re.Pattern":
    """把 ``*`` 当作 ``.*`` 的通配符，转义其余正则元字符后编译（带锚点）。

    缓存编译结果：名单条目数量有限，每次过滤判定都重建正则没必要。
    """
    body = re.escape(pattern).replace("\\*", ".*")
    return re.compile("^" + body + "$")


def _wildcard_match(host: str, pattern: str) -> bool:
    """通配符整串匹配；``*.example.com`` 这类前缀写法额外涵盖根域。"""
    if _wildcard_pattern(pattern).fullmatch(host):
        return True
    # ``*.example.com`` 在 fullmatch 下要求 * 匹配到前导子域，根域自身不被命中；
    # DNS 习惯里 *.example.com 通常也指 example.com 本身，这里补上。
    if pattern.startswith("*."):
        suffix = pattern[2:]
        if "." in suffix:
            return host == suffix or host.endswith("." + suffix)
    return False


class FilterConfig:
    """过滤配置（持久化进 settings.json 的部分）。

    黑白名单是两个独立列表 + 一个启用开关，且只能启用其中一个：
    ``enabled`` 关掉整个域名过滤，``active_list`` 决定启用的是黑名单
    还是白名单。两个列表各自增量维护，切换开关不丢内容。
    """

    def __init__(
        self,
        blacklist: list[str] | None = None,
        whitelist: list[str] | None = None,
        enabled: bool = False,
        active_list: str = LIST_BLACK,
        hide_connect: bool = False,
        hide_image: bool = False,
    ):
        self.blacklist = list(blacklist or [])
        self.whitelist = list(whitelist or [])
        self.enabled = enabled
        self.active_list = (
            active_list if active_list in (LIST_BLACK, LIST_WHITE) else LIST_BLACK
        )
        self.hide_connect = hide_connect
        self.hide_image = hide_image

    @property
    def active_entries(self) -> list[str]:
        """当前启用列表的内容（未启用时也返回内容，供编辑用）。"""
        return self.blacklist if self.active_list == LIST_BLACK else self.whitelist

    def to_dict(self) -> dict:
        return {
            "blacklist": list(self.blacklist),
            "whitelist": list(self.whitelist),
            "enabled": self.enabled,
            "active_list": self.active_list,
            "hide_connect": self.hide_connect,
            "hide_image": self.hide_image,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FilterConfig":
        data = data or {}
        if "blacklist" in data or "whitelist" in data:
            return cls(
                blacklist=[str(k) for k in data.get("blacklist", [])],
                whitelist=[str(k) for k in data.get("whitelist", [])],
                enabled=bool(data.get("enabled", False)),
                active_list=str(data.get("active_list", LIST_BLACK)),
                hide_connect=bool(data.get("hide_connect", False)),
                hide_image=bool(data.get("hide_image", False)),
            )
        # 旧版配置迁移：单列表 + host_mode 改写 → 落到对应新列表
        mode = data.get("host_mode", LIST_BLACK)
        if mode not in (LIST_BLACK, LIST_WHITE):
            mode = LIST_BLACK
        keywords = [str(k) for k in data.get("host_keywords", [])]
        return cls(
            blacklist=keywords if mode == LIST_BLACK else [],
            whitelist=keywords if mode == LIST_WHITE else [],
            enabled=bool(keywords),  # 老配置有词即视为启用
            active_list=mode,
            hide_connect=bool(data.get("hide_connect", False)),
            hide_image=bool(data.get("hide_image", False)),
        )

    def is_active(self) -> bool:
        """域名过滤是否真的在生效（空白名单 = 不过滤，防止误把流量全藏了）。"""
        return bool(self.enabled and self.active_entries)


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

    # ---- 域名过滤（黑/白名单两个列表 + 启用开关，只能启用一个）

    def _accept_domain(self, row: dict) -> bool:
        cfg = self.filter_config
        if not cfg.is_active():
            return True
        host = (row.get("host") or "").lower()
        entries = cfg.active_entries
        hit = any(host_matches(host, k) for k in entries if k)
        if cfg.active_list == LIST_WHITE:
            return hit
        return not hit  # blacklist：命中的隐藏

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
