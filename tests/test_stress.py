"""大流量长跑验证（路线图 #12）：高并发 / 长时间抓包下的稳定性与容量边界。

要验证的不变量（任何一个被打破都会变成「抓半天内存爆掉 / 界面卡死」）：

1. **容量硬上限**：``FlowStore.max_rows`` 与 ``CaptureAddon._max_flows`` 都是
   5000，喂远超上限的流量后，列表行数与缓存条数恒不超过上限——内存不会
   随抓包时长无限增长。
2. **完整链路抗压**：``summarize → append → update`` 在数万次调用下无异常、
   无泄漏式增长（每批结束后行数仍贴着上限）。
3. **统计聚合性能**：满容量（5000 条）下一次 ``compute_stats`` 必须在合理
   时间内完成（验证统计页 / MCP get_stats 不会在长跑后越跑越慢）。
4. **畸形流量不崩**：无响应（pending）/ 无 server_conn / 弱网延迟 / WebSocket
   各类 flow 在 summarize 下长跑不抛异常。

不跑真实代理 + curl 循环（沙箱里不可重复、耗时），而是用 mitmproxy 的
``tflow`` 造等价 flow 对象，把真实 addon / 模型 / 统计逻辑全跑一遍——
要验证的容量与性能不变量都在这些组件里。
"""

import time

import pytest
from mitmproxy.test import tflow

from addons.capture import CaptureAddon, MAX_FLOWS, MAX_FLOWS as _CAP
from app.stats import compute_stats
from app.ui.flow_store import FlowStore, MAX_ROWS


# ----------------------------------------------------------------- 造数据


def _flow(n, *, response=True, websocket=False, throttle_ms=0, broken=False):
    """造一条等价 flow：唯一 id 保证 request→response 走「更新」而非「新增」。"""
    if websocket:
        f = tflow.tflow(resp=True)
        # 极简 WS 对象：summarize 只读 messages / timestamp_end
        class _Msg:
            content = (b"ws-payload-%d" % (n % 7)) if not broken else None

        class _Ws:
            messages = [_Msg(), _Msg()]
            timestamp_end = time.time() if not broken else None

        f.websocket = _Ws()
    else:
        f = tflow.tflow(resp=response)
    f.id = "stress-flow-%d" % n
    if throttle_ms:
        f.metadata = {"mproxy_throttle_ms": throttle_ms}
    return f


def _pipeline(max_rows=MAX_ROWS, max_flows=MAX_FLOWS):
    """搭一条真实链路：CaptureAddon →（summarize）→ FlowStore。"""
    store = FlowStore()
    store.set_max_rows(max_rows)
    cap = CaptureAddon(max_flows=max_flows)

    def on_flow(s):
        store.append(s)

    def on_update(s):
        store.update(s)

    cap._on_flow = on_flow
    cap._on_update = on_update
    return cap, store


# ----------------------------------------------------------------- 1. 容量上限


def test_store_caps_at_max_rows():
    store = FlowStore()
    store.set_max_rows(MAX_ROWS)  # 默认 5000
    for n in range(20000):  # 远超上限
        store.append({
            "id": "r-%d" % n, "method": "GET", "host": "h", "server_ip": "",
            "path": "/", "url": "http://h/", "status": 200, "size": 1,
            "req_size": 0, "duration_ms": 1.0, "throttle_ms": 0,
            "content_type": "text/plain", "marked": "", "is_replay": False,
            "comment": "", "timestamp": time.time(), "is_connect": False,
            "is_websocket": False, "ws_messages": 0, "ws_closed": False,
            "timings": {},
        })
    assert len(store.rows) == MAX_ROWS  # 精确裁到上限，不是「掉到 90%」
    assert len(store.rows) <= MAX_ROWS


def test_store_respects_lower_limit():
    store = FlowStore()
    store.set_max_rows(100)  # 用户把保存条数调到 100
    for n in range(5000):
        store.append({"id": "r-%d" % n, "method": "GET", "host": "h",
                      "server_ip": "", "path": "/", "url": "http://h/",
                      "status": 200, "size": 1, "req_size": 0,
                      "duration_ms": 1.0, "throttle_ms": 0,
                      "content_type": "text/plain", "marked": "",
                      "is_replay": False, "comment": "", "timestamp": 0.0,
                      "is_connect": False, "is_websocket": False,
                      "ws_messages": 0, "ws_closed": False, "timings": {}})
    assert len(store.rows) == 100


def test_capture_flows_capped():
    cap = CaptureAddon(max_flows=MAX_FLOWS)
    for n in range(20000):
        f = _flow(n)
        cap.request(f)
        cap.response(f)
    assert len(cap.flows) <= MAX_FLOWS
    assert len(cap.flows) == MAX_FLOWS  # 精确裁到上限


# ------------------------------------------------------- 2. 完整链路长跑


def test_full_pipeline_long_run():
    """20 批 × 1000 条 = 2 万次 request+response，全程走真实回调与模型。

    验证：不抛异常、行数/缓存条数恒贴着上限、过程里行数从不越界。
    """
    cap, store = _pipeline()

    batches = 20
    per_batch = 1000
    peak_rows = 0
    peak_flows = 0
    base = 0
    for b in range(batches):
        for i in range(per_batch):
            n = base + i
            # 混入各类流量：大部分正常响应，少量 pending / WS / 弱网
            if i % 50 == 0:
                f = _flow(n, response=False)            # pending
            elif i % 70 == 0:
                f = _flow(n, websocket=True)            # WebSocket
            elif i % 90 == 0:
                f = _flow(n, throttle_ms=250)           # 弱网延迟
            else:
                f = _flow(n)
            cap.request(f)
            cap.response(f)
            peak_rows = max(peak_rows, len(store.rows))
            peak_flows = max(peak_flows, len(cap.flows))
        base += per_batch

    # 行数/缓存条数自始至终没越过上限
    assert peak_rows <= MAX_ROWS
    assert peak_flows <= MAX_FLOWS
    # 长跑结束后仍精确贴着上限（验证了「每批都在淘汰」，没有悄然堆积）
    assert len(store.rows) == MAX_ROWS
    assert len(cap.flows) == MAX_FLOWS


def test_long_run_stats_consistent():
    """长跑后统计聚合的 total 必须等于当前列表行数（口径不漂移）。"""
    cap, store = _pipeline()
    for n in range(8000):
        f = _flow(n)
        cap.request(f)
        cap.response(f)
    stats = compute_stats(list(cap.flows.values()))
    assert stats["total"] == len(cap.flows) == MAX_FLOWS


# ----------------------------------------------------- 3. 统计聚合性能


def test_stats_performant_at_capacity():
    """满容量 5000 条聚合必须足够快（统计页 / MCP get_stats 不能越跑越慢）。"""
    cap = CaptureAddon(max_flows=MAX_FLOWS)
    for n in range(MAX_FLOWS):
        f = _flow(n, throttle_ms=n % 5)
        cap.request(f)
        cap.response(f)

    start = time.perf_counter()
    stats = compute_stats(list(cap.flows.values()))
    elapsed = time.perf_counter() - start

    assert stats["total"] == MAX_FLOWS
    # 5000 条一次性聚合（含一次排序 + 域名累加）应远低于 1 秒
    assert elapsed < 1.0, "compute_stats(5000) 耗时 %.3fs，超过 1s 阈值" % elapsed


def test_stats_top_n_bounds():
    """慢请求 Top N 不超上限，且耗时 >0 的才进榜（长跑后无空榜污染）。"""
    cap = CaptureAddon(max_flows=MAX_FLOWS)
    for n in range(MAX_FLOWS):
        f = _flow(n)
        cap.request(f)
        cap.response(f)
    stats = compute_stats(list(cap.flows.values()), top_n=10)
    assert len(stats["slow_requests"]) <= 10
    assert len(stats["hosts"]) <= 10
    assert all(r["duration_ms"] > 0 for r in stats["slow_requests"])


# ----------------------------------------------------- 4. 畸形流量抗压


def test_summarize_handles_malformed():
    """各类畸形 flow 在 summarize 下长跑不抛异常（健壮性回归护栏）。"""
    cap = CaptureAddon(max_flows=MAX_FLOWS)
    for n in range(3000):
        if n % 4 == 0:
            f = _flow(n, response=False)        # pending：无响应
        elif n % 4 == 1:
            f = _flow(n, websocket=True)        # WebSocket
        elif n % 4 == 2:
            f = _flow(n, websocket=True, broken=True)  # 坏 WS：None 消息/无结束
        else:
            f = _flow(n, throttle_ms=n % 10)
        try:
            cap.request(f)
            cap.response(f)
        except Exception as e:  # pragma: no cover
            pytest.fail("summarize 对畸形 flow 抛异常: %r" % e)
    # 即便混入坏 WS，行数仍受控
    assert len(cap.flows) <= MAX_FLOWS


def test_pending_flows_do_not_corrupt_store():
    """pending（无响应）流量进列表后，长跑不出现 None 行或越界。"""
    cap, store = _pipeline()
    for n in range(6000):
        f = _flow(n, response=(n % 3 != 0))  # 1/3 是 pending
        cap.request(f)
        cap.response(f)
    assert len(store.rows) == MAX_ROWS
    for row in store.rows:
        assert row is not None
        assert row.get("id")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "--basetemp=/tmp/pytest-tmp-stress"]))
