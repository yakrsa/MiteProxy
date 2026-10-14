"""body 结构化展示（对齐 Fiddler 的 JSON / WebForm / ImageView inspector）。

纯函数、无 Qt 依赖：把「原始字节 + content-type」换算成某一种视图该显示什么，
UI 只负责渲染。这样格式化逻辑可以逐字单测（与 export.py / network.py 同一套路）。

四条硬规则：

1. **格式化失败一律回落原文 + 说明原因**，绝不因为解析失败就吞掉 body——
   抓包工具里"内容不见了"比"没格式化"严重得多。
2. **只按 content-type 判定表单**，不猜。表单体长得太像普通文本，猜错了会把
   正常文本拆成一堆莫名其妙的 key/value。
3. **十六进制视图单独抽出来**（此前内联在 UI 里，没法单测）。
4. **大内容不硬扛**：实测（见 DESIGN 3.2.5）卡顿来自两处——语法着色（2 万行
   ≈ 260ms）与超长单行的换行排版（300KB 单行 ≈ 1.2s，多行 2MB 才 50ms）。
   所以格式化用完整 body、只截断**渲染结果**，并给着色与换行各设一道闸门。
"""

from __future__ import annotations

import gzip
import json
import re
import zlib
from dataclasses import dataclass
from urllib.parse import parse_qsl

from app.textutil import decode_body

#: 原文 / 十六进制视图的输入截断（超过就截断显示，与搜索索引策略一致）
BODY_PREVIEW_LIMIT = 512 * 1024

#: 十六进制视图的渲染上限
HEX_VIEW_LIMIT = 64 * 1024

#: JSON 格式化输入上限：json.loads/dumps 很便宜（4MB 约 30ms），瓶颈不在这，
#: 所以给得宽松；真正要卡住的是下面的渲染上限。
JSON_PARSE_LIMIT = 4 * 1024 * 1024

#: 渲染文本上限（多行文本塞进 QPlainTextEdit 很便宜：2MB ≈ 50ms）
RENDER_TEXT_LIMIT = 2 * 1024 * 1024

#: 语法着色上限：QSyntaxHighlighter 按 block 走，2 万行约 260ms。
#: 超过就暂停着色——丢了颜色但界面不卡，取舍很清楚。
HIGHLIGHT_LIMIT = 256 * 1024

#: 换行闸门：单行超过这个长度就不换行。实测 100KB 单行换行 160ms、
#: 300KB 单行换行 1.2s（超线性增长），而多行文本换行几乎免费。
WRAP_MAX_LINE_CHARS = 64 * 1024

VIEW_AUTO = "auto"
VIEW_RAW = "raw"
VIEW_JSON = "json"
VIEW_FORM = "form"
VIEW_IMAGE = "image"
VIEW_HEX = "hex"

VIEW_MODE_ITEMS: tuple[tuple[str, str], ...] = (
    (VIEW_AUTO, "自动"),
    (VIEW_RAW, "原文"),
    (VIEW_JSON, "JSON"),
    (VIEW_FORM, "表单"),
    (VIEW_IMAGE, "图片"),
    (VIEW_HEX, "十六进制"),
)

#: 认定为表单的 content-type（只认这一个，不猜）
FORM_CONTENT_TYPES = ("application/x-www-form-urlencoded",)

#: 可预览的图片类型（svg 走矢量渲染，见 app/ui/detail_panel.ImageView）
IMAGE_CONTENT_TYPES = (
    "image/png", "image/jpeg", "image/jpg", "image/gif", "image/bmp",
    "image/webp", "image/x-icon", "image/vnd.microsoft.icon", "image/svg+xml",
)

# jsonp / ld+json / hal+json / vnd.api+json / problem+json …
_PLUS_JSON_RE = re.compile(r"^(?:application|text)/[\w.\-]+\+json$")


def view_mode_items() -> list[tuple[str, str]]:
    """[(key, 显示名)]，UI 视图按钮栏直接用。"""
    return list(VIEW_MODE_ITEMS)


def view_mode_label(key: str) -> str:
    for k, label in VIEW_MODE_ITEMS:
        if k == key:
            return label
    return VIEW_MODE_ITEMS[1][1]     # 未知 → 原文


# ====================================================================== 判定

def _main_content_type(content_type: str) -> str:
    """`application/json; charset=utf-8` → `application/json`。"""
    return (content_type or "").split(";")[0].strip().lower()


def is_json_content_type(content_type: str) -> bool:
    ct = _main_content_type(content_type)
    if ct in ("application/json", "text/json"):
        return True
    return bool(_PLUS_JSON_RE.match(ct))


def is_form_content_type(content_type: str) -> bool:
    return _main_content_type(content_type) in FORM_CONTENT_TYPES


def is_image_content_type(content_type: str) -> bool:
    ct = _main_content_type(content_type)
    return ct in IMAGE_CONTENT_TYPES or ct.startswith("image/")


def format_json_text(text: str) -> tuple[bool, str]:
    """缩进格式化。返回 `(是否成功, 文本)`——失败时文本是失败原因，供 UI 提示。

    不排序 key：保持服务端返回顺序（Fiddler 也是这样，便于和线上对照）。
    `ensure_ascii=False`：中文原样输出，不变成 `\\uXXXX`。

    `RecursionError` 必须单独接：`json.loads` 遇到深嵌套（如 `[[[[...]]]]`）
    会抛它，而它不是 `ValueError` 的子类——漏接就是整个界面崩掉。
    """
    try:
        obj = json.loads(text)
    except RecursionError:
        return False, "嵌套层级过深，超出解析器递归上限"
    except (json.JSONDecodeError, ValueError, MemoryError) as e:
        return False, str(e)
    try:
        return True, json.dumps(obj, ensure_ascii=False, indent=2)
    except (ValueError, TypeError, RecursionError, MemoryError) as e:
        return False, f"序列化失败：{e}"


def _json_parsable(text: str) -> bool:
    if not text or not text.strip():
        return False
    ok, _ = format_json_text(text.strip())
    return ok


def detect_view_mode(content_type: str, body_bytes: bytes | None,
                     limit: int = BODY_PREVIEW_LIMIT) -> str:
    """「自动」模式选哪个视图：看 content-type，必要时再嗅探 body。"""
    if not body_bytes:
        return VIEW_RAW
    ct = _main_content_type(content_type)
    if is_image_content_type(ct):
        return VIEW_IMAGE
    if is_form_content_type(ct):
        return VIEW_FORM

    text = decode_body(body_bytes[:limit], content_type)
    if text is None:
        return VIEW_HEX          # 解码不出来 → 二进制
    # 声明了 JSON 就无条件进 JSON 视图：解析不了时由渲染层回落原文**并说明原因**
    # （"服务端说自己是 JSON，实际不是"本身就是重要线索），而不是静默当成普通文本。
    if is_json_content_type(ct):
        return VIEW_JSON

    # 没声明 content-type、或声明成 text/plain 之类 —— 长得像 JSON 也按 JSON 显示。
    # 只在这两种情况里嗅探，且要求真的能解析：把普通文本塞进 JSON 视图只会显示
    # 一句吓人的"解析失败"，不如老老实实显示原文。
    # 要求首字符是 { 或 [，避免把 `[INFO]` 这种日志片段当 JSON。
    if (not ct or ct.startswith("text/")) and text.strip()[:1] in ("{", "["):
        return VIEW_JSON if _json_parsable(text) else VIEW_RAW
    return VIEW_RAW


# ====================================================================== JSON 渲染

@dataclass
class JsonFormat:
    """JSON 视图的渲染结果。

    `ok=False` 时 `text` 是**原文**（绝不是空串），`note` 说明为什么没格式化。
    """
    ok: bool
    text: str
    note: str = ""
    #: 渲染文本是否被截断（格式化成功但太长）
    truncated: bool = False


def format_json_body(body: bytes | None, content_type: str) -> JsonFormat:
    """把整个 body 当 JSON 格式化——**先完整解析、只截断渲染结果**。

    早期实现先按 512KB 截断再解析，结果任何大于 512KB 的 JSON 都会被截成
    半截、解析失败，用户反而失去格式化还看到一句"解析失败"。解析本身很便宜
    （4MB 约 30ms），所以这里反过来：完整解析，输出太长才截断。
    """
    if not body:
        return JsonFormat(False, "")
    total = len(body)

    def raw_preview() -> str:
        text = decode_body(body[:BODY_PREVIEW_LIMIT], content_type) or ""
        if total > BODY_PREVIEW_LIMIT:
            text += truncation_note(total)
        return text

    if total > JSON_PARSE_LIMIT:
        mb = total / 1024 / 1024
        return JsonFormat(
            False, raw_preview(),
            f"内容 {mb:.1f}MB 超出格式化上限 {JSON_PARSE_LIMIT // 1024 // 1024}MB，已显示原文",
        )

    text = decode_body(body, content_type)
    if text is None:
        return JsonFormat(False, "", "无法按文本解码")

    ok, pretty = format_json_text(text.strip())
    if not ok:
        return JsonFormat(False, raw_preview(), f"JSON 解析失败，已显示原文：{pretty}")

    if len(pretty) > RENDER_TEXT_LIMIT:
        pretty = pretty[:RENDER_TEXT_LIMIT] + truncation_note(
            len(pretty), limit=RENDER_TEXT_LIMIT
        )
        return JsonFormat(True, pretty, "", truncated=True)
    return JsonFormat(True, pretty)


def longest_line(text: str) -> int:
    """最长行的字符数（换行闸门用）。"""
    return max((len(seg) for seg in text.split("\n")), default=0)


def should_wrap(text: str, enabled: bool) -> tuple[bool, str]:
    """是否真的换行，以及不换行时的原因。

    换行对多行文本几乎免费，但对超长单行是超线性开销（300KB 单行 ≈ 1.2s），
    所以单行超闸门时宁可不换行并把理由说清楚——用户切到 JSON 视图（格式化后
    是多行）就又能换行了。
    """
    if not enabled:
        return False, ""
    n = longest_line(text)
    if n > WRAP_MAX_LINE_CHARS:
        return False, (
            f"单行最长 {n // 1024}KB 超过 {WRAP_MAX_LINE_CHARS // 1024}KB，"
            "已临时关闭换行（换行会让界面卡顿）"
        )
    return True, ""


# ====================================================================== 压缩内容

def content_encoding_of(headers) -> str:
    if headers is None:
        return ""
    try:
        return (headers.get("content-encoding", "") or "").strip()
    except Exception:
        return ""


def decompress(data: bytes, encoding: str) -> bytes | None:
    """按 content-encoding 解压；解不出来返回 None（不抛）。"""
    enc = (encoding or "").strip().lower()
    try:
        if enc in ("gzip", "x-gzip"):
            return gzip.decompress(data)
        if enc == "deflate":
            try:
                return zlib.decompress(data)
            except zlib.error:
                return zlib.decompress(data, -zlib.MAX_WBITS)   # 裸 deflate
        if enc == "br":
            import brotli

            return brotli.decompress(data)
        if enc == "zstd":
            import zstandard

            return zstandard.ZstdDecompressor().decompress(data)
    except Exception:
        return None
    return None


def sniff_decompress(data: bytes) -> tuple[bytes | None, str]:
    """不靠 header、按魔数猜压缩格式（mitmproxy 解压失败时的兜底）。

    返回 `(解压结果, 格式名)`；猜不出或解压失败返回 `(None, "")`。
    """
    if not data:
        return None, ""
    if data[:2] == b"\x1f\x8b":
        out = decompress(data, "gzip")
        return out, "gzip"
    if data[:4] == b"\x28\xb5\x2f\xfd":
        out = decompress(data, "zstd")
        return out, "zstd"
    if data[:1] == b"\x78":
        out = decompress(data, "deflate")
        return out, "deflate"
    return None, ""


def decoded_note(encoding: str, raw_len: int, shown_len: int,
                 source: str = "mitmproxy") -> str:
    """「已解压」提示文案。

    mitmproxy 的 `get_content()` 已经按 content-encoding 解压过了，但界面上
    不说，用户会以为看到的就是线上字节——导出时按 raw 还是解压后的算，全靠
    这里一句话说清楚。
    """
    if not encoding or raw_len <= 0 or shown_len == raw_len:
        return ""
    kind = "手动解压" if source == "fallback" else "已解压"
    return (
        f"{kind} {encoding}：线上 {raw_len / 1024:.1f}KB → "
        f"{shown_len / 1024:.1f}KB"
    )


# ====================================================================== 表单

def parse_urlencoded(text: str) -> list[tuple[str, str]]:
    """`a=1&name=%E5%BC%A0%E4%B8%89` → `[("a","1"), ("name","张三")]`。

    用 `parse_qsl` 而不是手切：它负责 `+` → 空格、`%XX` 解码，中文与特殊字符
    能直接读。`keep_blank_values=True` 保留 `flag=` 这类空值字段——空值本身
    就是调试时要看的信息（少了它你不知道前端到底传没传这个字段）。
    """
    if not text:
        return []
    # 连个 `=` 都没有 → 根本不是表单。parse_qsl 会把整串当成一个「key + 空值」返回，
    # 那样普通文本（比如一句错误信息）会被显示成一行莫名其妙的字段。
    if "=" not in text:
        return []
    return parse_qsl(text, keep_blank_values=True)


# ====================================================================== 十六进制

def hex_dump(data: bytes, total: int | None = None,
             limit: int = HEX_VIEW_LIMIT) -> str:
    """经典 `偏移 | 十六进制 | ASCII` 三栏视图。

    total 传完整 body 大小（用于"完整大小"提示），data 是已截断的内容。
    """
    if total is None:
        total = len(data)
    shown = data[:limit]
    lines = []
    for off in range(0, len(shown), 16):
        chunk = shown[off : off + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{off:08x}  {hex_part:<48}  {ascii_part}")
    text = "[二进制内容 · 十六进制视图]\n" + "\n".join(lines)
    if len(data) > limit:
        text += (
            f"\n…… [十六进制视图仅显示前 {limit // 1024}KB，"
            f"完整大小 {total // 1024}KB]"
        )
    return text


def truncation_note(total: int, limit: int = BODY_PREVIEW_LIMIT) -> str:
    return f"\n\n…… [已截断：仅显示前 {limit // 1024}KB，完整大小 {total // 1024}KB]"
