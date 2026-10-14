"""body 解码工具：统一默认 UTF-8（用户要求，见 DESIGN.md 3.2 修订）。

策略：
1. content-type 声明了合法 charset → 按声明解码（尊重服务端事实）；
2. 未声明 / 声明无法识别 → **默认 UTF-8**（mitmproxy 的 get_text 默认
   latin-1，会让中文内容显示为乱码，本项目不采用该默认）；
3. 都失败 → 返回 None，调用方走十六进制视图。
"""

from __future__ import annotations

import difflib
import re
from typing import Optional

DEFAULT_CHARSET = "utf-8"

_CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?([\w\-]+)", re.IGNORECASE)


def charset_from_content_type(content_type: str) -> Optional[str]:
    if not content_type:
        return None
    m = _CHARSET_RE.search(content_type)
    if not m:
        return None
    charset = m.group(1).lower()
    if charset in ("utf8", "utf-8"):
        return "utf-8"
    return charset


def decode_body(data: bytes, content_type: str = "") -> Optional[str]:
    """按声明 charset 或默认 UTF-8 解码；失败返回 None（转十六进制视图）。"""
    if not data:
        return ""
    declared = charset_from_content_type(content_type)
    candidates = []
    if declared:
        candidates.append(declared)
    if DEFAULT_CHARSET not in candidates:
        candidates.append(DEFAULT_CHARSET)
    for enc in candidates:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def decode_for_search(data: bytes, content_type: str = "") -> str:
    """搜索用解码：永不失败，无法解码的部分用替换字符兜底。"""
    if not data:
        return ""
    declared = charset_from_content_type(content_type)
    for enc in (declared, DEFAULT_CHARSET):
        if not enc:
            continue
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode(DEFAULT_CHARSET, errors="replace")


# ---------------------------------------------------------------- 文本 diff


def unified_diff(
    old_text: str,
    new_text: str,
    context_lines: int = 3,
    max_lines: int = 2000,
) -> str:
    """行级 diff（difflib unified 格式）。用于非 JSON body 的重放对比。

    超行数上限时截断并附说明——几十万行的 diff 渲染出来界面直接卡死。
    """
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="原响应",
            tofile="新响应",
            lineterm="",
            n=context_lines,
        )
    )
    if not diff:
        return ""
    if len(diff) > max_lines:
        diff = diff[:max_lines]
        diff.append(f"……（diff 超过 {max_lines} 行，已截断）")
    return "\n".join(diff)
