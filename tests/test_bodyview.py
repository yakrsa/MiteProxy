"""body 结构化视图：纯逻辑（app/bodyview.py）+ 详情面板接线（offscreen Qt）。

纯逻辑盯三件容易出错的事：
1. JSON 判定不看走眼（content-type 变体、自动嗅探的边界）；
2. 格式化失败必须回落原文，不能吞 body；
3. 表单解析的 URL 解码与空值保留。

面板接线盯：模式切换能重渲染、JSON 着色只在 JSON 模式开、
搜索高亮在文本视图与表单表格上都生效。
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-bodyview-test-home")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

_app = None


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


from mitmproxy.http import Headers  # noqa: E402

from app.bodyview import (  # noqa: E402
    VIEW_AUTO,
    VIEW_FORM,
    VIEW_HEX,
    VIEW_IMAGE,
    VIEW_JSON,
    VIEW_RAW,
    BODY_PREVIEW_LIMIT,
    HIGHLIGHT_LIMIT,
    JSON_PARSE_LIMIT,
    WRAP_MAX_LINE_CHARS,
    WRAP_SCAN_LIMIT,
    content_encoding_of,
    decoded_note,
    decompress,
    detect_view_mode,
    format_json_body,
    format_json_text,
    hex_dump,
    is_form_content_type,
    is_image_content_type,
    is_json_content_type,
    longest_line,
    parse_urlencoded,
    should_wrap,
    sniff_decompress,
    truncation_note,
    view_mode_items,
    view_mode_label,
)
from app.ui.detail_panel import (  # noqa: E402
    BodyPane,
    MessagePane,
    WebSocketPane,
    _ws_display_url,
)


# ====================================================================== content-type 判定


class TestContentTypeDetection:
    @pytest.mark.parametrize("ct", [
        "application/json",
        "application/json; charset=utf-8",
        "text/json",
        "application/vnd.api+json",
        "application/hal+json",
        "application/problem+json",
        "application/ld+json",
    ])
    def test_json_types(self, ct):
        assert is_json_content_type(ct)

    @pytest.mark.parametrize("ct", [
        "text/html",
        "text/plain",
        "application/xml",
        "application/octet-stream",
        "application/x-www-form-urlencoded",
        "",
    ])
    def test_non_json_types(self, ct):
        assert not is_json_content_type(ct)

    def test_form_type(self):
        assert is_form_content_type("application/x-www-form-urlencoded")
        assert is_form_content_type("application/x-www-form-urlencoded; charset=UTF-8")
        assert not is_form_content_type("application/json")
        assert not is_form_content_type("multipart/form-data")

    def test_mode_items_cover_all(self):
        keys = [k for k, _ in view_mode_items()]
        assert keys == [
            VIEW_AUTO, VIEW_RAW, VIEW_JSON, VIEW_FORM, VIEW_IMAGE, VIEW_HEX
        ]
        assert view_mode_label(VIEW_IMAGE) == "图片"
        assert view_mode_label(VIEW_JSON) == "JSON"
        assert view_mode_label("nope") == "原文"

    @pytest.mark.parametrize("ct", [
        "image/png", "image/jpeg", "image/gif", "image/webp",
        "image/svg+xml", "image/x-icon", "image/bmp",
    ])
    def test_image_types(self, ct):
        assert is_image_content_type(ct)

    @pytest.mark.parametrize("ct", [
        "application/json", "text/html", "application/octet-stream", "",
    ])
    def test_non_image_types(self, ct):
        assert not is_image_content_type(ct)

    def test_image_detected_before_json(self):
        """图片优先：image/* 的字节永远不该被当文本嗅探。"""
        assert detect_view_mode("image/png", b"\x89PNG") == VIEW_IMAGE


# ====================================================================== JSON 格式化


class TestFormatJson:
    def test_pretty_and_key_order_preserved(self):
        ok, text = format_json_text('{"b":2,"a":1}')
        assert ok
        assert text == '{\n  "b": 2,\n  "a": 1\n}'

    def test_chinese_not_escaped(self):
        ok, text = format_json_text('{"name":"张三"}')
        assert ok and "张三" in text and "\\u" not in text

    def test_nested_indent(self):
        ok, text = format_json_text('{"a":{"b":[1,2]}}')
        assert ok
        assert text.splitlines()[1].startswith('  "a"')

    def test_top_level_array(self):
        ok, text = format_json_text("[1,2]")
        assert ok and text.startswith("[")

    def test_failure_returns_reason(self):
        ok, text = format_json_text("{not json")
        assert not ok
        assert "line 1" in text or "Expecting" in text      # 给 UI 当提示用

    def test_empty_string_is_failure(self):
        ok, _ = format_json_text("")
        assert not ok


# ====================================================================== 自动模式


class TestDetectViewMode:
    def test_json_by_content_type(self):
        body = b'{"a":1}'
        assert detect_view_mode("application/json", body) == VIEW_JSON

    def test_json_with_charset(self):
        assert detect_view_mode("application/json; charset=utf-8", b'{"a":1}') == VIEW_JSON

    def test_json_declared_but_broken_still_uses_json_view(self):
        """声明了 JSON 但内容解析不了（错误页、截断）→ 仍进 JSON 视图。

        内容不丢（渲染层回落原文），但会挂一句"解析失败"的原因——
        "服务端说自己是 JSON，实际不是"本身就是重要线索，不该被静默吃掉。
        """
        assert detect_view_mode("application/json", b"<html>500</html>") == VIEW_JSON

    def test_form_by_content_type(self):
        assert detect_view_mode(
            "application/x-www-form-urlencoded", b"a=1&b=2"
        ) == VIEW_FORM

    def test_no_content_type_sniffs_json(self):
        assert detect_view_mode("", b'{"a":1}') == VIEW_JSON

    def test_text_plain_sniffs_json(self):
        """有些接口声明成 text/plain 但返回 JSON——嗅探一下能省一次手动切换。"""
        assert detect_view_mode("text/plain", b'{"a":1}') == VIEW_JSON

    def test_plain_text_not_mistaken_for_json(self):
        assert detect_view_mode("text/plain", b"hello world") == VIEW_RAW

    def test_log_bracket_not_mistaken_for_json(self):
        """`[INFO] ...` 开头的日志不能被当数组——首尾字符必须是完整可解析的 JSON。"""
        assert detect_view_mode("", b"[INFO] start up") == VIEW_RAW

    def test_binary_falls_back_to_hex(self):
        assert detect_view_mode("application/octet-stream", b"\xff\xfe\x00\x01") == VIEW_HEX

    def test_empty_body(self):
        assert detect_view_mode("application/json", b"") == VIEW_RAW
        assert detect_view_mode("application/json", None) == VIEW_RAW

    def test_html_not_sniffed(self):
        """html 里含 `{` 也不当 JSON——猜错代价太大。"""
        assert detect_view_mode("text/html", b"<html>{a}</html>") == VIEW_RAW


# ====================================================================== 表单


class TestParseUrlencoded:
    def test_basic(self):
        assert parse_urlencoded("a=1&b=2") == [("a", "1"), ("b", "2")]

    def test_url_decoding(self):
        assert parse_urlencoded("name=%E5%BC%A0%E4%B8%89") == [("name", "张三")]

    def test_plus_is_space(self):
        assert parse_urlencoded("q=hello+world") == [("q", "hello world")]

    def test_blank_value_kept(self):
        """`flag=` 这种空值必须保留：前端传没传这个字段，本身就是要看的信息。"""
        assert parse_urlencoded("flag=&x=1") == [("flag", ""), ("x", "1")]

    def test_repeated_keys(self):
        assert parse_urlencoded("id=1&id=2") == [("id", "1"), ("id", "2")]

    def test_no_pairs(self):
        assert parse_urlencoded("not-a-form") == []

    def test_empty(self):
        assert parse_urlencoded("") == []


# ====================================================================== 十六进制 / 截断


class TestHexAndTruncation:
    def test_hex_dump_layout(self):
        text = hex_dump(b"\x00\x01hello")
        assert text.startswith("[二进制内容 · 十六进制视图]")
        assert "00000000" in text
        assert "hello" in text

    def test_hex_dump_total_size_note(self):
        data = b"x" * 1024
        text = hex_dump(data, total=200 * 1024, limit=512)
        assert "完整大小 200KB" in text

    def test_truncation_note(self):
        assert "完整大小 900KB" in truncation_note(900 * 1024)

# ====================================================================== 面板接线


def _headers(content_type: str, extra: dict | None = None):
    fields = {"content-type": content_type}
    fields.update(extra or {})
    return Headers(**fields)


def _pane(wrap: bool = True) -> BodyPane:
    """body 视图本体（MessagePane / WebSocketPane 都复用它）。"""
    return BodyPane(wrap_default=wrap)


class TestBodyPane:
    def test_auto_picks_json_and_shows_pretty(self):
        pane = _pane()
        pane.show_body(_headers("application/json"), b'{"b":2,"a":1}')
        assert pane.current_mode == VIEW_JSON
        assert pane.body_view.toPlainText() == '{\n  "b": 2,\n  "a": 1\n}'
        assert pane._json_highlighter.enabled
        assert pane.view_note.text() == "自动 → JSON"

    def test_mode_button_bar(self):
        """视图切换是 Fiddler 式的一排互斥按钮，不是下拉框。"""
        pane = _pane()
        assert not hasattr(pane, "mode_combo")
        assert list(pane.mode_buttons) == [VIEW_AUTO, VIEW_RAW, VIEW_JSON,
                                           VIEW_FORM, VIEW_IMAGE, VIEW_HEX]
        assert pane.mode_buttons[VIEW_AUTO].isChecked()
        assert pane.mode_group.exclusive()
        # set_mode 同步按钮选中态（先给个 body，让 current_mode 有实际解析值）
        pane.show_body(_headers("application/json"), b'{"a":1}')
        pane.set_mode(VIEW_JSON)
        assert pane.mode_buttons[VIEW_JSON].isChecked()
        assert not pane.mode_buttons[VIEW_AUTO].isChecked()
        assert pane.current_mode == VIEW_JSON
        # 未知 key 忽略，不改变当前视图
        pane.set_mode("nope")
        assert pane.current_mode == VIEW_JSON

    def test_switch_to_raw_keeps_original(self):
        pane = _pane()
        pane.show_body(_headers("application/json"), b'{"a":1}')
        pane.set_mode(VIEW_RAW)
        assert pane.body_view.toPlainText() == '{"a":1}'
        assert not pane._json_highlighter.enabled
        assert pane.current_mode == VIEW_RAW

    def test_manual_mode_is_sticky_across_messages(self):
        """手动切过之后换会话不回弹（对齐 Fiddler inspector）。"""
        pane = _pane()
        pane.show_body(_headers("application/json"), b'{"a":1}')
        pane.set_mode(VIEW_HEX)
        pane.show_body(_headers("application/json"), b'{"a":1}')
        assert pane.current_mode == VIEW_HEX
        assert "十六进制视图" in pane.body_view.toPlainText()

    def test_broken_json_falls_back_with_note(self):
        pane = _pane()
        pane.show_body(_headers("application/json"), b"{not json")
        assert pane.current_mode == VIEW_JSON
        assert pane.body_view.toPlainText() == "{not json"
        assert "JSON 解析失败" in pane.view_note.text()
        assert not pane._json_highlighter.enabled

    def test_form_renders_table_and_decodes(self):
        pane = _pane()
        pane.show_body(
            _headers("application/x-www-form-urlencoded"),
            b"name=%E5%BC%A0%E4%B8%89&flag=",
        )
        assert pane.current_mode == VIEW_FORM
        assert pane.body_stack.currentWidget() is pane.form_table
        assert pane.form_table.rowCount() == 2
        assert pane.form_table.item(0, 1).text() == "张三"
        assert pane.form_table.item(1, 1).text() == ""
        assert "已 URL 解码" in pane.view_note.text()

    def test_form_falls_back_to_raw_when_unparsable(self):
        pane = _pane()
        pane.show_body(_headers("application/json"), b"plain")
        pane.set_mode(VIEW_FORM)
        assert pane.body_stack.currentWidget() is pane.body_view
        assert pane.body_view.toPlainText() == "plain"
        assert "无法解析为表单" in pane.view_note.text()

    def test_binary_shows_hex(self):
        pane = _pane()
        pane.show_body(_headers("application/octet-stream"), b"\xff\xfe\x00")
        assert pane.current_mode == VIEW_HEX
        assert "十六进制视图" in pane.body_view.toPlainText()

    def test_empty_and_missing_body(self):
        pane = _pane()
        pane.show_body(_headers("text/plain"), b"")
        assert pane.body_view.toPlainText() == "（空 body）"
        pane.show_body(_headers("text/plain"), None)
        assert pane.body_view.toPlainText() == "（无 body）"

    def test_truncation_note_shown_when_oversized(self):
        pane = _pane()
        body = b"x" * (BODY_PREVIEW_LIMIT + 1024)
        pane.show_body(_headers("text/plain"), body)
        assert "已截断" in pane.body_view.toPlainText()
        assert "完整大小 513KB" in pane.body_view.toPlainText()

    def test_no_truncation_note_for_small_body(self):
        pane = _pane()
        pane.show_body(_headers("application/json"), b'{"a":"x"}')
        assert "已截断" not in pane.body_view.toPlainText()

    def test_highlight_in_text_view(self):
        pane = _pane()
        pane.show_body(_headers("application/json"), b'{"user":"alice"}')
        assert pane.highlight("alice", False) == 1
        assert pane.highlight("nobody", False) == 0
        assert pane.highlight("", False) == 0

    def test_highlight_in_form_table(self):
        pane = _pane()
        pane.show_body(
            _headers("application/x-www-form-urlencoded"), b"user=alice&k=1"
        )
        assert pane.body_stack.currentWidget() is pane.form_table
        assert pane.highlight("alice", False) == 1      # 命中值
        assert pane.highlight("user", False) == 1       # 命中名称
        assert pane.highlight("", False) == 0
        # 清空搜索后底色要撤掉，否则下次看表格全是黄的
        assert (pane.form_table.item(0, 1).background().style()
                == Qt.BrushStyle.NoBrush)

    def test_highlight_case_sensitive_in_table(self):
        pane = _pane()
        pane.show_body(
            _headers("application/x-www-form-urlencoded"), b"user=Alice"
        )
        assert pane.highlight("alice", True) == 0
        assert pane.highlight("Alice", True) == 1

    def test_clear_resets(self):
        msg = MessagePane()
        msg.show_message("1", _headers("application/json"), b'{"a":1}')
        msg.clear()
        assert msg.body_pane.body_view.toPlainText() == "（无 body）"
        assert msg.body_pane.form_table.rowCount() == 0
        assert msg.headers_table.rowCount() == 0


# ====================================================================== 大内容闸门


class TestLargeBodyGuards:
    def test_deep_nesting_does_not_crash(self):
        """深嵌套 JSON 会让 json.loads 抛 RecursionError——它不是 ValueError
        的子类，漏接就是整个界面崩掉。"""
        ok, reason = format_json_text("[" * 10000 + "]" * 10000)
        assert not ok
        assert "递归" in reason

    def test_deep_nesting_survives_in_pane(self):
        pane = _pane()
        pane.show_body(_headers("application/json"), b"[" * 10000 + b"]" * 10000)
        assert pane.current_mode == VIEW_JSON
        assert "递归" in pane.view_note.text()      # 内容还在，只是没格式化

    def test_big_json_still_formatted(self):
        """关键回归：以前先按 512KB 截断再解析，>512KB 的 JSON 全被截成半截、
        解析失败，用户反而失去格式化。现在先完整解析、只截断渲染结果。"""
        body = json.dumps([{"i": i} for i in range(60000)], ensure_ascii=False).encode()
        assert len(body) > BODY_PREVIEW_LIMIT
        result = format_json_body(body, "application/json")
        assert result.ok
        assert result.text.startswith("[\n  {")

    def test_big_json_render_capped(self):
        body = json.dumps({"k": "x" * (3 * 1024 * 1024)}, ensure_ascii=False).encode()
        result = format_json_body(body, "application/json")
        assert result.ok and result.truncated
        assert "已截断" in result.text

    def test_beyond_parse_limit_falls_back_to_raw(self):
        body = b'{"a":"' + b"x" * (JSON_PARSE_LIMIT + 1024) + b'"}'
        result = format_json_body(body, "application/json")
        assert not result.ok
        assert "超出格式化上限" in result.note
        assert result.text            # 原文还在，绝不返回空

    def test_highlighting_paused_for_huge_text(self):
        """着色按 block 走（2 万行约 260ms），超限就停色不停内容。"""
        pane = _pane()
        body = json.dumps(
            {"k": "y" * (HIGHLIGHT_LIMIT + 4096)}, ensure_ascii=False
        ).encode()
        pane.show_body(_headers("application/json"), body)
        assert len(pane.body_view.toPlainText()) > HIGHLIGHT_LIMIT
        assert not pane._json_highlighter.enabled


# ====================================================================== 换行


class TestWrap:
    def test_longest_line(self):
        assert longest_line("a\nabc\nab") == 3
        assert longest_line("") == 0

    def test_wrap_enabled_for_short_lines(self):
        assert should_wrap("a\nbb\nccc", True) == (True, "")

    def test_wrap_disabled_when_toggled_off(self):
        assert should_wrap("a" * 1000, False) == (False, "")

    def test_wrap_blocked_for_absurd_line(self):
        """300KB 单行换行要 1.2s（超线性）——宁可不换，也不能卡。"""
        ok, reason = should_wrap("A" * (WRAP_MAX_LINE_CHARS + 1), True)
        assert not ok
        assert "临时关闭换行" in reason

    def test_pane_applies_wrap(self):
        pane = _pane(wrap=True)
        pane.show_body(_headers("text/plain"), b"hello\nworld")
        assert pane.body_view.lineWrapMode() == \
            pane.body_view.LineWrapMode.WidgetWidth

    def test_pane_wrap_off(self):
        pane = _pane(wrap=False)
        pane.show_body(_headers("text/plain"), b"hello\nworld")
        assert pane.body_view.lineWrapMode() == \
            pane.body_view.LineWrapMode.NoWrap

    def test_wrap_note_not_duplicated_on_toggle(self):
        """反复点换行不能把提示越叠越长。"""
        pane = _pane(wrap=True)
        pane.show_body(_headers("text/plain"), b"hello")
        base = pane.view_note.text()
        for _ in range(3):
            pane.wrap_cb.setChecked(False)
            pane.wrap_cb.setChecked(True)
        assert pane.view_note.text() == base

    def test_wrap_reason_visible_when_blocked(self):
        pane = _pane(wrap=True)
        pane.show_body(_headers("text/plain"), b"A" * (WRAP_MAX_LINE_CHARS + 10))
        assert "临时关闭换行" in pane.view_note.text()

    def test_wrap_scan_window_big_multiline(self):
        """总长远超扫描窗口、但每行都短 → 仍判可换行（窗口内无超长行）。"""
        line = "x" * 50 + "\n"
        text = line * (WRAP_SCAN_LIMIT // len(line) + 10)   # > 256KB
        assert len(text) > WRAP_SCAN_LIMIT
        ok, reason = should_wrap(text, True)
        assert ok and reason == ""

    def test_wrap_scan_window_detects_long_line_inside(self):
        """窗口内出现超长单行 → 关换行（即便总长远超窗口）。"""
        text = "s\n" * 1000 + "A" * (WRAP_MAX_LINE_CHARS + 1) + "\n" + "t\n" * 100000
        ok, reason = should_wrap(text, True)
        assert not ok and "临时关闭换行" in reason

    def test_longest_line_scan_limit(self):
        """scan_limit 只扫前 N 字符：长文本不物化全文也能判定。"""
        text = "ab\n" + "c" * 5000 + "\n" + "d" * 9000
        assert longest_line(text, 3) == 2       # 窗口只含 "ab\n" → 仅首行
        assert longest_line(text, 100) == 97    # 窗口含 "ab\n"+97个c，看不到 d 行(9000)
        assert longest_line(text) == 9000       # 无限制 → 全文精确


# ====================================================================== 压缩内容


class TestCompression:
    def test_content_encoding_of(self):
        assert content_encoding_of(
            _headers("application/json", {"content-encoding": "gzip"})
        ) == "gzip"
        assert content_encoding_of(None) == ""

    def test_decompress_gzip(self):
        import gzip as _gzip

        assert decompress(_gzip.compress(b"hello world"), "gzip") == b"hello world"

    def test_decompress_unknown_returns_none(self):
        assert decompress(b"plain", "identity") is None

    def test_sniff_gzip_by_magic(self):
        import gzip as _gzip

        out, kind = sniff_decompress(_gzip.compress(b"payload"))
        assert out == b"payload" and kind == "gzip"

    def test_sniff_plain_returns_none(self):
        assert sniff_decompress(b"just text")[0] is None

    def test_note_only_when_size_changed(self):
        assert decoded_note("gzip", 100, 100) == ""
        assert "已解压 gzip" in decoded_note("gzip", 200, 1000)
        assert "手动解压" in decoded_note("gzip", 200, 1000, "fallback")

    def test_pane_shows_decoded_note(self):
        import gzip as _gzip

        raw = _gzip.compress(b'{"a":1}')
        pane = _pane()
        # raw_len 给压缩长度、body 给解压后的内容 → 说明"已解压"
        pane.show_body(
            _headers("application/json", {"content-encoding": "gzip"}),
            b'{"a":1}', raw_len=len(raw),
        )
        assert "已解压 gzip" in pane.view_note.text()

    def test_pane_fallback_when_mitmproxy_gave_up(self):
        """解压失败时 mitmproxy 把压缩字节原样返回（长度没变）→ 按魔数兜底。"""
        import gzip as _gzip

        raw = _gzip.compress("张三".encode())
        pane = _pane()
        pane.show_body(
            _headers("application/json", {"content-encoding": "gzip"}),
            raw, raw_len=len(raw),
        )
        assert pane._encoding_note.startswith("手动解压 gzip")
        assert "张三" in pane.body_view.toPlainText()


# ====================================================================== 图片


def _png_bytes() -> bytes:
    """最小合法 PNG（1×1）— 不依赖 Pillow，手工拼。"""
    import struct
    import zlib as _zlib

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", _zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    raw = b"\x00" + b"\x00\x00\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", _zlib.compress(raw)) + chunk(b"IEND", b""))


class TestImage:
    def test_png_previewed(self):
        pane = _pane()
        pane.show_body(_headers("image/png"), _png_bytes())
        assert pane.current_mode == VIEW_IMAGE
        assert pane.body_stack.currentWidget() is pane.image_view
        assert not pane.zoom_combo.isHidden()      # 图片模式下显出缩放档位
        assert "PNG" in pane.view_note.text()

    def test_broken_image_falls_back_to_hex(self):
        pane = _pane()
        pane.show_body(_headers("image/png"), b"not really a png")
        assert "无法渲染为图片" in pane.view_note.text()
        assert "十六进制视图" in pane.body_view.toPlainText()

    def test_svg_previewed(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"></svg>'
        pane = _pane()
        pane.show_body(_headers("image/svg+xml"), svg)
        assert pane.current_mode == VIEW_IMAGE
        assert "SVG" in pane.view_note.text()

    def test_highlight_returns_zero_for_image(self):
        pane = _pane()
        pane.show_body(_headers("image/png"), _png_bytes())
        assert pane.highlight("x", False) == 0

    def test_zoom_switch_does_not_crash(self):
        pane = _pane()
        pane.show_body(_headers("image/png"), _png_bytes())
        for i in range(pane.zoom_combo.count()):
            pane.zoom_combo.setCurrentIndex(i)


# ====================================================================== WebSocket


class _FakeMessage:
    def __init__(self, content, from_client=True, text=True, ts=0.0):
        self.content = content
        self.from_client = from_client
        self.is_text = text
        self.type = type("Op", (), {"name": "TEXT" if text else "BINARY"})()
        self.timestamp = ts


class _FakeWebSocket:
    def __init__(self, messages):
        self.messages = messages
        self.close_code = None
        self.close_reason = ""
        self.timestamp_end = None
        self.closed_by_client = False


class _FakeFlow:
    def __init__(self, flow_id, messages):
        self.id = flow_id
        self.websocket = _FakeWebSocket(messages)
        self.request = type("R", (), {"pretty_url": "ws://x/socket"})()
        self.response = None


class TestWebSocketPane:
    def test_messages_listed(self):
        pane = WebSocketPane()
        flow = _FakeFlow("f1", [
            _FakeMessage(b"hello", from_client=True, ts=1700000000.0),
            _FakeMessage(b"world", from_client=False, ts=1700000001.0),
        ])
        pane.show_flow(flow)
        assert pane.table.rowCount() == 2
        assert pane.table.item(0, 2).text() == "→ 发送"
        assert pane.table.item(1, 2).text() == "← 接收"
        assert pane.table.item(0, 5).text() == "hello"
        assert "共 2 条消息" in pane.info_label.text()

    def test_incremental_refresh_keeps_rows(self):
        pane = WebSocketPane()
        flow = _FakeFlow("f1", [_FakeMessage(b"a")])
        pane.show_flow(flow)
        flow.websocket.messages.append(_FakeMessage(b"b"))
        assert pane.refresh(flow) is True
        assert pane.table.rowCount() == 2
        assert pane.refresh(flow) is False      # 没新消息就不动

    def test_selecting_message_shows_payload(self):
        pane = WebSocketPane()
        flow = _FakeFlow("f1", [_FakeMessage(json.dumps({"k": 1}).encode())])
        pane.show_flow(flow)
        pane.table.selectRow(0)
        assert pane.body_pane.body_view.toPlainText().startswith('{\n  "k": 1')

    def test_binary_message_preview_is_hex(self):
        pane = WebSocketPane()
        flow = _FakeFlow("f1", [_FakeMessage(b"\x00\x01", text=False)])
        pane.show_flow(flow)
        assert "00 01" in pane.table.item(0, 5).text()
        assert pane.table.item(0, 3).text() == "BINARY"

    def test_clear(self):
        pane = WebSocketPane()
        flow = _FakeFlow("f1", [_FakeMessage(b"a")])
        pane.show_flow(flow)
        pane.clear()
        assert pane.table.rowCount() == 0


class TestWsDisplayUrl:
    """握手请求行是 http://（RFC 6455 规定），给人看要显示 ws://。"""

    def test_http_becomes_ws(self):
        assert _ws_display_url("http://x.test/socket") == "ws://x.test/socket"

    def test_https_becomes_wss(self):
        assert _ws_display_url("https://x.test/s") == "wss://x.test/s"

    def test_already_ws_untouched(self):
        assert _ws_display_url("ws://x.test/s") == "ws://x.test/s"

    def test_pane_info_uses_ws_scheme(self):
        pane = WebSocketPane()
        flow = _FakeFlow("f1", [_FakeMessage(b"a")])
        flow.request.pretty_url = "http://x.test/socket"
        pane.show_flow(flow)
        assert pane.info_label.text().startswith("ws://x.test/socket")
