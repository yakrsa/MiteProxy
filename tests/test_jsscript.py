"""CustomRules.js 导入器测试。"""

from addons.importers import jsscript

TYPICAL_JS = """
static function OnBeforeRequest(oSession: Session) {
    // 用户信息-空列表
    if (oSession.uriContains("/api/user/list")) {
        oSession.utilCreateResponseAndBypassServer();
        oSession.responseCode = 200;
        oSession.utilSetResponseBody('{"total":0,"items":[]}');
        oSession.oResponse.headers.Add("Content-Type", "application/json");
    }
    if (oSession.uriContains("/api/order/detail")) {
        oSession.utilCreateResponseAndBypassServer();
        oSession.responseCode = 503;
        oSession.utilSetResponseBody("service unavailable");
    }
    // 正则命中
    if (/\\/v1\\/user\\/(\\d+)\\/detail/.test(oSession.URI)) {
        oSession.utilCreateResponseAndBypassServer();
        oSession.responseCode = 200;
        oSession.utilSetResponseBody('{"id":"$1"}');
    }
    // 本地文件
    if (oSession.uriContains("/api/config")) {
        oSession["x-replywithfile"] = "C:\\\\mocks\\\\config.json";
    }
}
"""

COMPLEX_JS = """
static function OnBeforeRequest(oSession: Session) {
    if (oSession.uriContains("/api/dynamic")) {
        oSession.utilCreateResponseAndBypassServer();
        oSession.utilSetResponseBody('{"t":"' + new Date() + '"}');
    }
    if (oSession.HTTPMethodIs("POST") && oSession.uriContains("/api/x")) {
        FiddlerApplication.Log.LogString("just logging");
    }
    var counter = 0;
    if (counter > 5) {
        oSession.utilCreateResponseAndBypassServer();
    }
}
"""

NO_FUNC_JS = "// 只有注释，没有函数"


def _write(tmp_path, content):
    f = tmp_path / "CustomRules.js"
    f.write_text(content, encoding="utf-8")
    return f


def test_typical_patterns(tmp_path):
    result = jsscript.parse_file(_write(tmp_path, TYPICAL_JS))
    assert result.ok_count == 4
    assert result.skip_count == 0

    by_match = {r.match.value: r for r in result.rules}

    r = by_match["/api/user/list"]
    assert r.name == "用户信息-空列表"  # 取自上方注释
    assert r.action.status == 200
    assert r.action.body == '{"total":0,"items":[]}'
    assert r.action.headers == {"Content-Type": "application/json"}

    r = by_match["/api/order/detail"]
    assert r.action.status == 503
    assert r.action.body == "service unavailable"

    r = by_match[r"\/v1\/user\/(\d+)\/detail"]
    assert r.match.type == "regex"
    assert r.action.body == '{"id":"$1"}'

    r = by_match["/api/config"]
    assert r.action.body_source == "file"
    assert r.action.file_path == "C:\\mocks\\config.json"


def test_complex_blocks_skipped(tmp_path):
    result = jsscript.parse_file(_write(tmp_path, COMPLEX_JS))
    # 动态拼接 → 跳过；日志块无 mock 内容 → 跳过；counter 块无 URL 条件 → 跳过
    assert result.ok_count == 0
    assert result.skip_count == 3
    reasons = " ".join(reason for _, reason in result.skipped)
    assert "动态拼接" in reasons


def test_missing_onbeforerequest(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="OnBeforeRequest"):
        jsscript.parse_file(_write(tmp_path, NO_FUNC_JS))


def test_empty_function(tmp_path):
    js = "static function OnBeforeRequest(oSession: Session) {\n}\n"
    result = jsscript.parse_file(_write(tmp_path, js))
    assert result.ok_count == 0
    assert result.skip_count == 1


def test_braces_inside_string_not_miscounted(tmp_path):
    """字符串里的 } 不应导致函数体截断。"""
    js = """
static function OnBeforeRequest(oSession: Session) {
    if (oSession.uriContains("/api/brace")) {
        oSession.utilCreateResponseAndBypassServer();
        oSession.utilSetResponseBody('{"nested":"}"}');
    }
}
"""
    result = jsscript.parse_file(_write(tmp_path, js))
    assert result.ok_count == 1
    assert result.rules[0].action.body == '{"nested":"}"}'
