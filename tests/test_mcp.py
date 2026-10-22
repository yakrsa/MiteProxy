"""MCP 接口（app/mcpserver.py）的单元测试。

分两层测：
1. 过滤 / 序列化是纯函数，直接喂假 flow 断言（快、无网络）；
2. JSON-RPC 与 HTTP 端点：直接调 handle_rpc，以及真起一次本地服务走
   POST /mcp 与 GET /api/flows（只绑 127.0.0.1）。
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from app.mcpserver import (
    MAX_LIMIT,
    McpServer,
    filter_flows,
    flow_to_dict,
    handle_rpc,
)


def _flow(url="http://x.test/api/list", method="GET", status=200,
          req_headers=None, req_body=None, resp_headers=None, resp_body=None):
    from mitmproxy.test import tflow

    flow = tflow.tflow(resp=True)
    flow.request.url = url
    flow.request.method = method
    flow.response.status_code = status
    if req_headers:
        for k, v in req_headers.items():
            flow.request.headers[k] = v
    if req_body is not None:
        flow.request.content = req_body
    if resp_headers:
        for k, v in resp_headers.items():
            flow.response.headers[k] = v
    if resp_body is not None:
        flow.response.content = resp_body
    return flow


# ------------------------------------------------------------------ 过滤

def test_filter_by_url_keyword():
    flows = [
        _flow("http://x.test/api/list"),
        _flow("http://y.test/other"),
    ]
    assert [f.request.url for f in filter_flows(flows, url="api")] == [
        "http://x.test/api/list"
    ]


def test_filter_by_param_in_query():
    flows = [
        _flow("http://x.test/api?q=hello"),
        _flow("http://x.test/api?q=bye"),
    ]
    assert len(filter_flows(flows, param="hello")) == 1


def test_filter_by_param_in_body():
    flows = [
        _flow(req_body=b"username=alice&page=2"),
        _flow(req_body=b"username=bob"),
    ]
    picked = filter_flows(flows, param="alice")
    assert len(picked) == 1
    assert picked[0].request.content == b"username=alice&page=2"


def test_filter_by_header_keyword():
    flows = [
        _flow(req_headers={"X-Token": "secret-abc"}),
        _flow(req_headers={"X-Token": "zzz"}),
    ]
    assert len(filter_flows(flows, header="secret-abc")) == 1
    # 头名也参与匹配
    assert len(filter_flows(flows, header="x-token")) == 2


def test_filter_by_method_and_status():
    flows = [
        _flow(method="POST", status=200),
        _flow(method="GET", status=404),
    ]
    assert len(filter_flows(flows, method="post")) == 1     # 大小写不敏感
    assert len(filter_flows(flows, status=404)) == 1
    assert len(filter_flows(flows, method="GET", status=404)) == 1


def test_limit_takes_the_most_recent():
    flows = [_flow(f"http://x.test/{i}") for i in range(10)]
    picked = filter_flows(flows, limit=3)
    # flows 按到达顺序，取最近的 → 末尾三条
    assert [f.request.url for f in picked] == [
        "http://x.test/7", "http://x.test/8", "http://x.test/9"
    ]


def test_limit_is_capped():
    flows = [_flow(f"http://x.test/{i}") for i in range(5)]
    assert len(filter_flows(flows, limit=10_000)) == min(5, MAX_LIMIT)


def test_no_filter_returns_all():
    flows = [_flow(), _flow()]
    assert len(filter_flows(flows)) == 2


# ------------------------------------------------------------------ 序列化

def test_flow_to_dict_shape():
    flow = _flow(
        url="http://x.test/api?q=1",
        req_headers={"X-Token": "t"},
        resp_headers={"Content-Type": "application/json"},
        resp_body=b'{"ok":1}',
    )
    d = flow_to_dict(flow)
    assert d["method"] == "GET"
    assert d["url"] == "http://x.test/api?q=1"
    assert d["status"] == 200
    assert d["request_headers"]["X-Token"] == "t"
    assert d["response_headers"]["Content-Type"] == "application/json"
    assert d["response_body"] == '{"ok":1}'


def test_body_is_preview_by_default():
    long_body = b"x" * 5000
    d = flow_to_dict(_flow(resp_body=long_body))
    assert d["body_truncated"] is True
    assert len(d["response_body"]) < len(long_body)

    full = flow_to_dict(_flow(resp_body=long_body), include_body=True)
    assert full["body_truncated"] is False
    assert len(full["response_body"]) == 5000


# ------------------------------------------------------------------ JSON-RPC

def test_rpc_initialize():
    resp = handle_rpc(lambda: [], {"jsonrpc": "2.0", "id": 1,
                                   "method": "initialize", "params": {}})
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "MiteProxy"


def test_rpc_tools_list_has_get_recent_flows():
    resp = handle_rpc(lambda: [], {"id": 2, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert "get_recent_flows" in names


def test_rpc_tools_call_returns_flows():
    flows = [_flow("http://x.test/api/a"), _flow("http://y.test/b")]
    resp = handle_rpc(lambda: flows, {
        "id": 3,
        "method": "tools/call",
        "params": {"name": "get_recent_flows", "arguments": {"url": "api"}},
    })
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["total"] == 1
    assert payload["flows"][0]["url"] == "http://x.test/api/a"


def test_rpc_unknown_tool_errors():
    resp = handle_rpc(lambda: [], {
        "id": 4, "method": "tools/call",
        "params": {"name": "nope", "arguments": {}},
    })
    assert "error" in resp


def test_rpc_notification_has_no_response():
    assert handle_rpc(lambda: [], {"method": "notifications/initialized"}) is None


# ------------------------------------------------------------------ HTTP 端到端

@pytest.fixture()
def mcp_server():
    flows = [
        _flow("http://x.test/api/a", req_headers={"X-Token": "abc"}),
        _flow("http://x.test/other/b"),
    ]
    server = McpServer(flow_provider=lambda: flows, port=18899)
    if not server.start():
        pytest.skip("MCP 测试端口不可用")
    yield server, flows
    server.stop()


def test_http_post_mcp(mcp_server):
    server, _ = mcp_server
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_recent_flows", "arguments": {"url": "api"}},
    }).encode()
    req = urllib.request.Request(
        server.url, data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        payload = json.loads(resp.read().decode())
    inner = json.loads(payload["result"]["content"][0]["text"])
    assert inner["total"] == 1


def test_http_rest_flows(mcp_server):
    server, _ = mcp_server
    with urllib.request.urlopen(
        f"http://127.0.0.1:{server._bound_port}/api/flows?header=abc", timeout=5
    ) as resp:
        payload = json.loads(resp.read().decode())
    assert payload["total"] == 1
    assert payload["flows"][0]["request_headers"]["X-Token"] == "abc"


# ------------------------------------------------------------ 监听地址（局域网）

def test_default_host_is_localhost_only():
    server = McpServer(flow_provider=lambda: [])
    assert server.host == "127.0.0.1"
    assert server.exposed is False


def test_exposed_flag():
    """只有 127.0.0.1 / ::1 / localhost 算「仅本机」，其余都对外。"""
    assert McpServer(lambda: [], host="127.0.0.1").exposed is False
    assert McpServer(lambda: [], host="::1").exposed is False
    assert McpServer(lambda: [], host="localhost").exposed is False
    assert McpServer(lambda: [], host="0.0.0.0").exposed is True
    assert McpServer(lambda: [], host="192.168.1.5").exposed is True
    # 空串按默认处理（回落仅本机），不当成"对外"
    assert McpServer(lambda: [], host="").exposed is False


def test_urls_lists_every_address_when_wildcard():
    """绑 0.0.0.0 时要告诉用户每个可连的地址，别只丢一个 127.0.0.1。"""
    server = McpServer(lambda: [], port=8899, host="0.0.0.0")
    urls = server.urls()
    assert urls[0] == "http://127.0.0.1:8899/mcp"
    for u in urls:
        assert u.endswith("/mcp")
    # 非通配地址只返回自己，且 IPv6 要带方括号
    assert McpServer(lambda: [], host="::1").urls() == ["http://[::1]:8899/mcp"]
    assert McpServer(lambda: [], host="192.168.1.5").urls() == [
        "http://192.168.1.5:8899/mcp"
    ]


def test_bind_wildcard_is_reachable_on_localhost():
    """0.0.0.0 = 全部网卡，本机当然也要能连上（回归用：别绑错族）。"""
    flows = [_flow("http://x.test/api/a")]
    server = McpServer(flow_provider=lambda: flows, port=18898, host="0.0.0.0")
    if not server.start():
        pytest.skip("0.0.0.0 绑定在本机不可用（无权限或被策略拦截）")
    try:
        body = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_recent_flows", "arguments": {}},
        }).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server._bound_port}/mcp", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode())
        inner = json.loads(payload["result"]["content"][0]["text"])
        assert inner["total"] == 1
    finally:
        server.stop()


def test_unbindable_host_fails_fast():
    """填了本机没有的 IP：换端口也没用，应当立即失败而不是空转 20 次。"""
    server = McpServer(lambda: [], port=18897, host="10.255.255.1")
    assert server.start() is False
    assert not server.running


def test_settings_roundtrip_keeps_host():
    """监听地址要进 settings.json，下次启动保持。"""
    from app.settings import Settings

    s = Settings(mcp_host="0.0.0.0", mcp_port=9001, mcp_enabled=True)
    data = s.to_dict()
    assert data["mcp_host"] == "0.0.0.0"
    back = Settings.from_dict(data)
    assert back.mcp_host == "0.0.0.0"
    assert back.mcp_port == 9001
    # 手改坏了要回落默认，别让服务启动时才炸
    assert Settings.from_dict({"mcp_host": "  "}).mcp_host == "127.0.0.1"
    assert Settings.from_dict({}).mcp_host == "127.0.0.1"


# ------------------------------------------------------- get_flow_detail（详情工具）


def _rpc(name, arguments, flows, **kw):
    return handle_rpc(lambda: flows, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }, **kw)


def _detail_payload(result) -> dict:
    return json.loads(result["result"]["content"][0]["text"])


def test_tools_list_exposes_all_three_tools():
    tools = handle_rpc(lambda: [], {"jsonrpc": "2.0", "id": 1,
                                    "method": "tools/list"})["result"]["tools"]
    assert [t["name"] for t in tools] == [
        "get_recent_flows", "get_flow_detail", "get_stats"
    ]
    schema = tools[1]["inputSchema"]
    assert schema["required"] == ["id"]
    assert "include_body" in schema["properties"]


def test_flow_detail_returns_full_body_beyond_preview():
    """详情的意义就是全量：不能被 _safe_text 的 64KB 匹配上限悄悄截断。"""
    big = b"x" * 100_000
    f = _flow("http://x.test/api/a", resp_body=big)
    d = _detail_payload(_rpc("get_flow_detail", {"id": f.id}, [f]))
    assert len(d["response_body"]) == 100_000
    assert d["body_truncated"] is False
    assert d["response_body_encoding"] == "utf-8"


def test_flow_detail_binary_falls_back_to_base64():
    import base64

    raw = b"\x00\x01\xff\xfe binary"
    f = _flow("http://x.test/api/a", resp_body=raw)
    d = _detail_payload(_rpc("get_flow_detail", {"id": f.id}, [f]))
    assert d["response_body_encoding"] == "base64"
    assert base64.b64decode(d["response_body"]) == raw


def test_flow_detail_preview_when_body_not_requested():
    f = _flow("http://x.test/api/a", resp_body=b"y" * 5000)
    d = _detail_payload(
        _rpc("get_flow_detail", {"id": f.id, "include_body": False}, [f])
    )
    assert len(d["response_body"]) == 2000
    assert d["body_truncated"] is True


def test_flow_detail_carries_timings_and_server_ip():
    """耗时 / 服务器 IP 必须走 capture 的口径，跟列表列同源。"""
    f = _flow("http://x.test/api/a")
    d = _detail_payload(_rpc("get_flow_detail", {"id": f.id}, [f]))
    assert "timings" in d and "duration_ms" in d
    assert isinstance(d["duration_ms"], float)
    assert d["request_headers"] and isinstance(d["request_headers"], dict)


def test_flow_detail_missing_id_is_tool_error_not_rpc_error():
    """没找到属于**工具执行**失败，走 content + isError，不是 JSON-RPC error。"""
    f = _flow("http://x.test/api/a")
    result = _rpc("get_flow_detail", {"id": "no-such-id"}, [f])
    assert "error" not in result or result["result"].get("isError") is True
    payload = _detail_payload(result)
    assert "no-such-id" in payload["error"]


def test_flow_detail_accepts_unique_id_prefix():
    f = _flow("http://x.test/api/a")
    d = _detail_payload(_rpc("get_flow_detail", {"id": f.id[:8]}, [f]))
    assert d["id"] == f.id


def test_resolve_flow_prefers_injected_getter():
    f = _flow("http://x.test/api/a")
    from app.mcpserver import resolve_flow

    # 注入的 getter 优先（capture.get_flow），列表里根本没有这条也能拿到
    got, err = resolve_flow([], f.id, flow_by_id=lambda _id: f)
    assert got is f and err is None
    # 前缀歧义要报错而不是随便挑一条
    class _Fake:
        def __init__(self, fid):
            self.id = fid

    got, err = resolve_flow([_Fake("abc-1"), _Fake("abc-2")], "abc")
    assert got is None and "abc" in err


def test_rest_detail_endpoint(mcp_server):
    server, flows = mcp_server
    fid = flows[0].id
    with urllib.request.urlopen(
        f"http://127.0.0.1:{server._bound_port}/api/flows/{fid}", timeout=5
    ) as resp:
        payload = json.loads(resp.read().decode())
    assert payload["id"] == fid
    assert payload["request_headers"]["X-Token"] == "abc"


def test_rest_detail_missing_is_404(mcp_server):
    import urllib.error

    server, _ = mcp_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(
            f"http://127.0.0.1:{server._bound_port}/api/flows/nope", timeout=5
        )
    assert exc.value.code == 404


# ------------------------------------------------------- get_stats（统计工具）


def test_get_stats_aggregates_all_flows():
    """统计吃全量快照——不该被 get_recent_flows 的 200 条上限截断。"""
    flows = [
        _flow(f"http://a.test/{i}", status=500 if i % 4 == 0 else 200)
        for i in range(30)
    ]
    payload = _detail_payload(_rpc("get_stats", {}, flows))
    assert payload["total"] == 30
    assert payload["errors"] == 8                 # 0,4,8,...,28
    assert payload["error_rate"] == pytest.approx(8 / 30, abs=1e-4)
    assert payload["hosts"][0]["host"] == "a.test"
    assert payload["hosts"][0]["count"] == 30
    assert payload["slow_requests"]
    assert payload["timeline"]["buckets"]
    # 与统计页同一份聚合：键集合一致（app/stats.py::compute_stats）
    from app.stats import compute_stats
    assert set(payload) == set(compute_stats(flows))


def test_get_stats_url_filter():
    flows = [
        _flow("http://a.test/api/1", status=500),
        _flow("http://b.test/other/2"),
    ]
    payload = _detail_payload(_rpc("get_stats", {"url": "api"}, flows))
    assert payload["total"] == 1
    assert payload["errors"] == 1
    assert [h["host"] for h in payload["hosts"]] == ["a.test"]


def test_get_stats_top_n_clamped():
    flows = [_flow(f"http://h{i}.test/1") for i in range(60)]
    payload = _detail_payload(_rpc("get_stats", {"top_n": 9999}, flows))
    from app.stats import MAX_TOP_N
    assert len(payload["hosts"]) == MAX_TOP_N


def test_get_stats_empty_flows():
    payload = _detail_payload(_rpc("get_stats", {}, []))
    assert payload["total"] == 0
    assert payload["error_rate"] == 0.0
    assert payload["timeline"]["buckets"] == []


def test_rest_stats_endpoint(mcp_server):
    server, _ = mcp_server
    with urllib.request.urlopen(
        f"http://127.0.0.1:{server._bound_port}/api/stats?url=api", timeout=5
    ) as resp:
        payload = json.loads(resp.read().decode())
    assert payload["total"] == 1
    assert payload["hosts"][0]["host"] == "x.test"


def test_rest_stats_bad_top_n_is_400(mcp_server):
    import urllib.error

    server, _ = mcp_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(
            f"http://127.0.0.1:{server._bound_port}/api/stats?top_n=abc", timeout=5
        )
    assert exc.value.code == 400


# ------------------------------------------------------- 写操作（默认关）


def _rpc_tools_list(**kwargs):
    return handle_rpc(lambda: [], {"jsonrpc": "2.0", "id": 1,
                                   "method": "tools/list"}, **kwargs)["result"]["tools"]


def test_tools_list_excludes_write_tools_by_default():
    names = [t["name"] for t in _rpc_tools_list()]
    assert names == ["get_recent_flows", "get_flow_detail", "get_stats"]


def test_tools_list_includes_write_tools_when_enabled():
    tools = _rpc_tools_list(write_enabled=True, write_ops={})
    names = [t["name"] for t in tools]
    assert names == ["get_recent_flows", "get_flow_detail", "get_stats",
                     "add_mock_rule", "replay_flow", "set_breakpoint"]
    by_name = {t["name"]: t for t in tools}
    assert by_name["add_mock_rule"]["inputSchema"]["required"] == ["url"]
    assert by_name["replay_flow"]["inputSchema"]["required"] == ["id"]
    assert by_name["set_breakpoint"]["inputSchema"]["required"] == ["enabled"]


def test_write_tool_rejected_when_disabled():
    """没开写权限时，写工具等同不存在（与未知工具同样 -32602）。"""
    resp = handle_rpc(lambda: [], {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "add_mock_rule",
                   "arguments": {"url": "http://x.test"}},
    })
    assert "error" in resp
    assert resp["error"]["code"] == -32602


def test_write_op_success_dispatches():
    calls = {}

    def add_rule(args):
        calls["args"] = args
        return {"ok": True, "rule": {"id": "r1"}}

    resp = handle_rpc(lambda: [], {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "add_mock_rule",
                   "arguments": {"url": "http://x.test/a"}},
    }, write_enabled=True, write_ops={"add_mock_rule": add_rule})
    assert "error" not in resp
    inner = json.loads(resp["result"]["content"][0]["text"])
    assert inner["ok"] is True
    assert calls["args"]["url"] == "http://x.test/a"
    assert "isError" not in resp["result"]


def test_write_op_error_result_is_tool_error():
    """回调返回带 error 的结果 = 工具执行失败（isError），不是协议错误。"""
    resp = handle_rpc(lambda: [], {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "replay_flow", "arguments": {"id": "abc"}},
    }, write_enabled=True,
        write_ops={"replay_flow": lambda args: {"error": "代理未运行"}})
    assert "error" not in resp
    assert resp["result"]["isError"] is True
    inner = json.loads(resp["result"]["content"][0]["text"])
    assert inner["error"] == "代理未运行"


def test_write_op_exception_is_rpc_error():
    def boom(args):
        raise RuntimeError("kaboom")

    resp = handle_rpc(lambda: [], {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "set_breakpoint", "arguments": {"enabled": True}},
    }, write_enabled=True, write_ops={"set_breakpoint": boom})
    assert resp["error"]["code"] == -32603


def test_write_op_missing_callback_is_rpc_error():
    """开着写权限但没注入回调（配置不一致）→ 内部错误，不静默吞掉。"""
    resp = handle_rpc(lambda: [], {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "add_mock_rule", "arguments": {"url": "u"}},
    }, write_enabled=True, write_ops=None)
    assert resp["error"]["code"] == -32603


def test_http_tools_list_reflects_write_flag():
    """HTTP 层 tools/list 跟着运行时可变的 write_enabled 走（即时开关）。"""
    flows = [_flow()]
    server = McpServer(flow_provider=lambda: flows, port=18898,
                       write_enabled=False)
    if not server.start():
        pytest.skip("MCP 测试端口不可用")
    try:
        def _post(method, params=None):
            body = json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": method,
                "params": params or {},
            }).encode()
            req = urllib.request.Request(
                server.url, data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())

        names = [t["name"] for t in _post("tools/list")["result"]["tools"]]
        assert "add_mock_rule" not in names
        # 运行中打开开关（设置里改的那种）：不重启服务，客户端重新 list 即可见
        server.write_enabled = True
        names = [t["name"] for t in _post("tools/list")["result"]["tools"]]
        assert "add_mock_rule" in names
        # 调用仍会失败（没注入回调）→ -32603，证明门控真的放行了请求
        resp = _post("tools/call", {"name": "add_mock_rule",
                                    "arguments": {"url": "u"}})
        assert resp["error"]["code"] == -32603
    finally:
        server.stop()


def test_settings_roundtrip_keeps_write_flag():
    from app.settings import Settings

    s = Settings()
    s.mcp_write_enabled = True
    assert Settings.from_dict(s.to_dict()).mcp_write_enabled is True
    assert Settings.from_dict({}).mcp_write_enabled is False
