"""统计聚合（app/stats.py）的单元测试。

统计页与 MCP 的 get_stats 共用这份逻辑，所以这里把口径钉死：
错误率、域名聚合、慢请求排序、时间分桶、URL 过滤、边界（空列表 /
无响应 / WS / 重放）。全部纯逻辑，不起 Qt、不起服务。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.stats import (
    DEFAULT_TOP_N,
    MAX_TIMELINE_BUCKETS,
    MAX_TOP_N,
    compute_stats,
    match_url,
)


def _flow(url="http://x.test/api/list", method="GET", status=200,
          duration_ms=100.0, host=None, req_size=0, resp_size=0,
          at=1000.0):
    """造假会话：只带统计用到的字段（鸭子类型，不依赖 mitmproxy 内部）。"""
    if host is None and "://" in url:
        host = url.split("://", 1)[1].split("/", 1)[0]
    return SimpleNamespace(
        id=url + str(at),
        request=SimpleNamespace(
            method=method,
            pretty_host=host or "",
            pretty_url=url,
            path=url.split(host or "", 1)[-1] if host else url,
            timestamp_start=at,
            raw_content=b"r" * req_size,
        ),
        response=None if status == 0 else SimpleNamespace(
            status_code=status,
            timestamp_end=at + duration_ms / 1000.0,
            raw_content=b"x" * resp_size,
        ),
        websocket=None,
        is_replay=False,
    )


# ------------------------------------------------------------------ 总览


def test_empty_flows():
    s = compute_stats([])
    assert s["total"] == 0
    assert s["errors"] == 0
    assert s["error_rate"] == 0.0
    assert s["avg_duration_ms"] == 0.0
    assert s["hosts"] == [] and s["slow_requests"] == []
    assert s["statuses"] == [] and s["methods"] == []
    assert s["timeline"]["buckets"] == []


def test_totals_and_error_rate():
    flows = [
        _flow(url="http://a.test/1", status=200),
        _flow(url="http://a.test/2", status=404),
        _flow(url="http://a.test/3", status=500),
    ]
    s = compute_stats(flows)
    assert s["total"] == 3
    assert s["errors"] == 2                    # 4xx + 5xx 都算错误
    assert s["error_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert s["pending"] == 0


def test_pending_flows_counted_separately():
    """没有响应的会话不是错误（连接层失败更像「没响应」）。"""
    s = compute_stats([_flow(status=0), _flow(status=200)])
    assert s["pending"] == 1
    assert s["errors"] == 0
    assert s["statuses"][0] == {"status": 0, "count": 1}


def test_avg_and_max_duration():
    flows = [
        _flow(url="http://a.test/1", duration_ms=100.0),
        _flow(url="http://a.test/2", duration_ms=300.0),
    ]
    s = compute_stats(flows)
    assert s["avg_duration_ms"] == 200.0
    assert s["max_duration_ms"] == 300.0


def test_p95_interpolates():
    flows = [
        _flow(url=f"http://a.test/{i}", duration_ms=float(i))
        for i in range(1, 101)
    ]
    s = compute_stats(flows)
    # 1..100 的线性插值 P95 = 1 + 99*0.95 = 95.05
    assert s["p95_duration_ms"] == pytest.approx(95.05, abs=0.2)


def test_bytes_and_ws_replay_counters():
    flows = [
        _flow(url="http://a.test/1", req_size=10, resp_size=100),
        _flow(url="http://a.test/2", req_size=5, resp_size=50),
    ]
    flows[1].is_replay = True
    flows[0].websocket = object()             # 只要不是 None 就算 WS 会话
    s = compute_stats(flows)
    assert s["request_bytes"] == 15
    assert s["response_bytes"] == 150
    assert s["websockets"] == 1
    assert s["replays"] == 1


# ------------------------------------------------------------------ 分布


def test_hosts_aggregation_sorted_by_count():
    flows = [
        _flow(url="http://b.test/1", status=500, duration_ms=50.0, resp_size=10),
        _flow(url="http://b.test/2", status=200, duration_ms=150.0, resp_size=20),
        _flow(url="http://a.test/1", status=200, duration_ms=10.0, resp_size=30),
    ]
    s = compute_stats(flows)
    assert [h["host"] for h in s["hosts"]] == ["b.test", "a.test"]
    b = s["hosts"][0]
    assert b["count"] == 2
    assert b["errors"] == 1
    assert b["error_rate"] == pytest.approx(0.5, abs=1e-4)
    assert b["avg_duration_ms"] == 100.0
    assert b["max_duration_ms"] == 150.0
    assert b["response_bytes"] == 30


def test_hosts_tie_broken_by_slower_avg():
    """请求数并列时平均耗时高的排前面——更值得关注。"""
    flows = [
        _flow(url="http://a.test/1", duration_ms=10.0),
        _flow(url="http://b.test/1", duration_ms=900.0),
    ]
    s = compute_stats(flows)
    assert [h["host"] for h in s["hosts"]] == ["b.test", "a.test"]


def test_statuses_and_methods_sorted_by_count():
    flows = [
        _flow(url="http://a.test/1", status=200, method="GET"),
        _flow(url="http://a.test/2", status=200, method="GET"),
        _flow(url="http://a.test/3", status=404, method="POST"),
    ]
    s = compute_stats(flows)
    assert s["statuses"] == [
        {"status": 200, "count": 2}, {"status": 404, "count": 1}
    ]
    assert s["methods"] == [
        {"method": "GET", "count": 2}, {"method": "POST", "count": 1}
    ]


def test_slow_requests_sorted_and_capped():
    flows = [
        _flow(url=f"http://a.test/{i}", duration_ms=float(i * 10), at=float(i))
        for i in range(1, 21)
    ]
    s = compute_stats(flows, top_n=5)
    assert len(s["slow_requests"]) == 5
    durs = [r["duration_ms"] for r in s["slow_requests"]]
    assert durs == sorted(durs, reverse=True)
    assert durs[0] == 200.0
    assert s["slow_requests"][0]["url"].endswith("/20")


def test_slow_requests_skip_zero_duration():
    """没耗时数据的会话进 Top N 没有意义（request_span_ms 为 0）。"""
    flow = _flow(url="http://a.test/1")
    flow.request.timestamp_start = None
    flow.response = None
    s = compute_stats([flow])
    assert s["slow_requests"] == []


def test_top_n_clamped():
    flows = [_flow(url=f"http://h{i}.test/1", at=float(i)) for i in range(60)]
    s = compute_stats(flows, top_n=9999)
    assert len(s["hosts"]) == MAX_TOP_N
    # 非法值回落默认，不炸
    assert len(compute_stats(flows, top_n="abc")["hosts"]) == DEFAULT_TOP_N


# ------------------------------------------------------------------ 时间线


def test_timeline_buckets():
    flows = [
        _flow(url=f"http://a.test/{i}", at=1000.0 + i * 0.5, resp_size=i)
        for i in range(30)
    ]
    tl = compute_stats(flows)["timeline"]
    assert len(tl["buckets"]) == 30          # 点数少于上限时一桶一点
    assert sum(b["count"] for b in tl["buckets"]) == 30
    assert sum(b["response_bytes"] for b in tl["buckets"]) == sum(range(30))
    assert tl["span_seconds"] == pytest.approx(14.5, abs=0.01)


def test_timeline_capped_and_single_instant():
    many = [_flow(url=f"http://a.test/{i}", at=1000.0 + i * 0.01)
            for i in range(500)]
    tl = compute_stats(many)["timeline"]
    assert len(tl["buckets"]) == MAX_TIMELINE_BUCKETS
    assert sum(b["count"] for b in tl["buckets"]) == 500

    # 全部同一时刻（重放一批 mock）：所有点落进同一个桶
    same = [_flow(url=f"http://a.test/{i}", at=1000.0) for i in range(5)]
    tl2 = compute_stats(same)["timeline"]
    assert len(tl2["buckets"]) == 1
    assert tl2["buckets"][0]["count"] == 5
    assert tl2["bucket_seconds"] == 0.0


def test_timeline_skips_flows_without_timestamp():
    broken = _flow(url="http://a.test/1")
    broken.request.timestamp_start = None
    ok = _flow(url="http://a.test/2", at=1000.0)
    tl = compute_stats([broken, ok])["timeline"]
    assert sum(b["count"] for b in tl["buckets"]) == 1


# ------------------------------------------------------------------ URL 过滤


def test_match_url():
    f = _flow(url="http://a.test/api/list", method="GET")
    assert match_url(f, "") is True                       # 空 = 不过滤
    assert match_url(f, "API") is True                    # 大小写不敏感
    assert match_url(f, "get http") is True               # 方法也参与匹配
    assert match_url(f, "a.test/api") is True
    assert match_url(f, "nope") is False
    assert match_url(SimpleNamespace(request=None), "x") is False


def test_compute_stats_url_filter():
    flows = [
        _flow(url="http://a.test/api/1", status=500),
        _flow(url="http://b.test/other/2", status=200),
    ]
    s = compute_stats(flows, url="api")
    assert s["total"] == 1
    assert s["errors"] == 1
    assert [h["host"] for h in s["hosts"]] == ["a.test"]


# ------------------------------------------------------------------ 输出形态


def test_output_is_json_serializable():
    """MCP 直接 json.dumps 这个字典——任何非标准类型都会在路上炸。"""
    flows = [_flow(url="http://a.test/1", status=500, resp_size=7)]
    s = compute_stats(flows)
    text = json.dumps(s, ensure_ascii=False)
    assert '"total": 1' in text


def test_iso_timestamps_present():
    s = compute_stats([_flow(url="http://a.test/1", at=1000.0)])
    assert s["first_at"] and s["last_at"]
    assert "T" in s["first_at"]
