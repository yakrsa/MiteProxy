"""网络模拟相关的纯逻辑：弱网限速配置 + 域名映射规则。

不依赖 Qt、不碰 mitmproxy 运行时对象，只做「配置 → 参数」的换算与校验，
所以能被逐字单测；真正生效分别在 `addons/throttle.py` 与 mitmproxy 自带的
MapRemote addon（靠 `map_remote` 选项驱动）。

关于限速的语义（重要，避免误解）：
不是逐块限速，而是**按响应体大小折算总传输时间，在响应发回客户端前一次性等待**。
对"复现 loading 态 / 超时 / 骨架屏"这类场景足够，且行为可预测。
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

#: 单次延迟上限：手滑填个 999999 不至于把连接挂死
MAX_DELAY_MS = 30_000

#: 档位：(key, 显示名, 延迟 ms, 速率 kbps)。0 表示该项不生效
THROTTLE_PRESETS: tuple[tuple[str, str, int, int], ...] = (
    ("off", "关闭", 0, 0),
    ("2g", "2G（50 kbps + 400ms）", 400, 50),
    ("3g", "3G（400 kbps + 200ms）", 200, 400),
    ("4g", "4G（4 Mbps + 80ms）", 80, 4000),
    ("weak", "弱网（50 kbps + 2000ms）", 2000, 50),
    ("custom", "自定义", 0, 0),
)

PRESET_KEYS = tuple(p[0] for p in THROTTLE_PRESETS)
DEFAULT_PRESET = "off"

#: mitmproxy 的 map_remote 选项格式是 "<sep>/regex/replacement"，分隔符取首字符。
#: 用不可见字符当分隔符，避免和正则里的 | 或 URL 里的 /、# 撞车。
MAP_SPEC_SEP = "\x1f"

#: 哪些字符出现时认为用户写的是「正则」而不是「普通域名」。
#: 注意**不包含 `.`**——域名本来就带点，把 `api.prod.com` 当正则会让 `.` 变
#: 成"任意字符"，错误的匹配范围（apiXprodYcom 也会被改写）。
_REGEX_HINT_CHARS = set("*+?[](){}|\\^$")

#: 允许的普通主机名字符（IPv6 单独用 ipaddress 判）
_HOSTNAME_RE = re.compile(r"[A-Za-z0-9._\-]+")

#: Windows 盘符路径（C:\ 或 C:/）
_WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def looks_like_path(text: str) -> bool:
    """target 看着像本地路径而不是 host:port → 按 Map Local 处理。

    认得 `/`、`./`、`../`、`~`、`\\` 开头与 Windows 盘符。
    注意 `parse_target` 也能"解析"出一些含 `/` 的串（它取第一段当 netloc），
    所以顺序是**先看路径形态**，再看 host:port。
    """
    raw = (text or "").strip()
    if not raw:
        return False
    if _WIN_DRIVE_RE.match(raw):
        return True
    return raw.startswith(("/", "./", "../", "~", "\\"))


@dataclass
class ThrottleConfig:
    """弱网模拟配置（持久化进 settings.json）。"""

    preset: str = DEFAULT_PRESET
    latency_ms: int = 0
    rate_kbps: int = 0

    # ---------------------------------------------------------------- 取值

    @property
    def enabled(self) -> bool:
        return self.preset != "off" and (self.latency_ms > 0 or self.rate_kbps > 0)

    def to_dict(self) -> dict:
        return {
            "preset": self.preset,
            "latency_ms": self.latency_ms,
            "rate_kbps": self.rate_kbps,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ThrottleConfig":
        data = data or {}
        preset = str(data.get("preset") or DEFAULT_PRESET)
        if preset not in PRESET_KEYS:
            preset = DEFAULT_PRESET
        cfg = cls(
            preset=preset,
            latency_ms=sanitize_int(data.get("latency_ms"), MAX_DELAY_MS),
            rate_kbps=sanitize_int(data.get("rate_kbps"), 10_000_000),
        )
        if preset != "custom":
            # 非自定义档位以档位表为准，避免 settings.json 手改后出现"档位和参
            # 数对不上"的迷惑状态
            _, _, latency, rate = preset_values(preset)
            cfg.latency_ms, cfg.rate_kbps = latency, rate
        return cfg

    # ---------------------------------------------------------------- 计算

    def delay_ms(self, body_bytes: int = 0) -> float:
        """本条响应的总延迟（ms）= 固定延迟 + 按体积折算的传输时间。"""
        if not self.enabled:
            return 0.0
        delay = float(max(0, self.latency_ms))
        if self.rate_kbps > 0 and body_bytes > 0:
            bytes_per_second = self.rate_kbps * 1024 / 8
            delay += body_bytes / bytes_per_second * 1000.0
        return min(delay, float(MAX_DELAY_MS))


def sanitize_int(value, upper: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(n, upper))


def preset_values(key: str) -> tuple[str, str, int, int]:
    """档位 → (key, 显示名, 延迟 ms, 速率 kbps)。未知档位退化为「关闭」。"""
    for item in THROTTLE_PRESETS:
        if item[0] == key:
            return item
    return THROTTLE_PRESETS[0]


def preset_labels() -> list[tuple[str, str]]:
    """[(key, 显示名)]，UI 下拉直接用。"""
    return [(key, label) for key, label, _, _ in THROTTLE_PRESETS]


# ====================================================================== 域名映射


@dataclass
class MapRule:
    """一条域名映射：把 source 匹配到的请求按 target 处理。

    target 有两种形态，按写法自动区分：
    - `host:port` / `http://host:port` → **Map Remote**：改写上游地址；
    - 本地路径（`/`、`./`、`~`、`C:\\` 开头）→ **Map Local**：按路径取本地文件，
      文件不存在时回落上游。
    """

    source: str = ""
    target: str = ""
    enabled: bool = True

    @property
    def kind(self) -> str:
        """remote | local | unknown（unknown = 填了但两种都认不出）。"""
        if not (self.source.strip() and self.target.strip()):
            return "unknown"
        if looks_like_path(self.target):
            return "local"
        return "remote" if parse_target(self.target) else "unknown"

    def to_dict(self) -> dict:
        return {"source": self.source, "target": self.target, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, data: dict) -> "MapRule":
        data = data or {}
        return cls(
            source=str(data.get("source") or "").strip(),
            target=str(data.get("target") or "").strip(),
            enabled=bool(data.get("enabled", True)),
        )

    def is_usable(self) -> bool:
        return bool(self.enabled and self.source.strip() and self.target.strip())


def _valid_host(host: str) -> bool:
    """目标主机名合法性：IP（含 IPv6）或 [A-Za-z0-9._-]+。"""
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    return bool(_HOSTNAME_RE.fullmatch(host))


def parse_target(target: str) -> tuple[str, str] | None:
    """`127.0.0.1:8080` / `http://dev.local:9000` → (scheme, host[:port])。

    未写 scheme 时按 http（本地开发服务几乎都是 http）；写死了就尊重它。
    返回 None 表示无法解析：空串、只有 scheme、主机名非法、端口越界。
    """
    raw = (target or "").strip()
    if not raw:
        return None
    scheme = "http"
    if "://" in raw:
        parsed = urlparse(raw)
        if not parsed.hostname:
            return None
        scheme = (parsed.scheme or "http").lower()
        netloc = parsed.netloc
    else:
        netloc = raw.split("/", 1)[0]
        if not netloc:
            return None
        parsed = urlparse(f"http://{netloc}")

    try:
        # .port 越界会抛 ValueError（如 127.0.0.1:99999），必须在这里接住
        port = parsed.port
    except ValueError:
        return None
    if port is not None and not (0 < port < 65536):
        return None
    if not _valid_host(parsed.hostname or ""):
        return None
    return scheme, netloc


def _host_pattern(source: str) -> str | None:
    """原域名 → 正则片段。

    含 `* + ? [ ] ( ) { } | \\ ^ $` 时按用户写的正则处理（高级用法），
    否则整串转义成字面量——普通域名一定走这条，避免 `.` 变成通配。
    """
    text = (source or "").strip()
    if not text:
        return None
    # 用户可能连 scheme 一起写了，剥掉避免拼出 ^https?://http://...
    text = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", "", text)
    text = text.rstrip("/")
    if not text:
        return None
    if any(ch in _REGEX_HINT_CHARS for ch in text):
        return text
    return re.escape(text)


def _map_subject(source: str) -> str | None:
    """原域名 → 匹配 URL 前缀的正则（Map Remote / Map Local 共用）。

    只匹配 scheme + host + 端口：`^https?://api\\.prod\\.com(?::\\d+)?/`
    路径与 query 不进匹配——两种映射都要求路径原样保留/映射。
    """
    pattern = _host_pattern(source)
    if pattern is None:
        return None
    return rf"^https?://{pattern}(?::\d+)?/"


def build_map_remote_spec(rule: MapRule) -> str | None:
    """规则 → mitmproxy `map_remote` 选项串；不可用返回 None。

    只处理 remote 形态；local 形态的目标不是 host:port，这里返回 None
    （由 map_local_entries 接手，见 addons/maplocal.py）。
    """
    if not rule.is_usable() or rule.kind != "remote":
        return None
    subject = _map_subject(rule.source)
    parsed = parse_target(rule.target)
    if subject is None or parsed is None:
        return None
    scheme, netloc = parsed
    replacement = f"{scheme}://{netloc}/"
    # 含分隔符会破坏 spec 解析，直接判为不可用（而不是静默错位）
    if MAP_SPEC_SEP in subject or MAP_SPEC_SEP in replacement:
        return None
    return MAP_SPEC_SEP + subject + MAP_SPEC_SEP + replacement


def build_map_remote_specs(rules) -> tuple[list[str], list[MapRule]]:
    """批量转换，返回 (specs, 被跳过的规则)。

    被跳过 = 未启用 / 字段为空 / target 无法解析 / 原域名是非法正则。
    """
    specs: list[str] = []
    skipped: list[MapRule] = []
    for rule in rules or []:
        if not rule.enabled:
            continue
        spec = build_map_remote_spec(rule)
        if spec is None:
            skipped.append(rule)
            continue
        try:
            re.compile(spec.split(MAP_SPEC_SEP)[1])
        except (re.error, IndexError):
            skipped.append(rule)
            continue
        specs.append(spec)
    return specs, skipped


def rules_from_dicts(items) -> list[MapRule]:
    """[[dict]] → [MapRule]，忽略非 dict 的脏数据。"""
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        out.append(MapRule.from_dict(item))
    return out


def rules_to_dicts(rules) -> list[dict]:
    return [r.to_dict() for r in rules or []]


def map_local_entries(rules) -> list[tuple["re.Pattern[str]", Path]]:
    """local 形态的规则 → [(URL 前缀正则, 本地目录)]，供 MapLocalAddon 用。

    跳过：未启用 / 非 local 形态 / 原域名是非法正则。
    目录不存在**不在这里拦**——用户可能先填规则后建目录，运行时找不到文件
    自然回落到上游（见 addons/maplocal.py）。
    """
    entries: list[tuple[re.Pattern, Path]] = []
    for rule in rules or []:
        if not rule.is_usable() or rule.kind != "local":
            continue
        subject = _map_subject(rule.source)
        if subject is None:
            continue
        try:
            pattern = re.compile(subject)
        except re.error:
            continue
        entries.append((pattern, Path(rule.target).expanduser()))
    return entries


def describe_rule(rule: MapRule) -> str:
    """给 UI 用的一句话说明（列表里显示映射结果）。"""
    kind = rule.kind
    if not rule.source.strip():
        return "未填写原域名"
    if kind == "local":
        return f"https?://{rule.source}/* → 本地目录 {rule.target}"
    if kind == "unknown":
        return "目标无法识别（应形如 127.0.0.1:8080 或 /path/to/dir）"
    parsed = parse_target(rule.target)
    if parsed is None:
        return "目标无法解析（应形如 127.0.0.1:8080）"
    scheme, netloc = parsed
    return f"https?://{rule.source}/* → {scheme}://{netloc}/*"
