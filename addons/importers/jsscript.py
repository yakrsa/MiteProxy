"""CustomRules.js 导入器：启发式解析 FiddlerScript 的 OnBeforeRequest（DESIGN.md 3.4.2）。

JScript.NET 无法完整执行，这里只静态识别典型 mock 模式：

    if (oSession.uriContains("/api/user")) {
        oSession.utilCreateResponseAndBypassServer();
        oSession.responseCode = 200;
        oSession.utilSetResponseBody('{"name":"mock"}');
        oSession.oResponse.headers.Add("Content-Type", "application/json");
    }

无法静态识别的块（复杂条件、动态拼接 body）一律进 skipped 清单，不静默丢弃。
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.rules import CONTAINS, REGEX, Action, Match, Rule

log = logging.getLogger(__name__)

_FUNC_RE = re.compile(
    r"\bstatic\s+function\s+OnBeforeRequest\s*\([^)]*\)\s*\{", re.IGNORECASE
)


@dataclass
class ImportResult:
    rules: list[Rule] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return len(self.rules)

    @property
    def skip_count(self) -> int:
        return len(self.skipped)


def parse_file(path: str | Path) -> ImportResult:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    m = _FUNC_RE.search(text)
    if not m:
        raise ValueError("未找到 static function OnBeforeRequest(...) 定义")
    body, _ = _match_braces(text, m.end() - 1)
    if body is None:
        raise ValueError("OnBeforeRequest 函数体括号不匹配")

    result = ImportResult()
    for cond, block, preceding_comment in _iter_if_blocks(body):
        _parse_block(cond, block, preceding_comment, result)
    if result.ok_count == 0 and result.skip_count == 0:
        result.skipped.append(("(整个函数)", "未识别到任何 mock 模式"))
    return result


# ------------------------------------------------------------------ if 块遍历


def _iter_if_blocks(body: str):
    """产出 (条件文本, 块文本, 前一行注释)。"""
    if_re = re.compile(r"\bif\s*\(")
    i = 0
    while True:
        m = if_re.search(body, i)
        if not m:
            return
        cond, j = _match_parens(body, m.end() - 1)
        if cond is None:
            i = m.end()
            continue
        k = j
        while k < len(body) and body[k] in " \t\r\n":
            k += 1
        if k < len(body) and body[k] == "{":
            block, k2 = _match_braces(body, k)
        else:
            # 无花括号的单语句 if：取到行尾
            nl = body.find("\n", k)
            k2 = nl if nl != -1 else len(body)
            block = body[k:k2]
        if block is not None:
            yield cond, block, _preceding_comment(body, m.start())
        i = k2 if k2 else m.end()


def _preceding_comment(body: str, pos: int) -> Optional[str]:
    """取 if 语句上一行的 // 注释作为规则名候选。"""
    prev_end = body.rfind("\n", 0, pos)
    if prev_end == -1:
        return None
    prev_start = body.rfind("\n", 0, prev_end) + 1
    line = body[prev_start:prev_end].strip()
    if line.startswith("//"):
        return line[2:].strip()
    return None


# ------------------------------------------------------------------ 块解析


def _parse_block(
    cond: str, block: str, comment: Optional[str], result: ImportResult
) -> None:
    match = _parse_condition(cond)
    if match is None:
        preview = " ".join(cond.split())[:40]
        result.skipped.append((f"条件: {preview}", "暂不支持的匹配条件"))
        return

    fallback_name = comment or match.value[:40]

    # ---- body 提取（纯字符串字面量才认；含变量/拼接的进 skipped）
    body_text: Optional[str] = None
    dynamic_body = False

    args = _call_args(block, "utilSetResponseBody")
    if args is not None:
        literal = _string_literal(args)
        if literal is not None:
            body_text = literal
        else:
            dynamic_body = True

    if body_text is None and not dynamic_body:
        m = re.search(r"responseBodyString\s*=\s*([^;]+);", block, re.S)
        if m:
            literal = _string_literal(m.group(1).strip())
            if literal is not None:
                body_text = literal
            else:
                dynamic_body = True

    if dynamic_body:
        result.skipped.append((fallback_name, "body 为动态拼接，无法静态解析"))
        return

    # ---- 其他信号
    status = None
    m = re.search(r"responseCode\s*=\s*[\"']?(\d+)[\"']?", block)
    if m:
        status = int(m.group(1))

    headers: dict[str, str] = {}
    for hm in re.finditer(
        r"headers\s*\.\s*Add\s*\(\s*(['\"])(.+?)\1\s*,\s*(['\"])(.*?)\3\s*\)",
        block,
        re.S,
    ):
        headers[hm.group(2)] = _js_unescape(hm.group(4))
    for hm in re.finditer(
        r"headers\s*\[\s*(['\"])(.+?)\1\s*\]\s*=\s*(['\"])(.*?)\3", block, re.S
    ):
        headers[hm.group(2)] = _js_unescape(hm.group(4))
    for hm in re.finditer(
        r"oResponse\s*\[\s*(['\"])(.+?)\1\s*\]\s*=\s*(['\"])(.*?)\3", block, re.S
    ):
        headers[hm.group(2)] = _js_unescape(hm.group(4))

    file_path = None
    fm = re.search(r"x-replywithfile\s*['\"]?\s*\]\s*=\s*(['\"])(.*?)\1", block)
    if fm:
        file_path = _js_unescape(fm.group(2))

    has_bypass = "utilCreateResponseAndBypassServer" in block
    has_content = (
        body_text is not None
        or status is not None
        or bool(headers)
        or file_path is not None
    )
    if not has_content and not has_bypass:
        result.skipped.append((fallback_name, "块内无 mock 响应内容"))
        return
    # 仅 bypass 无内容：允许导入为空 200 响应（Fiddler 语义等价）

    if file_path:
        action = Action(
            status=status or 200,
            headers=headers,
            body_source="file",
            body="",
            file_path=file_path,
        )
    else:
        action = Action(
            status=status or 200,
            headers=headers,
            body_source="inline",
            body=body_text or "",
        )

    result.rules.append(
        Rule(
            id="imported_" + uuid.uuid4().hex[:8],
            name=(comment or f"FiddlerScript: {match.value}")[:60],
            enabled=True,
            match=match,
            action=action,
            source="js",
        )
    )


def _parse_condition(cond: str) -> Optional[Match]:
    """从 if 条件中提取 URL 类匹配；取第一个可识别的。"""
    candidates: list[Match] = []

    m = re.search(r"uriContains\s*\(\s*(['\"])(.*?)\1\s*\)", cond, re.S)
    if m:
        candidates.append(Match(type=CONTAINS, value=_js_unescape(m.group(2))))

    m = re.search(r"HostnameIs\s*\(\s*(['\"])(.*?)\1\s*\)", cond, re.S)
    if m:
        candidates.append(Match(type=CONTAINS, value=_js_unescape(m.group(2))))

    # /regex/.test(oSession.URI) 或 oSession.URI.match(/regex/)
    m = re.search(r"/((?:[^/\\\n]|\\.)+)/\s*\.\s*test\s*\(", cond)
    if not m:
        m = re.search(r"\.\s*match\s*\(\s*/((?:[^/\\\n]|\\.)+)/", cond)
    if m:
        candidates.append(Match(type=REGEX, value=m.group(1)))

    if not candidates:
        return None
    # 多个 URL 条件（&& 组合）时只取第一个，其余条件丢失——
    # 启发式解析的已知边界，调用方在预览中可见规则内容。
    return candidates[0]


# ------------------------------------------------------------------ 词法工具


def _call_args(s: str, func_name: str) -> Optional[str]:
    """取 func_name(...) 的实参文本；不存在返回 None。"""
    m = re.search(rf"\b{re.escape(func_name)}\s*\(", s)
    if not m:
        return None
    args, _ = _match_parens(s, m.end() - 1)
    return args


def _string_literal(args: str) -> Optional[str]:
    """实参是单一字符串字面量时返回反转义内容，否则 None。

    关键：内部不允许出现未转义的同类引号——否则是 'a' + x + 'b' 这类拼接，
    必须判为动态，不能静态求值。
    """
    if args is None:
        return None
    m = re.fullmatch(r"\s*(['\"])(.*)\1\s*", args, re.S)
    if not m:
        return None
    quote, inner = m.group(1), m.group(2)
    for i, ch in enumerate(inner):
        if ch == quote and (i == 0 or inner[i - 1] != "\\"):
            return None
    return _js_unescape(inner)


def _match_parens(s: str, open_idx: int) -> tuple[Optional[str], int]:
    return _match_delims(s, open_idx, "(", ")")


def _match_braces(s: str, open_idx: int) -> tuple[Optional[str], int]:
    return _match_delims(s, open_idx, "{", "}")


def _match_delims(
    s: str, open_idx: int, open_ch: str, close_ch: str
) -> tuple[Optional[str], int]:
    """从 open_idx（开括号处）配对到对应闭括号，返回 (内部文本, 闭括号后下标)。

    跳过字符串字面量与注释，避免把括号/花括号误配。
    """
    if open_idx >= len(s) or s[open_idx] != open_ch:
        return None, open_idx
    depth = 0
    i = open_idx
    n = len(s)
    while i < n:
        ch = s[i]
        if ch in "'\"":
            quote = ch
            i += 1
            while i < n:
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == quote:
                    break
                i += 1
        elif ch == "/" and i + 1 < n and s[i + 1] == "/":
            nl = s.find("\n", i)
            i = n if nl == -1 else nl
            continue
        elif ch == "/" and i + 1 < n and s[i + 1] == "*":
            end = s.find("*/", i + 2)
            i = n if end == -1 else end + 1
            continue
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return s[open_idx + 1 : i], i + 1
        i += 1
    return None, n


def _js_unescape(s: str) -> str:
    """反转义常见 JS 字符串转义。"""

    def repl(m: re.Match) -> str:
        if m.group(1) is not None:  # \uXXXX
            try:
                return chr(int(m.group(1), 16))
            except ValueError:
                return m.group(0)
        if m.group(2) is not None:  # \xXX
            try:
                return chr(int(m.group(2), 16))
            except ValueError:
                return m.group(0)
        c = m.group(3)
        mapping = {
            "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f",
            "0": "\0", "\\": "\\", "'": "'", '"': '"', "/": "/",
        }
        return mapping.get(c, c)

    return re.sub(
        r"\\(?:u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2})|(.))", repl, s, flags=re.S
    )
