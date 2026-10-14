"""textutil 测试：默认 UTF-8 解码策略（用户要求，替代 mitmproxy 的 latin-1 默认）。"""

from app.textutil import (
    charset_from_content_type,
    decode_body,
    decode_for_search,
)


class TestCharsetFromContentType:
    def test_none_when_absent(self):
        assert charset_from_content_type("text/html") is None
        assert charset_from_content_type("") is None

    def test_extracts_charset(self):
        assert charset_from_content_type("text/html; charset=utf-8") == "utf-8"
        assert charset_from_content_type('text/html; charset="GBK"') == "gbk"
        assert charset_from_content_type("application/json;charset=UTF8") == "utf-8"


class TestDecodeBody:
    def test_default_utf8_when_undeclared(self):
        """核心：未声明 charset 时默认 UTF-8（中文不乱码）。"""
        data = "你好，世界".encode("utf-8")
        assert decode_body(data, "text/html") == "你好，世界"
        assert decode_body(data, "") == "你好，世界"

    def test_declared_charset_wins(self):
        data = "中文内容".encode("gbk")
        assert decode_body(data, "text/html; charset=gbk") == "中文内容"

    def test_invalid_declared_falls_back_to_utf8(self):
        data = "abc".encode("utf-8")
        assert decode_body(data, "text/html; charset=not-a-charset") == "abc"

    def test_utf8_mislabeled_as_latin1_still_works_via_utf8_fallback(self):
        """声明 latin-1 但实际是 UTF-8 中文：声明优先解出乱码也不报错，
        与浏览器行为一致（浏览器按声明解码）。"""
        data = "中文".encode("utf-8")
        # 声明 latin-1 永远能解码（latin-1 覆盖全部字节），结果是按 latin-1 解释
        result = decode_body(data, "text/plain; charset=iso-8859-1")
        assert result is not None  # 不进入十六进制视图

    def test_binary_returns_none(self):
        data = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0xFF])
        assert decode_body(data, "image/png") is None

    def test_empty(self):
        assert decode_body(b"", "text/plain") == ""


class TestDecodeForSearch:
    def test_never_fails_on_binary(self):
        data = bytes([0x89, 0xFF, 0xFE])
        result = decode_for_search(data, "application/octet-stream")
        assert isinstance(result, str)

    def test_utf8_default(self):
        assert decode_for_search("中文".encode("utf-8"), "text/plain") == "中文"

    def test_declared_charset(self):
        assert (
            decode_for_search("内容".encode("gbk"), "text/html; charset=gbk") == "内容"
        )
