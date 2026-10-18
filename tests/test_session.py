"""会话保存与恢复（app/session.py）。

用真实 mitmproxy Request/Response/HTTPFlow 造数据，断言：
- 落盘 → 读回后 method/url/headers/body/状态码逐字一致（含中文与二进制）；
- body 预算：超单条上限→截断、超整包预算→只留元数据；
- 坏行/半截行/版本不符只跳过计数，不影响其余会话；
- 恢复出来的 flow 仍能被 CaptureAddon.summarize 与导出模块消费（是"活会话"）。
"""

import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mitmproxy.http import HTTPFlow, Request, Response  # noqa: E402

from addons.capture import CaptureAddon  # noqa: E402
from app import session as session_mod  # noqa: E402
from app.export import build_raw, build_response, export_bytes  # noqa: E402
from app.session import (  # noqa: E402
    SESSION_VERSION,
    SessionLimits,
    archive_autosave,
    clear_autosave,
    load_session,
    read_autosave_meta,
    save_autosave,
    save_session,
)

URL = "https://api.example.com/v1/order?id=7"


def _flow(
    method="POST",
    url=URL,
    req_headers=None,
    req_body=b'{"amount":199}',
    status=201,
    reason="Created",
    res_headers=None,
    res_body=b'{"msg":"\xe4\xb8\xad\xe6\x96\x87"}',
    server_ip=None,
    marked="",
):
    headers = {"Host": "api.example.com"}
    headers.update(req_headers or {})
    req = Request.make(method, url, content=req_body, headers=headers)
    req.timestamp_start, req.timestamp_end = 100.0, 100.1
    res = Response.make(
        status,
        content=res_body,
        headers=res_headers if res_headers is not None else {"Content-Type": "application/json; charset=utf-8"},
    )
    res.reason = reason
    res.timestamp_start, res.timestamp_end = 100.4, 100.5
    flow = HTTPFlow(client_conn=None, server_conn=None)
    flow.request = req
    flow.response = res
    flow.marked = marked
    if server_ip:
        flow.server_conn = types.SimpleNamespace(
            peername=(server_ip, 443), address=(server_ip, 443)
        )
    return flow


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    """把自动快照相关路径指到临时目录（模块级常量，需 monkeypatch）。"""
    p = {
        "autosave": tmp_path / "last-session.jsonl",
        "meta": tmp_path / "last-session.meta.json",
        "archive": tmp_path / "last-session.previous.jsonl",
    }
    monkeypatch.setattr(session_mod, "AUTOSAVE_PATH", p["autosave"])
    monkeypatch.setattr(session_mod, "AUTOSAVE_META_PATH", p["meta"])
    monkeypatch.setattr(session_mod, "ARCHIVE_PATH", p["archive"])
    return p


class TestRoundTrip:
    def test_request_and_response_survive(self, tmp_path):
        target = tmp_path / "s.jsonl"
        result = save_session(target, [_flow()])
        assert result.ok and result.count == 1
        assert target.exists()

        loaded = load_session(target)
        assert loaded.ok and loaded.count == 1 and loaded.skipped == 0
        req = loaded.flows[0].request
        res = loaded.flows[0].response
        assert req.method == "POST"
        assert req.pretty_url == URL
        assert req.get_content(strict=False) == b'{"amount":199}'
        assert req.headers["Host"] == "api.example.com"
        assert res.status_code == 201
        assert res.reason == "Created"
        assert res.get_content(strict=False) == b'{"msg":"\xe4\xb8\xad\xe6\x96\x87"}'
        assert res.headers["content-type"] == "application/json; charset=utf-8"

    def test_timestamps_restored_for_export(self, tmp_path):
        target = tmp_path / "s.jsonl"
        save_session(target, [_flow()])
        flow = load_session(target).flows[0]
        assert flow.request.timestamp_start == 100.0
        assert flow.response.timestamp_end == 100.5
        # 时间戳在 → HAR 的 timings 能拆出三段
        entry = json.loads(export_bytes(flow, "har").decode())["log"]["entries"][0]
        assert entry["timings"] == {"send": 100.0, "wait": 300.0, "receive": 100.0}

    def test_binary_body_byte_exact(self, tmp_path):
        raw = bytes(range(256))
        target = tmp_path / "s.jsonl"
        save_session(target, [_flow(res_body=raw, res_headers={"Content-Type": "application/octet-stream"})])
        flow = load_session(target).flows[0]
        assert flow.response.get_content(strict=False) == raw

    def test_duplicate_headers_preserved(self, tmp_path):
        flow = _flow(res_body=b"ok", res_headers={"Content-Type": "text/plain"})
        flow.response.headers.add("Set-Cookie", "a=1")
        flow.response.headers.add("Set-Cookie", "b=2")
        target = tmp_path / "s.jsonl"
        save_session(target, [flow])
        restored = load_session(target).flows[0]
        assert restored.response.headers.get_all("Set-Cookie") == ["a=1", "b=2"]

    def test_http_version_and_marked_kept(self, tmp_path):
        flow = _flow(marked="MOCK:rule-a")
        flow.request.http_version = "HTTP/2.0"
        target = tmp_path / "s.jsonl"
        save_session(target, [flow])
        restored = load_session(target).flows[0]
        assert restored.request.http_version == "HTTP/2.0"
        assert restored.marked == "MOCK:rule-a"

    def test_summary_kept_and_id_rewritten(self, tmp_path):
        flow = _flow(server_ip="93.184.216.34")
        target = tmp_path / "s.jsonl"
        save_session(target, [flow])
        loaded = load_session(target)
        summary = loaded.summaries[0]
        assert summary["server_ip"] == "93.184.216.34"      # 派生字段不丢
        assert summary["method"] == "POST"
        assert summary["status"] == 201
        assert summary["id"] == loaded.flows[0].id           # id 换成重建后的
        assert summary["id"] != flow.id

    def test_restored_flow_is_live_session(self, tmp_path):
        """恢复出来的会话要能直接进详情/导出/摘要，不是死记录。"""
        target = tmp_path / "s.jsonl"
        save_session(target, [_flow(marked="MOCK:x")])
        flow = load_session(target).flows[0]
        summary = CaptureAddon.summarize(flow)
        assert summary["status"] == 201
        assert summary["url"] == URL
        assert summary["marked"] == "MOCK:x"
        assert "===== 请求 =====" in build_raw(flow)
        assert build_response(flow).startswith(b"HTTP/1.1 201 Created")

    def test_restored_flow_can_be_copied_for_replay(self, tmp_path):
        """回归：`Flow.copy()` 会访问 client_conn/server_conn.get_state()，
        连接为 None 时恢复出来的会话重放不了（曾踩过）。"""
        from app.replay import make_replay_copy

        target = tmp_path / "s.jsonl"
        save_session(target, [_flow()])
        flow = load_session(target).flows[0]
        assert flow.client_conn is not None
        assert flow.server_conn is not None
        copy = make_replay_copy(flow)
        assert copy.id != flow.id
        assert copy.request.pretty_url == URL
        assert copy.request.method == "POST"
        assert copy.response is None          # 重放副本不带走旧响应
        assert flow.response is not None      # 原会话不受影响

    def test_http2_flow_restores_authority_for_replay(self, tmp_path):
        """回归：HTTP/2 的 :authority 既不在 headers 里、也不落盘，恢复时必须
        复原。否则重放出去是「无 Host、无 :authority」的裸请求，上游网关直接
        判 400（实测 hq.yxzq.com 返回 alibaba-ga 的 400 Bad Request）。"""
        from app.replay import make_replay_copy

        flow = _flow()
        flow.request.headers.pop("Host", None)   # HTTP/2 没有 Host 头
        flow.request.http_version = "HTTP/2.0"
        target = tmp_path / "s.jsonl"
        save_session(target, [flow])
        restored = load_session(target).flows[0]

        assert restored.request.http_version == "HTTP/2.0"
        assert restored.request.authority == "api.example.com"
        assert restored.request.first_line_format == "absolute"
        assert make_replay_copy(restored).request.authority == "api.example.com"

    def test_ipv6_flow_roundtrip_keeps_valid_url(self, tmp_path):
        """回归：`pretty_url` 对 IPv6 不加方括号，存档后是 `http://::1:8080/x`，
        恢复时 `Request.make` 直接抛 ValueError（No hostname given）——
        整份会话都打不开。存档 URL 必须带方括号。
        """
        flow = _flow(url="http://[::1]:8080/api/x")
        flow.request.headers.pop("Host", None)   # HTTP/2 没有 Host 头
        flow.request.http_version = "HTTP/2.0"
        target = tmp_path / "s.jsonl"
        save_session(target, [flow])

        assert '"http://[::1]:8080/api/x"' in target.read_text(encoding="utf-8")
        result = load_session(target)            # 不允许抛异常
        assert len(result.flows) == 1
        assert result.skipped == 0
        assert result.flows[0].request.host == "::1"
        assert result.flows[0].request.authority == "[::1]:8080"

    def test_restored_server_conn_carries_ip(self, tmp_path):
        """合成连接的 peername 用保存的服务端 IP，服务器 IP 列语义与抓包一致。"""
        target = tmp_path / "s.jsonl"
        save_session(target, [_flow(server_ip="203.0.113.9")])
        flow = load_session(target).flows[0]
        assert flow.server_conn.peername == ("203.0.113.9", 443)
        assert flow.server_conn.tls is True   # https 会话

    def test_multiple_flows_order_preserved(self, tmp_path):
        flows = [_flow(url=f"https://a.test/{i}", res_body=str(i).encode()) for i in range(5)]
        target = tmp_path / "s.jsonl"
        result = save_session(target, flows)
        assert result.count == 5
        loaded = load_session(target)
        assert [f.request.pretty_url for f in loaded.flows] == [f"https://a.test/{i}" for i in range(5)]

    def test_no_temp_file_left(self, tmp_path):
        target = tmp_path / "s.jsonl"
        save_session(target, [_flow()])
        assert list(tmp_path.glob("*.tmp")) == []


class TestLimits:
    def test_body_truncated_over_single_limit(self, tmp_path):
        big = b"x" * 5000
        limits = SessionLimits(body_limit=1000, total_limit=10_000)
        target = tmp_path / "s.jsonl"
        result = save_session(target, [_flow(res_body=big, res_headers={"Content-Type": "text/plain"})], limits)
        assert result.bodies_truncated == 1
        flow = load_session(target).flows[0]
        assert flow.response.get_content(strict=False) == b"x" * 1000
        # 原始大小仍记录在案，便于知道被截了
        record = json.loads(target.read_text(encoding="utf-8").splitlines()[0])
        assert record["response"]["body"]["size"] == 5000
        assert record["response"]["body"]["truncated"] is True

    def test_body_dropped_when_budget_exhausted(self, tmp_path):
        """预算耗尽后只丢响应体；请求体照样保留（否则恢复出来没法重放）。"""
        limits = SessionLimits(body_limit=1000, total_limit=100)
        flows = [_flow(url=f"https://a.test/{i}", res_body=b"y" * 500,
                       res_headers={"Content-Type": "text/plain"}) for i in range(3)]
        target = tmp_path / "s.jsonl"
        result = save_session(target, flows, limits)
        assert result.count == 3                     # 元数据全在
        assert result.bodies_dropped == 2            # 只有第 1 条吃到了 100 字节预算
        loaded = load_session(target)
        assert loaded.count == 3                     # 列表条目不少
        assert loaded.flows[0].response.get_content(strict=False) == b"y" * 100
        assert loaded.flows[1].response.get_content(strict=False) == b""
        assert loaded.flows[2].response.get_content(strict=False) == b""
        for flow in loaded.flows:                    # 请求体不丢
            assert flow.request.get_content(strict=False) == b'{"amount":199}'

    def test_request_body_survives_exhausted_budget(self, tmp_path):
        """预算给 0 的极端情况：响应体全丢，请求体仍在。"""
        limits = SessionLimits(body_limit=1000, total_limit=0)
        target = tmp_path / "s.jsonl"
        save_session(target, [_flow(res_body=b"z" * 100)], limits)
        flow = load_session(target).flows[0]
        assert flow.response.get_content(strict=False) == b""
        assert flow.request.get_content(strict=False) == b'{"amount":199}'

    def test_default_limits_are_generous(self, tmp_path):
        target = tmp_path / "s.jsonl"
        result = save_session(target, [_flow(res_body=b"z" * 200_000)])
        assert result.bodies_dropped == 0
        assert result.bodies_truncated == 0
        assert load_session(target).flows[0].response.get_content(strict=False) == b"z" * 200_000


class TestErrorHandling:
    def test_empty_flow_list_reports_error(self, tmp_path):
        result = save_session(tmp_path / "s.jsonl", [])
        assert not result.ok
        assert not (tmp_path / "s.jsonl").exists()

    def test_missing_file(self, tmp_path):
        result = load_session(tmp_path / "nope.jsonl")
        assert not result.ok
        assert "不存在" in result.error

    def test_bad_lines_skipped_and_counted(self, tmp_path):
        target = tmp_path / "s.jsonl"
        save_session(target, [_flow()])
        good = target.read_text(encoding="utf-8")
        target.write_text(
            "{ 这不是 json\n"
            + good
            + json.dumps({"v": 999, "summary": {}}) + "\n"
            + '["不是对象"]\n',
            encoding="utf-8",
        )
        loaded = load_session(target)
        assert loaded.count == 1
        assert loaded.skipped == 3

    def test_truncated_last_line_tolerated(self, tmp_path):
        target = tmp_path / "s.jsonl"
        save_session(target, [_flow(url="https://a.test/1"), _flow(url="https://a.test/2")])
        data = target.read_text(encoding="utf-8")
        target.write_text(data[: int(len(data) * 0.75)], encoding="utf-8")   # 砍掉末尾
        loaded = load_session(target)
        assert loaded.ok
        assert loaded.count >= 1
        assert [f.request.pretty_url for f in loaded.flows][0] == "https://a.test/1"

    def test_missing_request_treated_as_bad_line(self, tmp_path):
        target = tmp_path / "s.jsonl"
        target.write_text(
            json.dumps({"v": SESSION_VERSION, "summary": {}, "request": None, "response": None}) + "\n",
            encoding="utf-8",
        )
        loaded = load_session(target)
        assert loaded.count == 0
        assert loaded.skipped == 1


class TestAutosave:
    def test_save_autosave_writes_meta(self, paths):
        result = save_autosave([_flow(), _flow(url="https://a.test/2")])
        assert result.ok and result.count == 2
        assert paths["autosave"].exists()
        meta = read_autosave_meta()
        assert meta["count"] == 2
        assert meta["saved_at"]
        assert meta["bytes"] > 0

    def test_meta_absent_when_no_snapshot(self, paths):
        assert read_autosave_meta() is None

    def test_meta_invalid_json_returns_none(self, paths):
        paths["meta"].write_text("{坏", encoding="utf-8")
        assert read_autosave_meta() is None

    def test_meta_without_snapshot_file_returns_none(self, paths):
        paths["meta"].write_text(json.dumps({"count": 3, "saved_at": "x"}), encoding="utf-8")
        assert read_autosave_meta() is None

    def test_archive_moves_snapshot(self, paths):
        save_autosave([_flow()])
        archive_autosave()
        assert paths["archive"].exists()
        assert not paths["autosave"].exists()
        assert read_autosave_meta() is None

    def test_clear_removes_snapshot(self, paths):
        save_autosave([_flow()])
        clear_autosave()
        assert not paths["autosave"].exists()
        assert read_autosave_meta() is None

    def test_autosave_limits_are_smaller(self):
        assert session_mod.AUTOSAVE_LIMITS.body_limit < session_mod.DEFAULT_LIMITS.body_limit
        assert session_mod.AUTOSAVE_LIMITS.total_limit < session_mod.DEFAULT_LIMITS.total_limit

    def test_autosave_snapshot_round_trips(self, paths):
        save_autosave([_flow(marked="MOCK:a")])
        loaded = load_session(paths["autosave"])
        assert loaded.count == 1
        assert loaded.summaries[0]["marked"] == "MOCK:a"


# ================================================================ WS 消息入库（v1.11）


def _ws_flow(messages, close_code=None, close_reason="", timestamp_end=None):
    from mitmproxy.websocket import WebSocketData

    flow = _flow(status=101, reason="Switching Protocols", res_body=b"")
    flow.websocket = WebSocketData(
        messages=messages,
        close_code=close_code,
        close_reason=close_reason,
        timestamp_end=timestamp_end,
    )
    return flow


def _msg(content, from_client=False, opcode=1, timestamp=None):
    from mitmproxy.websocket import WebSocketMessage

    return WebSocketMessage(
        type=opcode, from_client=from_client, content=content, timestamp=timestamp
    )


class TestWebSocketPersistence:
    def test_messages_survive_round_trip(self, tmp_path):
        target = tmp_path / "ws.jsonl"
        flow = _ws_flow(
            [
                _msg(b"hello", from_client=True, timestamp=100.2),
                _msg("世界".encode("utf-8"), timestamp=100.3),
            ],
            close_code=1000,
            close_reason="bye",
            timestamp_end=101.0,
        )
        result = save_session(target, [flow])
        assert result.ok and result.count == 1

        loaded = load_session(target)
        assert loaded.count == 1 and loaded.skipped == 0
        ws = getattr(loaded.flows[0], "websocket", None)
        assert ws is not None
        assert len(ws.messages) == 2
        assert ws.messages[0].from_client is True
        assert ws.messages[0].content == b"hello"
        assert ws.messages[0].is_text is True
        assert ws.messages[1].content == "世界".encode("utf-8")
        assert ws.messages[1].from_client is False
        assert ws.close_code == 1000
        assert ws.close_reason == "bye"
        assert ws.timestamp_end == 101.0
        # 行上的消息数与实际存储一致
        assert loaded.summaries[0]["ws_messages"] == 2
        assert loaded.summaries[0]["ws_closed"] is True

    def test_binary_message_round_trip(self, tmp_path):
        target = tmp_path / "ws.jsonl"
        flow = _ws_flow([_msg(bytes(range(16)), opcode=2)])   # Opcode.BINARY
        save_session(target, [flow])
        ws = getattr(load_session(target).flows[0], "websocket", None)
        assert ws is not None and len(ws.messages) == 1
        assert ws.messages[0].content == bytes(range(16))
        assert ws.messages[0].is_text is False

    def test_restored_flow_is_live_for_summarize(self, tmp_path):
        target = tmp_path / "ws.jsonl"
        save_session(target, [_ws_flow([_msg(b"a"), _msg(b"b")])])
        flow = load_session(target).flows[0]
        summary = CaptureAddon.summarize(flow)
        assert summary["is_websocket"] is True
        assert summary["ws_messages"] == 2
        assert summary["status"] == 101

    def test_non_ws_record_has_no_ws_key(self, tmp_path):
        target = tmp_path / "plain.jsonl"
        save_session(target, [_flow()])
        record = json.loads(target.read_text(encoding="utf-8").splitlines()[0])
        # summary 里本来就有 ws_messages 计数；关键是**记录顶层**没有 ws_messages
        assert "ws_messages" not in record

    def test_message_limit_truncates(self, tmp_path):
        target = tmp_path / "ws.jsonl"
        flow = _ws_flow([_msg(b"x") for _ in range(2100)])
        result = save_session(target, [flow])
        assert result.ok
        record = json.loads(target.read_text(encoding="utf-8").splitlines()[0])
        assert len(record["ws_messages"]["messages"]) == 2000
        assert record["ws_messages"]["total"] == 2100
        assert record["ws_messages"]["truncated"] is True
        # 恢复后行显示与实际存储一致（不是 2100）
        loaded = load_session(target)
        assert loaded.summaries[0]["ws_messages"] == 2000
        assert len(getattr(loaded.flows[0], "websocket").messages) == 2000

    def test_budget_exhaustion_drops_messages(self, tmp_path):
        target = tmp_path / "ws.jsonl"
        big = b"y" * 4096
        flow = _ws_flow([_msg(big) for _ in range(10)])
        limits = SessionLimits(body_limit=8 * 1024, total_limit=10 * 1024)
        result = save_session(target, [flow], limits)
        assert result.ok
        assert result.bodies_dropped == 1
        record = json.loads(target.read_text(encoding="utf-8").splitlines()[0])
        stored = record["ws_messages"]["messages"]
        assert 0 < len(stored) < 10
        assert record["ws_messages"]["truncated"] is True
        assert record["ws_messages"]["total"] == 10

    def test_old_file_without_ws_still_loads(self, tmp_path):
        """v1.11 前保存的文件没有 ws_messages 字段——必须照常恢复。"""
        target = tmp_path / "old.jsonl"
        save_session(target, [_flow()])
        record = json.loads(target.read_text(encoding="utf-8").splitlines()[0])
        assert "ws_messages" not in record
        loaded = load_session(target)
        assert loaded.count == 1 and loaded.skipped == 0
        assert getattr(loaded.flows[0], "websocket", None) is None

    def test_truncated_flag_reported_in_result(self, tmp_path):
        target = tmp_path / "ws.jsonl"
        # 5 × 400B = 2000B > 整包 1024B：第三条会被截到剩余预算
        flow = _ws_flow([_msg(b"z" * 400) for _ in range(5)])
        limits = SessionLimits(body_limit=1024, total_limit=1024)
        result = save_session(target, [flow], limits)
        assert result.bodies_truncated == 1
