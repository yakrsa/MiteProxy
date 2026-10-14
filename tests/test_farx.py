"""FARX 导入器测试：使用 Telerik 官方规则仓库真实样本回归。"""

from pathlib import Path

import pytest

from addons.importers import farx

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_official_map_local_manual():
    """官方样本：contains 条件 + 手工响应（Headers/Body）。"""
    result = farx.parse_file(FIXTURES / "map-local-manual.farx")
    assert result.ok_count == 1
    rule = result.rules[0]
    assert rule.match.type == "contains"
    assert rule.match.value == "example.com"
    assert rule.action.status == 200
    assert rule.action.headers.get("Content-Type") == "text/html; charset=UTF-8"
    assert "<!doctype html>" in rule.action.body.lower()
    assert rule.name == "Map Local (Manual)"
    assert rule.source == "farx"


def test_parse_official_map_remote_redirect():
    """官方样本：contains 条件 + type 6 重定向 → 307 + Location + 正则匹配。"""
    result = farx.parse_file(FIXTURES / "map-remote.farx")
    assert result.ok_count == 1
    rule = result.rules[0]
    assert rule.action.status == 307
    assert rule.action.headers.get("Location") == "http://localhost:4000/$2"
    # 重定向映射为正则匹配（find 正则体），$2 由 mock 引擎替换
    assert rule.match.type == "regex"
    assert rule.match.value == "(.*example.com/)(.*)"
    m = rule.match.match_url("http://example.com/api/data")
    assert m is not False and m.group(2) == "api/data"


def test_parse_nonexistent_file():
    with pytest.raises(OSError):
        farx.parse_file(FIXTURES / "not-exist.farx")


def test_parse_garbage_file(tmp_path):
    bad = tmp_path / "bad.farx"
    bad.write_text("this is not xml <<<", encoding="utf-8")
    with pytest.raises(ValueError, match="FARX"):
        farx.parse_file(bad)


def test_parse_empty_ruleset(tmp_path):
    empty = tmp_path / "empty.farx"
    empty.write_text(
        '<?xml version="1.0" encoding="utf-8"?><AutoResponder RulesVersion="2">'
        "<State Enabled=\"true\"></State></AutoResponder>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ResponseRule"):
        farx.parse_file(empty)


def test_binary_body_goes_to_file(tmp_path, monkeypatch):
    """二进制 body（非 UTF-8）应落缓存文件走 file 模式。"""
    import base64

    from app import rules as rules_mod

    home = tmp_path / "cfg"
    home.mkdir()
    monkeypatch.setattr(rules_mod, "CONFIG_DIR", home)

    png = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0xFF, 0xFE])
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<AutoResponder RulesVersion="2"><State Enabled="true">'
        '<ResponseRule Comment="img" Enabled="true" '
        'Match="{&quot;matches&quot;:[&quot;%%eyJ0eXBlIjo0LCJjb25kaXRpb24iOiJjb250YWlucyIsInZhbHVlIjoiYXBpLmltZyJ9&quot;]}" '
        'Action="[]" '
        f'Headers="{base64.b64encode(b"HTTP/1.1 200 OK\\r\\ncontent-type: image/png").decode()}" '
        f'Body="{base64.b64encode(png).decode()}" />'
        "</State></AutoResponder>"
    )
    f = tmp_path / "img.farx"
    f.write_text(xml, encoding="utf-8")

    result = farx.parse_file(f)
    assert result.ok_count == 1
    rule = result.rules[0]
    assert rule.action.body_source == "file"
    assert Path(rule.action.file_path).read_bytes() == png
