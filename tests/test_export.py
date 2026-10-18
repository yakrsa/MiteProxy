"""导出与复制（DESIGN.md 3.2.3）：cURL / 原始报文 / 完整响应 / HAR 1.2 / 响应 Body。

用真实的 mitmproxy Request/Response/HTTPFlow 对象造数据，断言导出的逐字内容
——避免鸭子类型假对象掩盖真实 API 差异。
"""

import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mitmproxy.http import HTTPFlow, Request, Response  # noqa: E402

from app.export import (  # noqa: E402
    FORMAT_BODY,
    FORMAT_HAR,
    FORMAT_RAW,
    FORMAT_RESPONSE,
    REQUIRES_RESPONSE,
    build_curl,
    build_har,
    build_har_json,
    build_raw,
    build_response,
    body_filename,
    default_filename,
    ensure_suffix,
    export_bytes,
    name_filters,
)

DEFAULT_URL = "https://api.example.com/v1/user?page=1&size=20"


def _flow(
    method="GET",
    url=DEFAULT_URL,
    req_body=b"",
    req_headers=None,
    status=200,
    res_body=b'{"ok":true}',
    res_headers=None,
    marked="",
    with_response=True,
):
    headers = {"Host": "api.example.com", "Accept": "*/*"}
    headers.update(req_headers or {})
    req = Request.make(method, url, content=req_body, headers=headers)
    res = Response.make(
        status,
        content=res_body,
        headers=res_headers if res_headers is not None else {"Content-Type": "application/json"},
    )
    flow = HTTPFlow(client_conn=None, server_conn=None)
    flow.request = req
    flow.response = res if with_response else None
    flow.marked = marked
    return flow


class TestBuildCurl:
    def test_get_has_no_method_flag(self):
        line = build_curl(_flow())
        assert line.startswith("curl 'https://api.example.com/v1/user?page=1&size=20'")
        assert " -X " not in line
        assert "--data-binary" not in line

    def test_get_keeps_captured_headers(self):
        """除 Host / 伪头外，抓到的头原样带上（content-length 等也不丢）。"""
        line = build_curl(_flow(req_headers={"Content-Type": "application/json"}))
        assert "-H 'Accept: */*'" in line
        assert "-H 'Content-Type: application/json'" in line

    def test_post_includes_method_and_body(self):
        line = build_curl(
            _flow(
                method="POST",
                url="https://api.example.com/v1/order",
                req_body=b'{"amount":199}',
                req_headers={"Content-Type": "application/json"},
            )
        )
        assert line.startswith("curl -X POST 'https://api.example.com/v1/order' ")
        assert "-H 'Content-Type: application/json'" in line
        assert line.endswith("--data-binary '{\"amount\":199}'")

    def test_host_header_skipped(self):
        """Host 交给 curl 自己带，避免手改 URL 后 Host 不一致。"""
        assert "Host:" not in build_curl(_flow())

    def test_pseudo_headers_skipped(self):
        flow = _flow()
        flow.request.headers[":method"] = "GET"
        assert ":method" not in build_curl(flow)

    def test_single_quote_escaped_for_posix(self):
        line = build_curl(_flow(req_body=b"a'b", req_headers={"Content-Type": "text/plain"}))
        assert "'\\''" in line
        assert line.endswith("--data-binary 'a'\\''b'")

    def test_cmd_style_uses_double_quotes(self):
        line = build_curl(_flow(), style="cmd")
        assert line.startswith('curl "https://api.example.com/v1/user?page=1&size=20"')
        assert '-H "Accept: */*"' in line
        assert "'" not in line

    def test_cmd_style_escapes_inner_double_quote(self):
        line = build_curl(
            _flow(method="POST", req_body=b'{"a":1}', req_headers={"Content-Type": "application/json"}),
            style="cmd",
        )
        assert '--data-binary "{\\"a\\":1}"' in line

    def test_binary_body_becomes_file_reference(self):
        line = build_curl(
            _flow(method="POST", req_body=b"\x00\x01\x02", req_headers={"Content-Type": "application/octet-stream"})
        )
        assert line.endswith("--data-binary '@payload.bin'")

    def test_no_request_returns_empty(self):
        flow = _flow()
        flow.request = None
        assert build_curl(flow) == ""


class TestBuildRaw:
    def test_contains_start_lines_and_bodies(self):
        raw = build_raw(_flow(res_headers={"Content-Type": "http/1.1"}))
        assert "===== 请求 =====" in raw
        assert "===== 响应 =====" in raw
        assert "GET /v1/user?page=1&size=20 HTTP/1.1" in raw
        assert "HTTP/1.1 200 OK" in raw
        assert "Host: api.example.com" in raw
        assert '{"ok":true}' in raw

    def test_binary_body_not_inlined(self):
        raw = build_raw(_flow(res_body=b"\x00\x01\x02", res_headers={"Content-Type": "application/octet-stream"}))
        assert "二进制 body：3 字节" in raw

    def test_request_body_present(self):
        raw = build_raw(_flow(method="POST", req_body=b'{"a":1}', req_headers={"Content-Type": "application/json"}))
        assert '{"a":1}' in raw

    def test_without_response_only_request_block(self):
        raw = build_raw(_flow(with_response=False))
        assert "===== 请求 =====" in raw
        assert "===== 响应 =====" not in raw


class TestHar:
    def test_document_shell(self):
        doc = build_har(_flow())
        assert doc["log"]["version"] == "1.2"
        assert doc["log"]["creator"]["name"] == "MiteProxy"
        assert doc["log"]["pages"] == []
        assert len(doc["log"]["entries"]) == 1

    def test_request_fields(self):
        entry = build_har(_flow())["log"]["entries"][0]
        req = entry["request"]
        assert req["method"] == "GET"
        assert req["url"] == DEFAULT_URL
        assert req["queryString"] == [{"name": "page", "value": "1"}, {"name": "size", "value": "20"}]
        assert {"name": "Host", "value": "api.example.com"} in req["headers"]
        assert req["bodySize"] == 0
        assert "postData" not in req

    def test_http2_missing_host_is_filled(self):
        """HTTP/2 的 :authority 是伪头、不在 headers 里，HAR 不能因此缺 Host
        （HAR 1.2 要求 request.headers 含 Host，否则导入别的工具会丢主机）。"""
        flow = _flow()
        flow.request.headers.pop("Host", None)
        flow.request.http_version = "HTTP/2.0"
        headers = build_har(flow)["log"]["entries"][0]["request"]["headers"]
        assert {"name": "Host", "value": "api.example.com"} in headers
        # 已有 Host 的不重复补
        assert sum(1 for h in headers if h["name"].lower() == "host") == 1

    def test_har_ipv6_host_is_bracketed(self):
        flow = _flow(url="http://[::1]:8080/x")
        flow.request.headers.pop("Host", None)
        flow.request.http_version = "HTTP/2.0"
        headers = build_har(flow)["log"]["entries"][0]["request"]["headers"]
        assert {"name": "Host", "value": "[::1]:8080"} in headers

    def test_post_data(self):
        entry = build_har(
            _flow(method="POST", req_body=b'{"a":1}', req_headers={"Content-Type": "application/json"})
        )["log"]["entries"][0]
        assert entry["request"]["postData"]["mimeType"] == "application/json"
        assert entry["request"]["postData"]["text"] == '{"a":1}'
        assert entry["request"]["bodySize"] == 7

    def test_response_fields(self):
        entry = build_har(_flow(status=201, res_headers={"Content-Type": "application/json; charset=utf-8"}))[
            "log"
        ]["entries"][0]
        res = entry["response"]
        assert res["status"] == 201
        assert res["statusText"] == "Created"
        assert res["content"]["mimeType"] == "application/json; charset=utf-8"
        assert res["content"]["text"] == '{"ok":true}'
        assert res["content"]["size"] == 11
        assert "encoding" not in res["content"]
        assert res["bodySize"] == 11

    def test_binary_content_base64(self):
        entry = build_har(_flow(res_body=b"\x89PNG\r\n", res_headers={"Content-Type": "image/png"}))["log"][
            "entries"
        ][0]
        content = entry["response"]["content"]
        assert content["encoding"] == "base64"
        assert base64.b64decode(content["text"]) == b"\x89PNG\r\n"
        assert content["mimeType"] == "image/png"

    def test_timings_fallback_when_timestamps_missing(self):
        """时间戳缺失（合成/未完成的流）时退化为「全部算 wait」，不能报错。"""
        flow = _flow()
        for msg in (flow.request, flow.response):
            msg.timestamp_start = None
            msg.timestamp_end = None
        entry = build_har(flow)["log"]["entries"][0]
        assert entry["timings"] == {"send": 0, "wait": 0, "receive": 0}
        assert entry["time"] == 0

    def test_time_equals_sum_of_timings(self):
        """HAR 规范要求 time == timings 之和。"""
        entry = build_har(_flow())["log"]["entries"][0]
        assert entry["time"] == round(sum(entry["timings"].values()), 1)
        assert entry["timings"]["wait"] >= 0

    def test_timings_split_from_mitmproxy_timestamps(self):
        flow = _flow()
        req, res = flow.request, flow.response
        req.timestamp_start, req.timestamp_end = 100.0, 100.1
        res.timestamp_start, res.timestamp_end = 100.4, 100.5
        entry = build_har(flow)["log"]["entries"][0]
        assert entry["timings"] == {"send": 100.0, "wait": 300.0, "receive": 100.0}
        assert entry["time"] == 500.0
        assert entry["startedDateTime"].endswith("Z")

    def test_mock_comment_and_redirect(self):
        flow = _flow(status=302, marked="MOCK:rule-a", res_headers={"Location": "https://x/y"})
        entry = build_har(flow)["log"]["entries"][0]
        assert entry["comment"] == "MOCK:rule-a"
        assert entry["response"]["redirectURL"] == "https://x/y"

    def test_json_is_parseable_and_utf8(self):
        text = build_har_json(_flow(res_body='{"msg":"中文"}'.encode("utf-8")))
        doc = json.loads(text)
        assert doc["log"]["entries"][0]["response"]["content"]["text"] == '{"msg":"中文"}'
        assert "中文" in text                    # ensure_ascii=False


class TestBuildResponse:
    """完整响应（Fiddler「Save → Response → Entire Response」）：头 + body，不含请求。"""

    def test_start_line_and_blank_separator(self):
        data = build_response(_flow(status=201, res_headers={"Content-Type": "application/json"}))
        head, _, body = data.partition(b"\r\n\r\n")
        lines = head.decode("utf-8").split("\r\n")
        assert lines[0] == "HTTP/1.1 201 Created"
        assert "Content-Type: application/json" in lines
        assert body == b'{"ok":true}'

    def test_request_not_included(self):
        data = build_response(_flow())
        assert b"GET /v1/user" not in data
        assert b"Host: api.example.com" not in data

    def test_keeps_duplicate_headers(self):
        flow = _flow(res_body=b"ok", res_headers={})
        flow.response.headers.add("Set-Cookie", "a=1")
        flow.response.headers.add("Set-Cookie", "b=2")
        text = build_response(flow).decode("utf-8")
        assert "Set-Cookie: a=1" in text
        assert "Set-Cookie: b=2" in text

    def test_binary_body_is_byte_exact(self):
        """二进制 body 原样拼接，不重编码、不截断。"""
        raw = bytes(range(256))
        data = build_response(_flow(res_body=raw, res_headers={"Content-Type": "application/octet-stream"}))
        assert data.endswith(raw)
        assert data.count(b"\r\n\r\n") == 1

    def test_chinese_body_utf8(self):
        data = build_response(_flow(res_body='{"msg":"中文"}'.encode("utf-8")))
        assert '{"msg":"中文"}'.encode("utf-8") in data

    def test_empty_body_ends_with_separator(self):
        data = build_response(_flow(res_body=b""))
        assert data.endswith(b"\r\n\r\n")
        assert data.decode("utf-8").splitlines()[0] == "HTTP/1.1 200 OK"

    def test_missing_reason_tolerated(self):
        flow = _flow()
        flow.response.reason = ""
        assert build_response(flow).startswith(b"HTTP/1.1 200\r\n")

    def test_no_response_returns_empty(self):
        assert build_response(_flow(with_response=False)) == b""

    def test_export_bytes_uses_response_format(self):
        assert export_bytes(_flow(), FORMAT_RESPONSE) == build_response(_flow())

    def test_requires_response_marks(self):
        assert FORMAT_RESPONSE in REQUIRES_RESPONSE
        assert FORMAT_BODY in REQUIRES_RESPONSE
        assert FORMAT_HAR not in REQUIRES_RESPONSE
        assert FORMAT_RAW not in REQUIRES_RESPONSE


class TestFilenames:
    def test_body_filename_from_url_tail(self):
        flow = _flow(url="https://cdn.example.com/assets/app.js?ver=2")
        assert body_filename(flow) == "app.js"

    def test_body_filename_falls_back_to_content_type(self):
        flow = _flow(url="https://cdn.example.com/", res_headers={"Content-Type": "text/html"})
        assert body_filename(flow) == "body.html"

    def test_default_filename_for_har_and_raw(self):
        flow = _flow()
        assert default_filename(flow, FORMAT_HAR) == "api.example.com_v1_user.har"
        assert default_filename(flow, FORMAT_RAW) == "api.example.com_v1_user.txt"
        assert default_filename(flow, FORMAT_RESPONSE) == "api.example.com_v1_user.response.txt"

    def test_ensure_suffix_appends_missing_ext(self):
        assert ensure_suffix("/tmp/x", FORMAT_HAR, _flow()) == "/tmp/x.har"
        assert ensure_suffix("/tmp/x", FORMAT_RAW, _flow()) == "/tmp/x.txt"
        assert ensure_suffix("/tmp/x", FORMAT_RESPONSE, _flow()) == "/tmp/x.txt"

    def test_ensure_suffix_keeps_response_default_name(self):
        assert ensure_suffix("/tmp/x.response.txt", FORMAT_RESPONSE, _flow()) == "/tmp/x.response.txt"

    def test_ensure_suffix_keeps_user_choice(self):
        assert ensure_suffix("/tmp/x.har", FORMAT_HAR, _flow()) == "/tmp/x.har"

    def test_body_suffix_from_content_type(self):
        flow = _flow(url="https://cdn.example.com/data", res_headers={"Content-Type": "application/json"})
        assert ensure_suffix("/tmp/x", FORMAT_BODY, flow) == "/tmp/x.json"

    def test_name_filters_map_all_formats(self):
        filters, mapping = name_filters()
        assert filters.count(";;") == len(mapping) - 1
        assert set(mapping.values()) == {FORMAT_HAR, FORMAT_RAW, FORMAT_RESPONSE, FORMAT_BODY}
        assert len(set(mapping.keys())) == len(mapping)      # 标签唯一，否则反查会串


class TestExportBytes:
    def test_har_is_utf8_json(self):
        data = export_bytes(_flow(), FORMAT_HAR)
        assert json.loads(data.decode("utf-8"))["log"]["version"] == "1.2"

    def test_raw_is_utf8_text(self):
        assert b"===== \xe8\xaf\xb7\xe6\xb1\x82 =====" in export_bytes(_flow(), FORMAT_RAW)

    def test_body_is_raw_response_bytes(self):
        assert export_bytes(_flow(res_body=b"\x00\xffbin"), FORMAT_BODY) == b"\x00\xffbin"

    def test_body_empty_when_no_response(self):
        assert export_bytes(_flow(with_response=False), FORMAT_BODY) == b""

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError):
            export_bytes(_flow(), "csv")
