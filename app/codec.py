"""编码转换（对齐 Fiddler 的 TextWizard）：纯函数，不依赖 Qt，可单测。

设计约定：
- 每个转换都是「文本进、文本出」，失败**不抛到 UI**——返回带 error 的 Result，
  界面显示红字说明，而不是崩掉或静默给个空框。
- 二进制中间产物（gzip/deflate）统一走 **Base64 或 Hex** 两种文本形态进出，
  输入侧两种都尝试识别，并在 note 里说明实际按哪种解的——避免「看起来能解、
  其实解的是另一种编码」这种误导。
- 解码结果不是合法 UTF-8 时不报错，按单字节回落并在 note 里说明，
  因为「解出来了但看不懂」比「报错」更有信息量。
"""

from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import html
import json
import re
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone

from app.jsonutil import dumps_json, parse_json
from urllib.parse import (
    quote,
    quote_plus,
    unquote_to_bytes,
)
from PySide6.QtCore import QCoreApplication, QT_TRANSLATE_NOOP


def _unquote_plus_to_bytes(text: str) -> bytes:
    """urllib 只有 unquote_plus（返回 str），这里要字节版以便非 UTF-8 时回落。"""
    return unquote_to_bytes(text.replace("+", " "))

# ---------------------------------------------------------------- 常量

GROUP_CODEC = QT_TRANSLATE_NOOP("Codec", "编解码")
GROUP_FORMAT = QT_TRANSLATE_NOOP("Codec", "格式 · 文本")
GROUP_HASH = QT_TRANSLATE_NOOP("Codec", "哈希")

#: 放到工具栏上的常用四项（对齐 Fiddler 里用得最多的那几个）
QUICK_KEYS = ("url_encode", "url_decode", "b64_encode", "b64_decode")

_B64_RE = re.compile(r"^[A-Za-z0-9+/\-_]+={0,2}$")
_HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")

#: 实时转换的输入上限，超过就让用户点按钮（见 codec_panel 的说明）
LIVE_LIMIT = 512 * 1024


class TransformError(Exception):
    """可预期的转换失败（输入不合格式等），消息直接给用户看。"""


@dataclass(frozen=True)
class Transform:
    key: str
    label: str
    group: str
    hint: str = ""


@dataclass(frozen=True)
class Result:
    text: str = ""
    #: 失败原因；非 None 时 text 为空
    error: str | None = None
    #: 成功但需要说明（如「已按单字节显示」「压缩率」）
    note: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _ok(text: str, note: str | None = None) -> Result:
    return Result(text=text, note=note)


# ---------------------------------------------------------------- 内部工具


def _decode_bytes(raw: bytes) -> Result:
    """字节 → 文本：UTF-8 优先，失败按单字节回落并说明。"""
    if not raw:
        return _ok("")
    try:
        return _ok(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return _ok(
            raw.decode("latin-1"),
            QCoreApplication.translate("Codec", "结果不是合法 UTF-8，已按单字节显示；要看原始字节请再做一次「Hex 编码」"),
        )


def _decode_bytes_str(raw: bytes) -> str:
    return _decode_bytes(raw).text


def _binary_candidates(text: str) -> list[tuple[str, bytes]]:
    """把输入当成「二进制数据的文本形态」解析：Hex 与 Base64 都试。

    返回 [(来源说明, 字节)]——两者都可能成立（如 `abcd`），由调用方逐个尝试。
    """
    s = re.sub(r"\s+", "", text)
    if not s:
        raise TransformError(QCoreApplication.translate("Codec", "输入为空"))
    out: list[tuple[str, bytes]] = []
    if _HEX_RE.match(s) and len(s) % 2 == 0:
        try:
            out.append(("Hex", bytes.fromhex(s)))
        except ValueError:
            pass
    if _B64_RE.match(s):
        padded = s + "=" * ((-len(s)) % 4)
        try:
            raw = (
                base64.urlsafe_b64decode(padded)
                if ("-" in s or "_" in s)
                else base64.b64decode(padded)
            )
            out.append(("Base64", raw))
        except (binascii.Error, ValueError):
            pass
    if not out:
        raise TransformError(
            QCoreApplication.translate("Codec", "输入既不是 Hex 也不是 Base64——二进制数据请先用其中一种形态贴进来")
        )
    return out


# ---------------------------------------------------------------- 转换实现


def _url_encode(text: str) -> Result:
    return _ok(quote(text, safe=""))


def _url_encode_form(text: str) -> Result:
    return _ok(quote_plus(text, safe=""))


def _url_decode(text: str) -> Result:
    return _decode_bytes(unquote_to_bytes(text))


def _url_decode_form(text: str) -> Result:
    return _decode_bytes(_unquote_plus_to_bytes(text))


def _b64_encode(text: str) -> Result:
    return _ok(base64.b64encode(text.encode("utf-8")).decode("ascii"))


def _b64_decode(text: str) -> Result:
    s = re.sub(r"\s+", "", text)
    if not s:
        return _ok("")
    if not _B64_RE.match(s):
        raise TransformError(
            QCoreApplication.translate("Codec", "不是合法的 Base64（只认 A-Z a-z 0-9 + / - _，末尾 = 补齐）")
        )
    padded = s + "=" * ((-len(s)) % 4)
    try:
        raw = (
            base64.urlsafe_b64decode(padded)
            if ("-" in s or "_" in s)
            else base64.b64decode(padded)
        )
    except (binascii.Error, ValueError) as exc:
        raise TransformError(QCoreApplication.translate("Codec", 'Base64 解码失败：{0}').format(exc))
    return _decode_bytes(raw)


def _hex_encode(text: str) -> Result:
    return _ok(text.encode("utf-8").hex())


def _hex_decode(text: str) -> Result:
    s = re.sub(r"[\s:,\-]", "", text.strip())
    s = re.sub(r"(?i)^0x", "", s)  # 容忍 0x 前缀
    if not s:
        return _ok("")
    if len(s) % 2:
        raise TransformError(QCoreApplication.translate("Codec", '十六进制长度应为偶数，当前 {0} 个字符').format(len(s)))
    if not _HEX_RE.match(s):
        raise TransformError(QCoreApplication.translate("Codec", "含非十六进制字符（只认 0-9 a-f A-F）"))
    return _decode_bytes(bytes.fromhex(s))


def _html_encode(text: str) -> Result:
    # quote=True：& < > " ' 全部转义，可直接贴进 HTML 属性
    return _ok(html.escape(text, quote=True))


def _html_decode(text: str) -> Result:
    return _ok(html.unescape(text))


def _unicode_escape(text: str) -> Result:
    """中文 → \u4e2d\u6587，换行 → \n（Python/JS 字符串字面量形态）。"""
    return _ok(text.encode("unicode_escape").decode("ascii"))


def _unicode_unescape(text: str) -> Result:
    # latin-1 + backslashreplace：让已存在的中文原样绕回，不破坏它们
    return _ok(text.encode("latin-1", "backslashreplace").decode("unicode_escape"))


def _json_escape(text: str) -> Result:
    """加 JSON 字符串所需的转义，但不加外层引号（方便嵌进现有 JSON）。"""
    return _ok(json.dumps(text, ensure_ascii=False)[1:-1])


def _json_unescape(text: str) -> Result:
    s = text.strip()
    if not s:
        return _ok("")
    try:
        # 带引号的完整 JSON 字符串 / 不带引号的字符串内容，都认
        return _ok(json.loads(s if s.startswith('"') else f'"{s}"'))
    except json.JSONDecodeError as exc:
        raise TransformError(QCoreApplication.translate("Codec", '不是合法的 JSON 字符串：{0}').format(exc))


def _json_error_message(error) -> str:
    """把 jsonutil 的定位信息压成一行（编码转换页的状态栏是单行的）。"""
    head = f"{error.location}：" if error.location else ""
    hint = f"（{error.hint}）" if error.hint else ""
    return f"{head}{error.message}{hint}"


def _json_pretty(text: str) -> Result:
    return _reshape_json(text, indent=2)


def _json_minify(text: str) -> Result:
    return _reshape_json(text, indent=None)


def _reshape_json(text: str, indent: int | None) -> Result:
    """复用 jsonutil：与 JSON 页同一套解析与错误定位，避免两处说法不一致。"""
    if not text.strip():
        return _ok("")
    result = parse_json(text)
    if not result.ok:
        raise TransformError(_json_error_message(result.error))
    ok, dumped = dumps_json(result.value, indent=indent)
    if not ok:
        raise TransformError(dumped)
    return _ok(dumped, note=result.notes[0] if result.notes else None)


def _gzip_compress(text: str) -> Result:
    raw = text.encode("utf-8")
    try:
        packed = gzip.compress(raw, mtime=0)  # mtime=0：同样输入每次结果一致
    except TypeError:  # pragma: no cover - 老版本 Python 无 mtime 参数
        packed = gzip.compress(raw)
    b64 = base64.b64encode(packed).decode("ascii")
    return _ok(b64, QCoreApplication.translate("Codec", 'UTF-8 {0}B → gzip {1}B → Base64 {2} 字符').format(len(raw), len(packed), len(b64)))


def _gunzip(text: str) -> Result:
    if not text.strip():
        return _ok("")
    for source, raw in _binary_candidates(text):
        try:
            out = gzip.decompress(raw)
        except (OSError, EOFError, zlib.error):
            continue
        result = _decode_bytes(out)
        return Result(
            result.text,
            note=QCoreApplication.translate("Codec", '（按 {0} 解析，解压后 {1}B）').format(source, len(out))
            + (f"；{result.note}" if result.note else ""),
        )
    raise TransformError(QCoreApplication.translate("Codec", "Gzip 解压失败：输入应是 gzip 数据的 Base64 或 Hex"))


def _deflate_decompress(text: str) -> Result:
    """HTTP 的 Content-Encoding: deflate 有两种（裸 deflate / zlib 头），都试。"""
    if not text.strip():
        return _ok("")
    for source, raw in _binary_candidates(text):
        for name, call in (
            (QCoreApplication.translate("Codec", "裸 deflate"), lambda b: zlib.decompress(b, -15)),
            (QCoreApplication.translate("Codec", "zlib 头"), lambda b: zlib.decompress(b)),
            ("gzip", lambda b: gzip.decompress(b)),
        ):
            try:
                out = call(raw)
            except (OSError, EOFError, zlib.error):
                continue
            result = _decode_bytes(out)
            return Result(
                result.text,
                note=QCoreApplication.translate("Codec", '（按 {0} 解析，{1}，解压后 {2}B）').format(source, name, len(out))
                + (f"；{result.note}" if result.note else ""),
            )
    raise TransformError(QCoreApplication.translate("Codec", "Deflate 解压失败：输入应是 deflate/zlib 数据的 Base64 或 Hex"))


def _upper(text: str) -> Result:
    return _ok(text.upper())


def _lower(text: str) -> Result:
    return _ok(text.lower())


def _jwt_decode(text: str) -> Result:
    s = text.strip()
    if not s:
        return _ok("")
    match = re.match(r"(?i)^bearer\s+(\S+)$", s)
    if match:
        s = match.group(1)
        prefix_note = QCoreApplication.translate("Codec", "（已自动去掉 Bearer 前缀）")
    else:
        prefix_note = ""
    parts = s.split(".")
    if len(parts) != 3:
        raise TransformError(
            QCoreApplication.translate("Codec", "JWT 应由 header.payload.signature 三段组成（Bearer 前缀会自动去掉）")
        )

    def decode_segment(seg: str, what: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(seg + "=" * ((-len(seg)) % 4))
        except (binascii.Error, ValueError):
            raise TransformError(QCoreApplication.translate("Codec", '{0} 不是合法的 Base64URL').format(what))
        return _decode_bytes_str(raw)

    def pretty(raw: str) -> str:
        try:
            return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, ValueError):
            return raw

    payload_raw = decode_segment(parts[1], "Payload")
    lines = [
        "— Header —",
        pretty(decode_segment(parts[0], "Header")),
        "",
        "— Payload —",
        pretty(payload_raw),
        "",
        "— Signature —",
        QCoreApplication.translate("Codec", '{0}（未校验签名）').format(parts[2]),
    ]

    note = None
    try:
        obj = json.loads(payload_raw)
    except (json.JSONDecodeError, ValueError):
        obj = None
    if isinstance(obj, dict):
        exp = obj.get("exp")
        if isinstance(exp, (int, float)):
            try:
                moment = datetime.fromtimestamp(float(exp))
            except (OverflowError, OSError, ValueError):
                moment = None
            if moment is not None:
                delta = (moment - datetime.now()).total_seconds()
                if delta < 0:
                    state = QCoreApplication.translate("Codec", "已过期")
                elif delta > 86400:
                    state = QCoreApplication.translate("Codec", '剩余 {0} 天').format(int(delta // 86400))
                else:
                    state = QCoreApplication.translate("Codec", "即将过期（24 小时内）")
                note = f"exp → {moment:%Y-%m-%d %H:%M:%S}（{state}）{prefix_note}".strip()
    if note is None and prefix_note:
        note = prefix_note.lstrip("（）")
    return _ok("\n".join(lines), note)


def _ts_to_date(text: str) -> Result:
    s = text.strip()
    if not s:
        return _ok("")
    try:
        value = float(s)
    except ValueError:
        raise TransformError(QCoreApplication.translate("Codec", "请输入数字时间戳（秒或毫秒）"))
    # 1e11 秒 = 公元 5138 年，实际不会遇到；用它区分秒/毫秒足够安全
    is_ms = abs(value) >= 1e11
    seconds = value / 1000.0 if is_ms else value
    try:
        local = datetime.fromtimestamp(seconds)
        utc = datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise TransformError(QCoreApplication.translate("Codec", '时间戳超出可表示范围：{0}').format(exc))
    unit = (QCoreApplication.translate("Codec", "毫秒") if is_ms
            else QCoreApplication.translate("Codec", "秒"))
    return _ok(QCoreApplication.translate(
        "Codec", "{0}（本地）\n{1}（UTC）\n原始数值 {2}，按{3}解释"
    ).format(
        f"{local:%Y-%m-%d %H:%M:%S}", f"{utc:%Y-%m-%d %H:%M:%S}", int(value), unit
    ))


def _date_to_ts(text: str) -> Result:
    s = text.strip()
    if not s:
        return _ok("")
    normalized = re.sub(r"(?i)Z$", "+00:00", s)
    moment: datetime | None = None
    try:
        moment = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
        ):
            try:
                moment = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
    if moment is None:
        raise TransformError(
            QCoreApplication.translate("Codec", "无法解析日期，试试 2026-10-14 00:17:33 或 2026-10-14T00:17:33Z")
        )
    if s.isdigit():
        raise TransformError(
            QCoreApplication.translate("Codec", '{0} 看起来是时间戳而不是日期，请用「时间戳 → 日期」').format(s)
        )
    stamp = moment.timestamp()
    zone = QCoreApplication.translate("Codec", "带时区偏移") if moment.tzinfo else QCoreApplication.translate("Codec", "按本地时区解释")
    # 第一行只放纯秒数：方便直接选中复制，附注放后面几行
    return _ok(QCoreApplication.translate(
        "Codec", "{0}\n{1}（毫秒）\n{2}，{3}"
    ).format(int(stamp), int(stamp * 1000), f"{moment:%Y-%m-%d %H:%M:%S}", zone))


def _digest(algo: str):
    def run(text: str) -> Result:
        return _ok(hashlib.new(algo, text.encode("utf-8")).hexdigest())

    return run


# ---------------------------------------------------------------- 注册表

_TRANSFORMS: tuple[Transform, ...] = (
    Transform("url_encode", QT_TRANSLATE_NOOP("Codec", "URL 编码"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "空格 → %20；除字母数字与 -_.~ 外全部转义（RFC 3986）")),
    Transform("url_encode_form", QT_TRANSLATE_NOOP("Codec", "URL 编码（表单）"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "空格 → +，用于 application/x-www-form-urlencoded")),
    Transform("url_decode", QT_TRANSLATE_NOOP("Codec", "URL 解码"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "%XX 还原；+ 保持为加号（适用于路径与 query）")),
    Transform("url_decode_form", QT_TRANSLATE_NOOP("Codec", "URL 解码（表单）"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "%XX 还原，且 + 视为空格（表单语义）")),
    Transform("b64_encode", QT_TRANSLATE_NOOP("Codec", "Base64 编码"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "UTF-8 字节 → Base64（标准字母表，含 + /）")),
    Transform("b64_decode", QT_TRANSLATE_NOOP("Codec", "Base64 解码"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "自动忽略换行空格；含 - _ 时按 URL-safe 字母表解")),
    Transform("hex_encode", QT_TRANSLATE_NOOP("Codec", "Hex 编码"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "UTF-8 字节 → 小写十六进制串")),
    Transform("hex_decode", QT_TRANSLATE_NOOP("Codec", "Hex 解码"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "十六进制串 → 文本；容忍空格、冒号与 0x 前缀")),
    Transform("html_encode", QT_TRANSLATE_NOOP("Codec", "HTML 实体编码"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "& < > \" ' → &amp; &lt; … 可直接贴进 HTML 属性")),
    Transform("html_decode", QT_TRANSLATE_NOOP("Codec", "HTML 实体解码"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "&amp; &#x27; &nbsp; 等实体还原为字符")),
    Transform("unicode_escape", QT_TRANSLATE_NOOP("Codec", "Unicode 转义"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "中文 → \\u4e2d\\u6587，换行 → \\n（字符串字面量形态）")),
    Transform("unicode_unescape", QT_TRANSLATE_NOOP("Codec", "Unicode 反转义"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "\\u4e2d\\u6587 → 中文，同时支持 \\x41 \\n \\t")),
    Transform("json_escape", QT_TRANSLATE_NOOP("Codec", "JSON 字符串转义"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "加 JSON 所需转义，不加外层引号")),
    Transform("json_unescape", QT_TRANSLATE_NOOP("Codec", "JSON 字符串反转义"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "去掉 JSON 转义；带不带外层引号都认")),
    Transform("gzip_compress", QT_TRANSLATE_NOOP("Codec", "Gzip 压缩"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "压缩后以 Base64 输出（mtime 固定，同输入同结果）")),
    Transform("gunzip", QT_TRANSLATE_NOOP("Codec", "Gzip 解压"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "输入为 gzip 数据的 Base64 或 Hex，两种都试")),
    Transform("deflate_decompress", QT_TRANSLATE_NOOP("Codec", "Deflate 解压"), GROUP_CODEC, QT_TRANSLATE_NOOP("Codec", "裸 deflate / zlib 头 / gzip 三种都试")),
    Transform("jwt_decode", QT_TRANSLATE_NOOP("Codec", "JWT 解码"), GROUP_FORMAT, QT_TRANSLATE_NOOP("Codec", "拆 header / payload 并美化 JSON，签名不校验；带 exp 时提示是否过期")),
    Transform("json_pretty", QT_TRANSLATE_NOOP("Codec", "JSON 美化"), GROUP_FORMAT, QT_TRANSLATE_NOOP("Codec", "缩进 2 空格，中文不转义")),
    Transform("json_minify", QT_TRANSLATE_NOOP("Codec", "JSON 压缩"), GROUP_FORMAT, QT_TRANSLATE_NOOP("Codec", "去掉所有多余空白，压成一行")),
    Transform("ts_to_date", QT_TRANSLATE_NOOP("Codec", "时间戳 → 日期"), GROUP_FORMAT, QT_TRANSLATE_NOOP("Codec", "自动区分秒 / 毫秒，同时给出本地时间与 UTC")),
    Transform("date_to_ts", QT_TRANSLATE_NOOP("Codec", "日期 → 时间戳"), GROUP_FORMAT, QT_TRANSLATE_NOOP("Codec", "秒与毫秒都给；无时区按本地时区解释")),
    Transform("upper", QT_TRANSLATE_NOOP("Codec", "转大写"), GROUP_FORMAT, QT_TRANSLATE_NOOP("Codec", "Unicode 大写（中文不受影响）")),
    Transform("lower", QT_TRANSLATE_NOOP("Codec", "转小写"), GROUP_FORMAT, QT_TRANSLATE_NOOP("Codec", "Unicode 小写（中文不受影响）")),
    Transform("md5", QT_TRANSLATE_NOOP("Codec", "MD5"), GROUP_HASH, QT_TRANSLATE_NOOP("Codec", "32 位十六进制（仅用于校验，勿当密码算法）")),
    Transform("sha1", QT_TRANSLATE_NOOP("Codec", "SHA-1"), GROUP_HASH, QT_TRANSLATE_NOOP("Codec", "40 位十六进制（仅用于校验）")),
    Transform("sha256", QT_TRANSLATE_NOOP("Codec", "SHA-256"), GROUP_HASH, QT_TRANSLATE_NOOP("Codec", "64 位十六进制（仅用于校验）")),
)

_FUNCS = {
    "url_encode": _url_encode,
    "url_encode_form": _url_encode_form,
    "url_decode": _url_decode,
    "url_decode_form": _url_decode_form,
    "b64_encode": _b64_encode,
    "b64_decode": _b64_decode,
    "hex_encode": _hex_encode,
    "hex_decode": _hex_decode,
    "html_encode": _html_encode,
    "html_decode": _html_decode,
    "unicode_escape": _unicode_escape,
    "unicode_unescape": _unicode_unescape,
    "json_escape": _json_escape,
    "json_unescape": _json_unescape,
    "gzip_compress": _gzip_compress,
    "gunzip": _gunzip,
    "deflate_decompress": _deflate_decompress,
    "jwt_decode": _jwt_decode,
    "json_pretty": _json_pretty,
    "json_minify": _json_minify,
    "ts_to_date": _ts_to_date,
    "date_to_ts": _date_to_ts,
    "upper": _upper,
    "lower": _lower,
    "md5": _digest("md5"),
    "sha1": _digest("sha1"),
    "sha256": _digest("sha256"),
}

#: 反向映射：可逆的转换互相指向对方（供 UI 的「反向」按钮用）
REVERSE: dict[str, str] = {
    "url_encode": "url_decode",
    "url_encode_form": "url_decode_form",
    "url_decode": "url_encode",
    "url_decode_form": "url_encode_form",
    "b64_encode": "b64_decode",
    "b64_decode": "b64_encode",
    "hex_encode": "hex_decode",
    "hex_decode": "hex_encode",
    "html_encode": "html_decode",
    "html_decode": "html_encode",
    "unicode_escape": "unicode_unescape",
    "unicode_unescape": "unicode_escape",
    "json_escape": "json_unescape",
    "json_unescape": "json_escape",
    "gzip_compress": "gunzip",
    "gunzip": "gzip_compress",
    "json_pretty": "json_minify",
    "json_minify": "json_pretty",
    "ts_to_date": "date_to_ts",
    "date_to_ts": "ts_to_date",
    "upper": "lower",
    "lower": "upper",
}

BY_KEY: dict[str, Transform] = {t.key: t for t in _TRANSFORMS}
ALL: tuple[Transform, ...] = _TRANSFORMS


def groups() -> list[tuple[str, list[Transform]]]:
    """按分组返回，供下拉框分段展示。"""
    order = (GROUP_CODEC, GROUP_FORMAT, GROUP_HASH)
    return [(name, [t for t in _TRANSFORMS if t.group == name]) for name in order]


def run(key: str, text: str) -> Result:
    """执行转换：任何异常都收敛成 Result.error，不往 UI 上抛。"""
    func = _FUNCS.get(key)
    if func is None:
        return Result(error=QCoreApplication.translate("Codec", '未知转换：{0}').format(key))
    try:
        return func(text)
    except TransformError as exc:
        return Result(error=str(exc))
    except Exception as exc:  # pragma: no cover - 兜底，避免 UI 崩
        return Result(error=f"{type(exc).__name__}: {exc}")
