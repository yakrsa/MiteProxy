"""FARX 导入器：解析 Fiddler AutoResponder / Rules 导出的 .farx 文件。

格式依据 Telerik 官方规则仓库真实样本解码验证（DESIGN.md 3.4.1）：

    <AutoResponder RulesVersion="2" FiddlerVersion="5.0.x">
      <State Enabled="true" Fallthrough="true" UseLatency="false">
        <ResponseRule Comment="..." Enabled="true"
                      Match='{"matches":["%%<base64:条件JSON>"], "matchCondition":1}'
                      Action='["%%<base64:动作JSON>", ...]'
                      Headers="<base64:原始响应头文本>"
                      Body="<base64:响应体字节>" />
      </State>
    </AutoResponder>
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app import rules as _rules_mod
from app.rules import CONTAINS, EXACT, REGEX, Action, Match, Rule

log = logging.getLogger(__name__)

# 动作类型（样本解码得出的编号）
_ACTION_MOCK_TYPES = {11, 22}   # 配合 Headers/Body 的手工响应
_ACTION_REDIRECT_TYPE = 6      # 重定向：find(正则) + value(目标，含 $1/$2)


@dataclass
class ImportResult:
    rules: list[Rule] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (名称, 原因)

    @property
    def ok_count(self) -> int:
        return len(self.rules)

    @property
    def skip_count(self) -> int:
        return len(self.skipped)


def parse_file(path: str | Path) -> ImportResult:
    """解析 .farx 文件，返回可导入规则与跳过清单。"""
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"不是有效的 FARX(XML) 文件: {e}") from e

    result = ImportResult()
    rule_elements = list(root.iter("ResponseRule"))
    if not rule_elements:
        raise ValueError("文件中没有找到 ResponseRule 节点")
    for rr in rule_elements:
        try:
            if _is_everywhere(rr):
                # Fiddler Everywhere：Match 是 {"matches":[...]} JSON 对象、
                # Match/Action 是 JSON 数组（base64 条件/动作）
                _parse_rule(rr, result)
            else:
                # Fiddler Classic (v4/v5)：Match/Action 是字符串前缀语法
                # （EXACT:/REGEX:/路径），与 Everywhere 的 JSON 格式不兼容
                _parse_classic_rule(rr, result)
        except Exception:
            log.exception("解析 ResponseRule 失败")
            result.skipped.append((rr.get("Comment") or "未命名规则", "解析异常，已跳过"))
    return result


# ------------------------------------------------------------------ 内部


def _is_everywhere(rr: ET.Element) -> bool:
    """Fiddler Everywhere 判定：Match/Action 任一是 JSON 数组，或 Match 是
    含 "matches" 键的 JSON 对象（官方样本 Match 为 {"matches":[...]} 形态）。
    Classic 格式的 Match/Action 是字符串前缀语法，不会是合法 JSON。"""
    for attr in ((rr.get("Match") or ""), (rr.get("Action") or "")):
        attr = attr.strip()
        if attr.startswith("["):
            return True
    match_attr = (rr.get("Match") or "").strip()
    if match_attr.startswith("{"):
        try:
            data = json.loads(match_attr)
        except json.JSONDecodeError:
            return False
        if isinstance(data, dict) and "matches" in data:
            return True
    return False


def _parse_rule(rr: ET.Element, result: ImportResult) -> None:
    comment = (rr.get("Comment") or "").strip() or "Fiddler 规则"
    enabled = (rr.get("Enabled") or "true").strip().lower() != "false"

    conditions = _decode_conditions(rr.get("Match") or "")
    actions = _decode_conditions(rr.get("Action") or "")
    headers_text = _b64_text(rr.get("Headers") or "")
    body_bytes = _b64_bytes(rr.get("Body") or "")

    if not conditions:
        result.skipped.append((comment, "无法解析匹配条件"))
        return

    # ---- 匹配条件 → Match（取第一个可识别的 URL 条件）
    match = _condition_to_match(conditions[0])
    if match is None:
        cond = conditions[0]
        result.skipped.append(
            (comment, f"暂不支持的匹配条件: {cond.get('condition')}")
        )
        return

    # ---- 动作识别：重定向（type 6）优先于手工响应
    redirect = next(
        (a for a in actions if a.get("type") == _ACTION_REDIRECT_TYPE), None
    )
    has_mock_action = any(a.get("type") in _ACTION_MOCK_TYPES for a in actions)
    has_payload = bool(headers_text or body_bytes)

    if redirect is not None:
        find = redirect.get("find") or ""
        target = redirect.get("value") or ""
        if find:
            # 用 find 正则做匹配，$1/$2 由 mock 引擎命中时替换（语义等价，见 3.4.1）
            match = Match(type=REGEX, value=find)
        action = Action(
            status=307,
            headers={"Location": target} if target else {},
            body_source="inline",
            body="",
        )
    elif has_mock_action or has_payload:
        status, headers = _parse_headers_text(headers_text)
        body_source, body, file_path = _body_to_source(body_bytes)
        action = Action(
            status=status,
            headers=headers,
            body_source=body_source,
            body=body,
            file_path=file_path,
        )
    else:
        result.skipped.append((comment, "无可识别的 mock / 重定向动作"))
        return

    result.rules.append(
        Rule(
            id="imported_" + uuid.uuid4().hex[:8],
            name=comment,
            enabled=enabled,
            match=match,
            action=action,
            source="farx",
        )
    )


def _decode_conditions(attr: str) -> list[dict]:
    """解析 Match/Action 属性：JSON 数组，元素可能是 "%%<base64 JSON>" 或裸 JSON。"""
    if not attr:
        return []
    try:
        data = json.loads(attr)
    except json.JSONDecodeError:
        return []
    items = data.get("matches", []) if isinstance(data, dict) else data
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, str):
            continue
        decoded = _decode_item(item)
        if isinstance(decoded, dict):
            out.append(decoded)
    return out


def _decode_item(item: str) -> Optional[dict]:
    payload = item[2:] if item.startswith("%%") else item
    # 先尝试 base64 → JSON（Fiddler Everywhere 格式）
    try:
        decoded = base64.b64decode(payload, validate=False).decode("utf-8")
        obj = json.loads(decoded)
        if isinstance(obj, dict):
            return obj
    except (binascii.Error, ValueError, UnicodeDecodeError):
        pass
    # 再尝试裸 JSON（兼容其他版本）
    try:
        obj = json.loads(item)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    return None


def _condition_to_match(cond: dict) -> Optional[Match]:
    condition = (cond.get("condition") or "").lower()
    value = cond.get("value")
    if value is None:
        return None
    value = str(value)
    if condition == "contains":
        return Match(type=CONTAINS, value=value)
    if condition == "equals":
        return Match(type=EXACT, value=value)
    if condition in ("matches", "regex"):
        return Match(type=REGEX, value=value)
    return None


def _b64_text(b64: str) -> str:
    if not b64:
        return ""
    try:
        return base64.b64decode(b64).decode("utf-8", errors="replace")
    except (binascii.Error, ValueError):
        return ""


def _b64_bytes(b64: str) -> bytes:
    if not b64:
        return b""
    try:
        return base64.b64decode(b64)
    except (binascii.Error, ValueError):
        return b""


def _parse_headers_text(headers_text: str) -> tuple[int, dict]:
    """'HTTP/2 200\\r\\ncontent-type: ...' → (状态码, headers dict)。"""
    if not headers_text.strip():
        return 200, {}
    lines = headers_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    status = 200
    first = lines[0].strip()
    if first.upper().startswith("HTTP/"):
        parts = first.split()
        if len(parts) >= 2 and parts[1].isdigit():
            status = int(parts[1])
        lines = lines[1:]
    headers: dict[str, str] = {}
    for line in lines:
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if not key:
            continue
        # 同名字段保留第一个（与 Fiddler 行为一致）
        existing = next((k for k in headers if k.lower() == key.lower()), None)
        if existing is not None:
            continue
        headers[_canonical_header(key)] = value.strip()
    return status, headers


# 常见 header 的规范大小写（HTTP 本身大小写不敏感，统一是为了 rules.json 里观感一致）
_CANONICAL_HEADERS = {
    "content-type": "Content-Type",
    "content-length": "Content-Length",
    "content-encoding": "Content-Encoding",
    "location": "Location",
    "cache-control": "Cache-Control",
    "set-cookie": "Set-Cookie",
    "retry-after": "Retry-After",
    "access-control-allow-origin": "Access-Control-Allow-Origin",
    "transfer-encoding": "Transfer-Encoding",
    "connection": "Connection",
    "accept-ranges": "Accept-Ranges",
    "last-modified": "Last-Modified",
}


def _canonical_header(key: str) -> str:
    return _CANONICAL_HEADERS.get(key.lower(), key)


def _body_to_source(body_bytes: bytes) -> tuple[str, str, Optional[str]]:
    """UTF-8 可解码 → 内联；二进制 → 落缓存文件走 file 模式。"""
    if not body_bytes:
        return "inline", "", None
    try:
        return "inline", body_bytes.decode("utf-8"), None
    except UnicodeDecodeError:
        # 运行时读取（而非 import 期绑定），保证测试 monkeypatch 与配置切换生效
        cache_dir = _rules_mod.CONFIG_DIR / "imported"
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / f"{uuid.uuid4().hex[:12]}.bin"
        target.write_bytes(body_bytes)
        log.info("二进制 body 已缓存: %s", target)
        return "file", "", str(target)


# ------------------------------------------------------------------ Fiddler Classic 格式
# 兼容 Fiddler Classic (v4/v5) AutoResponder 导出的 .farx：Match / Action 是字符串前缀语法，
# 而非 Everywhere 的 JSON 数组。实测样本：龙哥的 fiddler_ruls_all.farx（158 条，v5.0.20242）。
#   Match:  EXACT:https://x | REGEX:https://x | (无前缀=包含) | NOT:(暂不支持)
#   Action: 文件路径(返回文件内容) | *redir:url | *delay:ms | *status:code | 裸URL(=redir)
#           | xxx.dat(Fiddler 内置模板→状态码) | *bpu/*bpafter/*drop(暂不支持)


def _classic_name(rr: ET.Element, raw_match: str) -> str:
    c = (rr.get("Comment") or "").strip()
    if c:
        return c
    m = raw_match
    for p in ("EXACT:", "REGEX:", "NOT:"):
        if m.startswith(p):
            m = m[len(p):]
            break
    m = m.strip()
    return (m[:60] + ("…" if len(m) > 60 else "")) or "Fiddler 规则"


def _net_named_group_to_python(pattern: str) -> str:
    """Fiddler/.NET 命名组 (?<name>...) 或 (?'name'...) → Python (?P<name>...)。

    MiteProxy 用 Python re，不认 .NET 命名组语法，不转会导致运行时 re.compile
    抛 re.error、规则整条失效。同时需避开 (?<= / (?<! 后向断言（< 后非标识符）。
    """
    return re.sub(r"\(\?<\??[']?([A-Za-z_]\w*)'?>", r"(?P<\1>", pattern)


def _classic_match(raw: str) -> Optional[Match]:
    """Fiddler Classic 匹配字符串 → MiteProxy Match。否定匹配返回 None。"""
    if not raw:
        return None
    if raw.startswith("NOT:"):
        return None  # 否定匹配 MiteProxy 暂不支持
    if raw.startswith("REGEX:"):
        value = _net_named_group_to_python(raw[len("REGEX:"):])
        return Match(type=REGEX, value=value)
    if raw.startswith("EXACT:"):
        return Match(type=EXACT, value=raw[len("EXACT:"):])
    # 无前缀：Fiddler 默认按"包含"匹配
    return Match(type=CONTAINS, value=raw)


def _map_fiddler_vars(url: str, regex_value: str) -> str:
    """Fiddler 的 ${name} 变量 → MiteProxy 的 $1/$2（按正则命名组出现顺序映射）。"""
    names = re.findall(r"\(\?P<(\w+)>", regex_value)
    for i, name in enumerate(names, 1):
        url = url.replace("${%s}" % name, "$%d" % i)
    return url


def _dat_status(name: str) -> Optional[int]:
    """Fiddler 内置 .dat 响应模板（404_Plain.dat / 502_Unreachable.dat）→ 状态码。"""
    m = re.search(r"(\d{3})", name)
    return int(m.group(1)) if m else None


def _classic_action(raw: str, regex_value: str = ""):
    """解析 Classic Action 字符串。

    返回 (Action, skip_reason)：Action 为 None 时 skip_reason 非空（应跳过）。
    """
    if not raw.strip():
        return None, "动作(Response)为空，无响应可返回"
    delay_m = re.search(r"\*delay:(\d+)", raw)
    redir_m = re.search(r"\*redir:(\S+)", raw)
    status_m = re.search(r"\*status:(\d{3})", raw)
    latency = int(delay_m.group(1)) if delay_m else 0
    unsupported = []
    if "*bpu" in raw or "*bpafter" in raw:
        unsupported.append("断点(*bpu/*bpafter)")
    if "*drop" in raw:
        unsupported.append("丢弃(*drop)")
    if unsupported:
        return None, "暂不支持: " + "/".join(unsupported)
    # 去掉所有 * 指令，残余即 文件路径 / URL / 状态码 / .dat 模板
    rest = re.sub(r"\*\w+:?\S*", "", raw).strip()
    redirect = redir_m.group(1) if redir_m else None
    status = int(status_m.group(1)) if status_m else None
    file_path = None
    if rest.startswith(("http://", "https://")):
        redirect = rest  # 裸 URL 等价 *redir
    elif rest.endswith(".dat"):
        code = _dat_status(rest)
        if code:
            status = code
        else:
            return None, f"无法识别的 Fiddler 模板 {rest}"
    elif re.fullmatch(r"\*?\d{3}", rest):
        status = int(rest.lstrip("*"))
    elif rest:
        file_path = rest  # Windows 绝对路径（通常不含空格）
    if redirect and regex_value:
        redirect = _map_fiddler_vars(redirect, regex_value)
    if redirect:
        return Action(redirect_url=redirect, latency_ms=latency), ""
    if file_path:
        # 文件模式：保留原绝对路径（目标机需同步该文件，缺失时运行期标红）
        return Action(body_source="file", file_path=file_path, latency_ms=latency,
                      status=status or 200), ""
    if status is not None:
        return Action(status=status, latency_ms=latency), ""
    if latency:
        return None, "仅延迟透传，MiteProxy 暂不支持（需配合 mock/重定向动作）"
    return None, "无法识别的动作"


def _parse_classic_rule(rr: ET.Element, result: ImportResult) -> None:
    raw_match = (rr.get("Match") or "").strip()
    raw_action = (rr.get("Action") or "").strip()
    enabled = (rr.get("Enabled") or "true").strip().lower() != "false"
    name = _classic_name(rr, raw_match)
    match = _classic_match(raw_match)
    if match is None:
        result.skipped.append((name, f"不支持的匹配语法: {raw_match[:50]}"))
        return
    action, reason = _classic_action(raw_action, match.value if match.type == REGEX else "")
    if action is None:
        result.skipped.append((name, reason))
        return
    result.rules.append(
        Rule(
            id="imported_" + uuid.uuid4().hex[:8],
            name=name,
            enabled=enabled,
            match=match,
            action=action,
            source="farx",
        )
    )
