"""编码转换（对齐 Fiddler TextWizard）：纯逻辑 app/codec.py + 面板接线。

纯逻辑盯这些容易错的点：
1. URL 的 `+` 语义（表单 vs 路径）不能混；
2. Base64 输入校验要严格——宽松解析会让「随便一段文本都解得出乱码」；
3. 解码结果不是 UTF-8 时按字节回落并说明，而不是报错丢内容；
4. gzip/deflate 的输入既可能是 Base64 也可能是 Hex，两种都要能认；
5. 任何失败都收敛成 Result.error，不往 UI 抛。
"""

import base64
import gzip
import json
import os
import sys
import zlib
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-codec-test-home")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.codec import (  # noqa: E402
    ALL,
    BY_KEY,
    GROUP_CODEC,
    GROUP_FORMAT,
    GROUP_HASH,
    LIVE_LIMIT,
    QUICK_KEYS,
    REVERSE,
    groups,
    run,
)

_app = None


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def out(key: str, text: str) -> str:
    result = run(key, text)
    assert result.error is None, result.error
    return result.text


# ================================================================ URL


class TestUrl:
    def test_encode_spaces_and_chinese(self):
        assert out("url_encode", "a b") == "a%20b"
        assert out("url_encode", "张三") == "%E5%BC%A0%E4%B8%89"

    def test_encode_form_uses_plus(self):
        assert out("url_encode_form", "a b") == "a+b"
        assert out("url_encode_form", "张三") == "%E5%BC%A0%E4%B8%89"

    def test_decode_keeps_plus(self):
        """路径/query 里的 + 是加号本身，不该被当空格。"""
        assert out("url_decode", "a+b") == "a+b"
        assert out("url_decode", "a%20b") == "a b"

    def test_decode_form_plus_is_space(self):
        assert out("url_decode_form", "a+b") == "a b"
        assert out("url_decode_form", "%E5%BC%A0%E4%B8%89") == "张三"

    def test_roundtrip(self):
        for raw in ("张三", "a/b?c=1&d=2", "100%", "~,._-"):
            assert out("url_decode", out("url_encode", raw)) == raw

    def test_bad_percent_sequence_does_not_raise(self):
        """%zz 不是合法序列——原样保留，别抛异常。"""
        assert "%zz" in out("url_decode", "a%zzb")

    def test_non_utf8_bytes_fall_back_with_note(self):
        result = run("url_decode", "%FF%FE")
        assert result.error is None
        assert result.note and "UTF-8" in result.note


# ================================================================ Base64


class TestBase64:
    def test_encode_ascii_and_chinese(self):
        assert out("b64_encode", "hello") == "aGVsbG8="
        assert out("b64_encode", "张三") == base64.b64encode("张三".encode()).decode()

    def test_roundtrip(self):
        assert out("b64_decode", out("b64_encode", "张三 hello")) == "张三 hello"

    def test_tolerates_whitespace_and_linebreaks(self):
        assert out("b64_decode", "aGVs\nbG8 =") == "hello"

    def test_urlsafe_alphabet(self):
        raw = b"\xfb\xff~?"
        token = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        assert out("b64_decode", token) == raw.decode("latin-1")

    def test_rejects_plain_text_instead_of_silent_garbage(self):
        """宽松解析会把任意文本解成乱码——必须明确报错。"""
        result = run("b64_decode", "这不是 base64")
        assert result.error and "Base64" in result.error

    def test_rejects_bad_length(self):
        result = run("b64_decode", "AAAAA")
        assert result.error

    def test_empty_input_is_empty_output(self):
        assert out("b64_decode", "") == ""

    def test_non_utf8_result_note(self):
        result = run("b64_decode", base64.b64encode(b"\xff\xfe").decode())
        assert result.error is None
        assert result.note and "UTF-8" in result.note


# ================================================================ Hex


class TestHex:
    def test_roundtrip(self):
        assert out("hex_encode", "hi") == "6869"
        assert out("hex_decode", "6869") == "hi"

    def test_decode_accepts_separators_and_prefix(self):
        assert out("hex_decode", "68:69 6a") == "hij"
        assert out("hex_decode", "0x6869") == "hi"

    def test_odd_length_reported(self):
        result = run("hex_decode", "686")
        assert result.error and "偶数" in result.error

    def test_non_hex_reported(self):
        result = run("hex_decode", "zz")
        assert result.error and "十六进制" in result.error


# ================================================================ HTML / Unicode / JSON


class TestTextEscapes:
    def test_html_roundtrip(self):
        assert out("html_encode", '<a href="x">&') == "&lt;a href=&quot;x&quot;&gt;&amp;"
        assert out("html_decode", "&lt;a&gt;&amp;") == "<a>&"

    def test_unicode_escape(self):
        assert out("unicode_escape", "中") == "\\u4e2d"
        assert out("unicode_escape", "a\nb") == "a\\nb"

    def test_unicode_unescape(self):
        assert out("unicode_unescape", "\\u4e2d\\u6587") == "中文"
        assert out("unicode_unescape", "a\\nb") == "a\nb"

    def test_unicode_roundtrip_with_mixed_content(self):
        raw = "中文 abc \n"
        assert out("unicode_unescape", out("unicode_escape", raw)) == raw

    def test_json_escape_has_no_outer_quotes(self):
        assert out("json_escape", 'a"b') == 'a\\"b'
        assert out("json_escape", "a\nb") == "a\\nb"

    def test_json_unescape_accepts_bare_and_quoted(self):
        assert out("json_unescape", 'a\\"b') == 'a"b'
        assert out("json_unescape", '"a\\"b"') == 'a"b'

    def test_json_unescape_reports_bad_input(self):
        result = run("json_unescape", 'a"b')
        assert result.error

    def test_json_pretty_and_minify(self):
        raw = '{"b":2,"a":[1,2]}'
        pretty = out("json_pretty", raw)
        assert '\n  "b": 2' in pretty
        assert out("json_minify", pretty) == raw

    def test_json_pretty_keeps_chinese(self):
        assert "张三" in out("json_pretty", '{"n":"张三"}')

    def test_json_pretty_reports_bad_json(self):
        assert run("json_pretty", "{not json").error


# ================================================================ 压缩


class TestCompression:
    def test_gzip_roundtrip(self):
        packed = out("gzip_compress", "hello 张三")
        assert out("gunzip", packed) == "hello 张三"

    def test_gzip_is_deterministic(self):
        """mtime 必须固定，否则同样输入两次结果不同，没法对照。"""
        assert out("gzip_compress", "x") == out("gzip_compress", "x")

    def test_gunzip_accepts_hex_too(self):
        packed = gzip.compress(b"hello", mtime=0)
        assert out("gunzip", packed.hex()) == "hello"

    def test_gunzip_reports_non_gzip(self):
        result = run("gunzip", base64.b64encode(b"not gzip at all").decode())
        assert result.error and "Gzip" in result.error

    def test_deflate_raw(self):
        compressor = zlib.compressobj(wbits=-15)
        raw = compressor.compress(b"hello deflate") + compressor.flush()
        assert out("deflate_decompress", base64.b64encode(raw).decode()) == "hello deflate"

    def test_deflate_zlib_wrapper(self):
        raw = zlib.compress(b"hello zlib")
        assert out("deflate_decompress", raw.hex()) == "hello zlib"

    def test_deflate_reports_garbage(self):
        result = run("deflate_decompress", base64.b64encode(b"??").decode())
        assert result.error


# ================================================================ JWT / 时间 / 文本


def _jwt(payload: dict) -> str:
    def seg(obj) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(obj, ensure_ascii=False).encode()
        ).decode().rstrip("=")

    return f"{seg({'alg': 'HS256', 'typ': 'JWT'})}.{seg(payload)}.signature"


class TestJwt:
    def test_decodes_header_and_payload(self):
        text = out("jwt_decode", _jwt({"sub": "u1", "name": "张三"}))
        assert "HS256" in text and "张三" in text
        assert "signature（未校验签名）".replace("（", "（") in text or "signature" in text

    def test_strips_bearer_prefix(self):
        token = _jwt({"sub": "u1"})
        assert out("jwt_decode", f"Bearer {token}") == out("jwt_decode", token)

    def test_expired_token_noted(self):
        result = run("jwt_decode", _jwt({"exp": 1_000_000_000}))
        assert result.note and "已过期" in result.note

    def test_valid_exp_noted(self):
        result = run("jwt_decode", _jwt({"exp": 4_000_000_000}))
        assert result.note and "剩余" in result.note

    def test_rejects_non_jwt(self):
        assert run("jwt_decode", "abc").error


class TestTime:
    def test_seconds(self):
        text = out("ts_to_date", "1760000000")
        assert "2025" in text and "秒" in text

    def test_milliseconds(self):
        text = out("ts_to_date", "1760000000000")
        assert "毫秒" in text

    def test_rejects_non_number(self):
        assert run("ts_to_date", "昨天").error

    def test_date_to_ts_roundtrip(self):
        stamp = out("date_to_ts", "2025-10-09 20:53:20").splitlines()[0]
        assert "2025-10-09" in out("ts_to_date", stamp)

    def test_rejects_timestamp_looking_input(self):
        """纯数字多半是时间戳，别当成日期解析出离谱结果。"""
        assert run("date_to_ts", "1760000000").error

    def test_accepts_iso_with_zone(self):
        assert out("date_to_ts", "2025-10-09T12:00:00Z").splitlines()[0].isdigit()


class TestCase:
    def test_upper_lower(self):
        assert out("upper", "abc中文") == "ABC中文"
        assert out("lower", "ABC中文") == "abc中文"


class TestHash:
    def test_known_digests(self):
        assert out("md5", "abc") == "900150983cd24fb0d6963f7d28e17f72"
        assert len(out("sha1", "abc")) == 40
        assert len(out("sha256", "abc")) == 64


# ================================================================ 注册表自洽


class TestRegistry:
    def test_every_key_has_implementation(self):
        for transform in ALL:
            result = run(transform.key, "")
            assert result.error is None, f"{transform.key} 缺实现或空输入报错"

    def test_keys_unique(self):
        assert len(BY_KEY) == len(ALL)

    def test_groups_cover_all(self):
        grouped = [t for _, items in groups() for t in items]
        assert len(grouped) == len(ALL)
        assert {name for name, _ in groups()} == {GROUP_CODEC, GROUP_FORMAT, GROUP_HASH}

    def test_quick_keys_exist(self):
        assert all(key in BY_KEY for key in QUICK_KEYS)

    def test_reverse_is_involutive_and_valid(self):
        """反向映射必须成对且两端都存在，否则 UI 的「反向」会跳到不存在的项。"""
        for key, target in REVERSE.items():
            assert key in BY_KEY and target in BY_KEY
            assert REVERSE.get(target) == key

    def test_unknown_key_reports(self):
        assert run("nope", "x").error


# ================================================================ 面板接线


from app.ui.codec_panel import CodecPanel  # noqa: E402


def _panel() -> CodecPanel:
    panel = CodecPanel()
    panel.resize(900, 600)
    return panel


class TestCodecPanel:
    def test_default_key_is_first_quick(self):
        panel = _panel()
        assert panel.current_key == QUICK_KEYS[0]
        assert panel.combo.currentData() == QUICK_KEYS[0]

    def test_group_headers_are_not_selectable(self):
        panel = _panel()
        first = panel.combo.model().item(0)
        assert first is not None
        assert not (first.flags() & Qt.ItemFlag.ItemIsEnabled)

    def test_typing_converts_live(self):
        panel = _panel()
        panel.set_key("b64_encode")
        panel.input_edit.setPlainText("hello")
        panel.run_now()  # 与防抖定时器走同一条路径
        assert panel.output_edit.toPlainText() == "aGVsbG8="

    def test_switching_transform_reruns(self):
        panel = _panel()
        panel.input_edit.setPlainText("a b")
        panel.set_key("url_encode")
        panel.run_now()  # 与防抖定时器走同一条路径
        assert panel.output_edit.toPlainText() == "a%20b"
        panel.set_key("b64_encode")  # 换转换 → 自动重跑
        assert panel.output_edit.toPlainText() == "YSBi"

    def test_quick_button_syncs_combo(self):
        panel = _panel()
        panel.quick_buttons["b64_decode"].click()
        assert panel.current_key == "b64_decode"
        assert panel.quick_buttons["b64_decode"].isChecked()
        assert not panel.quick_buttons["b64_encode"].isChecked()

    def test_error_shown_in_status_and_output_cleared(self):
        panel = _panel()
        panel.set_key("b64_decode")
        panel.input_edit.setPlainText("这不是 base64")
        panel.run_now()
        assert panel.output_edit.toPlainText() == ""
        assert "Base64" in panel.status_label.text()

    def test_reverse_swaps_and_feeds_back(self):
        panel = _panel()
        panel.set_key("b64_encode")
        panel.input_edit.setPlainText("张三")
        panel.run_now()
        panel.reverse_btn.click()
        assert panel.current_key == "b64_decode"
        assert panel.output_edit.toPlainText() == "张三"

    def test_reverse_disabled_for_hash(self):
        panel = _panel()
        panel.set_key("md5")
        assert not panel.reverse_btn.isEnabled()

    def test_feed_back_moves_result_to_input(self):
        panel = _panel()
        panel.set_key("upper")
        panel.input_edit.setPlainText("abc")
        panel.run_now()
        panel.feed_btn.click()
        assert panel.input_edit.toPlainText() == "ABC"

    def test_copy_result(self, monkeypatch):
        panel = _panel()
        copied = {}
        monkeypatch.setattr(
            QApplication, "clipboard", staticmethod(lambda: _Clipboard(copied))
        )
        panel.set_key("upper")
        panel.input_edit.setPlainText("abc")
        panel.run_now()
        assert panel.copy_result() is True
        assert copied.get("text") == "ABC"

    def test_copy_empty_result_reports(self):
        panel = _panel()
        assert panel.copy_result() is False
        assert "为空" in panel.status_label.text()

    def test_clear_resets_both(self):
        panel = _panel()
        panel.input_edit.setPlainText("abc")
        panel.run_now()
        panel.clear_btn.click()
        assert panel.input_edit.toPlainText() == ""
        assert panel.output_edit.toPlainText() == ""

    def test_set_input_with_key(self):
        panel = _panel()
        panel.set_input("aGVsbG8=", key="b64_decode")
        assert panel.current_key == "b64_decode"
        assert panel.output_edit.toPlainText() == "hello"

    def test_live_conversion_paused_for_huge_input(self):
        """几 MB 文本每敲一个字全量重算会卡——超过阈值就交给「立即转换」。"""
        panel = _panel()
        big = "x" * (LIVE_LIMIT + 1)
        panel.input_edit.setPlainText(big)  # 触发 textChanged → _schedule
        assert not panel._timer.isActive()
        assert "已暂停自动转换" in panel.status_label.text()
        # 手动点按钮照样能跑
        panel.set_key("md5")
        panel.run_now()
        assert len(panel.output_edit.toPlainText()) == 32

    def test_counts_shown(self):
        panel = _panel()
        panel.input_edit.setPlainText("张三")
        assert "字节" in panel.input_count.text()


class _Clipboard:
    def __init__(self, sink: dict):
        self._sink = sink

    def setText(self, text: str) -> None:
        self._sink["text"] = text


# ================================================================ 主窗口接线


class _FakeMessage:
    def __init__(self, content: bytes, content_type: str = ""):
        self._content = content
        self.raw_content = content
        self.headers = {"content-type": content_type} if content_type else {}

    def get_content(self, strict: bool = False) -> bytes:
        return self._content


class _FakeFlow:
    def __init__(self, response=None, request=None):
        self.id = "f1"
        self.request = request
        self.response = response


from app.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    if not home.exists():
        home.mkdir(parents=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    win = MainWindow(restore_prompt=False)
    yield win
    win.close()


class TestMainWindowWiring:
    def test_tool_tab_present(self, window):
        labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert "工具" in labels
        assert window.tabs.widget(labels.index("工具")) is window.tool_panel
        assert window.tool_panel.tabs.tabText(0) == "编码转换"
        assert window.tool_panel.tabs.tabText(1) == "JSON"

    def test_goto_codec_page(self, window):
        window.tabs.setCurrentIndex(0)
        window._goto_tool("codec")
        assert window.tabs.currentWidget() is window.tool_panel
        assert window.tool_panel.current_key == "codec"

    def test_send_body_to_codec_uses_response(self, window, monkeypatch):
        body = '{"n":"张三"}'.encode("utf-8")
        flow = _FakeFlow(response=_FakeMessage(body, "application/json"))
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])
        window._send_body_to_tool()
        assert window.tabs.currentWidget() is window.tool_panel
        assert window.tool_panel.codec_panel.input_edit.toPlainText() == '{"n":"张三"}'

    def test_send_body_falls_back_to_request(self, window, monkeypatch):
        flow = _FakeFlow(request=_FakeMessage(b"a=1&b=2"))
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])
        window._send_body_to_tool()
        assert window.tool_panel.codec_panel.input_edit.toPlainText() == "a=1&b=2"

    def test_send_binary_body_as_hex(self, window, monkeypatch):
        flow = _FakeFlow(response=_FakeMessage(b"\xff\xfe\x00"))
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])
        window._send_body_to_tool()
        assert window.tool_panel.codec_panel.input_edit.toPlainText() == "fffe00"

    def test_send_body_without_body_does_nothing(self, window, monkeypatch):
        flow = _FakeFlow(response=_FakeMessage(b""))
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])
        window._send_body_to_tool()
        assert window.tool_panel.codec_panel.input_edit.toPlainText() == ""

    def test_send_body_to_json_page_when_json_page_active(self, window, monkeypatch):
        """停在 JSON 子页时送过去就该进 JSON 页并直接格式化。"""
        window.tool_panel.show_page("json")
        body = '{"a":1}'.encode("utf-8")
        flow = _FakeFlow(response=_FakeMessage(body, "application/json"))
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])
        window._send_body_to_tool()
        assert window.tool_panel.current_key == "json"
        assert window.tool_panel.json_panel.input_edit.toPlainText() == '{"a":1}'
        assert window.tool_panel.json_panel.text_view.toPlainText() == (
            '{\n  "a": 1\n}'
        )
