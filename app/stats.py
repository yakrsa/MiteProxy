"""流量统计聚合：统计/概览页与 MCP 的 get_stats 工具共用同一套口径。

设计约束：
- **纯逻辑、不依赖 Qt**：UI 面板和 MCP 工具都调它，单测直接喂 flow 列表；
- **口径与列表列同源**：耗时走 ``addons.capture.request_span_ms``，URL 走
  ``app.replay.format_request_url``——统计页和流量列表对不上数是这类工具
  最招骂的 bug，所以绝不在这里另算一套；
- 大列表友好：5000 条一次性聚合只有一次排序（慢请求 Top N），
  域名/状态码/方法用 dict 累加，没有嵌套循环。

聚合范围由调用方决定：统计页传「当前列表里的会话」（删除过的不计入），
MCP 传 capture 全量快照——逻辑同一份，输入不同。
"""

from __future__ import annotations

import math
from datetime import datetime

# 耗时 / URL 口径与列表列、耗时页、MCP 详情同源（见 addons/capture.py 注释）
from addons.capture import request_span_ms
from app.replay import format_request_url

#: 时间直方图最多分多少桶（再多屏幕上也画不下，反而显得碎）
MAX_TIMELINE_BUCKETS = 48
#: 慢请求 / 域名 Top N 的默认条数与上限
DEFAULT_TOP_N = 10
MAX_TOP_N = 50


# ================================================================ 公共小工具


def match_url(flow, needle: str) -> bool:
    """URL 关键字匹配（大小写不敏感子串，命中「方法 + URL」）。

    与 MCP ``get_recent_flows`` 的 url 条件同口径——两边各写一份必然漂移，
    所以抽到这里共用（``app.mcpserver.match_flow`` 也 import 本函数）。
    """
    if not needle:
        return True
    req = getattr(flow, "request", None)
    if req is None:
        return False
    method = str(getattr(req, "method", "") or "")
    return needle.lower() in f"{method} {flow_url(flow)}".lower()


def flow_url(flow) -> str:
    """会话 URL（IPv6 裸地址会拼出畸形串，统一走 format_request_url）。"""
    req = getattr(flow, "request", None)
    if req is None:
        return ""
    try:
        return format_request_url(req)
    except Exception:
        return getattr(req, "pretty_url", "") or ""


def _iso(ts) -> str:
    """时间戳 → 本地 ISO 毫秒串（给人看；机器要算用 duration_ms）。"""
    try:
        return datetime.fromtimestamp(float(ts)).isoformat(timespec="milliseconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _status_of(flow) -> int:
    """响应状态码；没有响应（pending / 连接失败）记 0。"""
    res = getattr(flow, "response", None)
    if res is None:
        return 0
    try:
        return int(getattr(res, "status_code", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _size_of(msg) -> int:
    """消息体大小。raw_content 在流式响应期间为 None（mitmproxy 文档明确），
    按 0 计——len(None) 抛 TypeError 会让整次聚合失败。"""
    if msg is None:
        return 0
    try:
        return len(msg.raw_content or b"")
    except Exception:
        return 0


def _request_start(flow):
    """请求开始时间戳（秒）；取不到返回 None。"""
    req = getattr(flow, "request", None)
    ts = getattr(req, "timestamp_start", None) if req is not None else None
    return ts if isinstance(ts, (int, float)) and ts > 0 else None


def _percentile(sorted_values: list[float], pct: float) -> float:
    """线性插值分位数（numpy 默认口径）；空列表返回 0。"""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * pct
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(sorted_values[int(k)])
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


# ================================================================ 聚合


def compute_stats(flows, top_n: int = DEFAULT_TOP_N, url: str = "") -> dict:
    """聚合一组会话 → 统计字典（统计页与 MCP get_stats 的输出完全一致）。

    参数：
        flows:  会话对象可迭代对象（capture.flows 的快照或列表子集）；
        top_n:  域名 / 慢请求各取前多少条（1~MAX_TOP_N，越界钳制）；
        url:    可选 URL 关键字（大小写不敏感子串，命中方法+URL）。

    返回的字典全是 JSON 可序列化类型（MCP 直接 json.dumps）。
    """
    try:
        top_n = int(top_n)
    except (TypeError, ValueError):
        top_n = DEFAULT_TOP_N
    top_n = max(1, min(top_n, MAX_TOP_N))

    picked = [f for f in flows if match_url(f, url)] if url else list(flows)

    total = len(picked)
    methods: dict[str, int] = {}
    statuses: dict[int, int] = {}
    hosts: dict[str, dict] = {}
    durations: list[float] = []
    req_bytes = resp_bytes = 0
    errors = pending = ws_count = replay_count = 0
    first_ts: float | None = None
    last_ts: float | None = None

    for f in picked:
        req = getattr(f, "request", None)
        res = getattr(f, "response", None)
        if getattr(f, "websocket", None) is not None:
            ws_count += 1
        if getattr(f, "is_replay", None):
            replay_count += 1

        method = str(getattr(req, "method", "") or "") if req is not None else ""
        methods[method or "-"] = methods.get(method or "-", 0) + 1

        status = _status_of(f)
        statuses[status] = statuses.get(status, 0) + 1
        if status >= 400:
            errors += 1
        elif status == 0:
            pending += 1

        # 耗时口径与列表「耗时」列同源（含弱网延迟；pending 会话会随时间
        # 增长——那正是列表里看到的数字，统计照抄即可）
        duration = request_span_ms(f)
        durations.append(duration)

        req_size = _size_of(req)
        resp_size = _size_of(res)
        req_bytes += req_size
        resp_bytes += resp_size

        ts = _request_start(f)
        if ts is not None:
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)

        host = str(getattr(req, "pretty_host", "") or "") if req is not None else ""
        host = host or "-"
        agg = hosts.get(host)
        if agg is None:
            agg = hosts[host] = {
                "host": host, "count": 0, "errors": 0,
                "duration_total_ms": 0.0, "max_duration_ms": 0.0,
                "response_bytes": 0, "request_bytes": 0,
            }
        agg["count"] += 1
        if status >= 400:
            agg["errors"] += 1
        agg["duration_total_ms"] += duration
        agg["max_duration_ms"] = max(agg["max_duration_ms"], duration)
        agg["response_bytes"] += resp_size
        agg["request_bytes"] += req_size

    durations.sort()
    avg = round(sum(durations) / total, 1) if total else 0.0

    host_rows = []
    for agg in hosts.values():
        count = agg["count"]
        host_rows.append({
            "host": agg["host"],
            "count": count,
            "errors": agg["errors"],
            "error_rate": round(agg["errors"] / count, 4) if count else 0.0,
            "avg_duration_ms": round(agg["duration_total_ms"] / count, 1) if count else 0.0,
            "max_duration_ms": round(agg["max_duration_ms"], 1),
            "response_bytes": agg["response_bytes"],
            "request_bytes": agg["request_bytes"],
        })
    # 请求数降序；并列时看平均耗时（慢的排前面，更值得关注）
    host_rows.sort(key=lambda r: (-r["count"], -r["avg_duration_ms"], r["host"]))
    host_rows = host_rows[:top_n]

    slow_rows = []
    for f in sorted(picked, key=lambda f: -request_span_ms(f))[:top_n]:
        duration = round(request_span_ms(f), 1)
        if duration <= 0:
            continue        # 没耗时数据的会话进 Top N 没有意义
        req = getattr(f, "request", None)
        slow_rows.append({
            "id": str(getattr(f, "id", "") or ""),
            "method": str(getattr(req, "method", "") or "") if req is not None else "",
            "url": flow_url(f),
            "host": str(getattr(req, "pretty_host", "") or "") if req is not None else "",
            "status": _status_of(f),
            "duration_ms": duration,
            "response_bytes": _size_of(getattr(f, "response", None)),
        })

    method_rows = [
        {"method": m, "count": c}
        for m, c in sorted(methods.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    status_rows = [
        {"status": s, "count": c}
        for s, c in sorted(statuses.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return {
        "total": total,
        "errors": errors,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "pending": pending,
        "avg_duration_ms": avg,
        "p95_duration_ms": round(_percentile(durations, 0.95), 1),
        "max_duration_ms": round(durations[-1], 1) if durations else 0.0,
        "request_bytes": req_bytes,
        "response_bytes": resp_bytes,
        "methods": method_rows,
        "statuses": status_rows,
        "hosts": host_rows,
        "slow_requests": slow_rows,
        "websockets": ws_count,
        "replays": replay_count,
        "first_at": _iso(first_ts),
        "last_at": _iso(last_ts),
        "timeline": _timeline(picked, first_ts, last_ts),
    }


def _timeline(flows, first_ts, last_ts) -> dict:
    """把请求按开始时间等宽分桶（最多 MAX_TIMELINE_BUCKETS 桶）。

    没有时间戳的会话（异常 flow）不进直方图——硬塞进第一桶会让
    「起点时刻」撒谎。span 为 0（全部同一瞬间，如重放一批 mock）时
    所有点落进同一个桶，bucket_seconds 记 0。
    """
    points = []
    for f in flows:
        ts = _request_start(f)
        if ts is not None:
            points.append((ts, _size_of(getattr(f, "response", None))))
    if not points:
        return {"buckets": [], "bucket_seconds": 0.0, "span_seconds": 0.0}

    points.sort()
    start, end = points[0][0], points[-1][0]
    span = max(end - start, 0.0)
    # span 为 0（全部同一瞬间，如重放一批 mock）时只留一个桶——
    # 按点数切出 N 个空桶只会画出一片空白，没有信息量
    n = 1 if span <= 0 else min(MAX_TIMELINE_BUCKETS, max(1, len(points)))
    bucket_seconds = span / n if span > 0 else 0.0

    counts = [0] * n
    sizes = [0] * n
    for ts, size in points:
        if bucket_seconds > 0:
            idx = min(n - 1, int((ts - start) / bucket_seconds))
        else:
            idx = 0
        counts[idx] += 1
        sizes[idx] += size

    return {
        "buckets": [
            {
                "start": _iso(start + i * bucket_seconds),
                "end": _iso(start + (i + 1) * bucket_seconds),
                "count": counts[i],
                "response_bytes": sizes[i],
            }
            for i in range(n)
        ],
        "bucket_seconds": round(bucket_seconds, 3),
        "span_seconds": round(span, 3),
    }
