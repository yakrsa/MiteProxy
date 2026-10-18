"""请求分段耗时（addons.capture.extract_timings + 详情页「耗时」签，v2.3.0）。

对齐 Fiddler Statistics 的计时口径：连接（含 DNS）/ TLS / 发送 / 等待（TTFB）/
接收五段，缺锚点的段记 0 且不显示；mock 与恢复会话都有明确定义。
"""

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mitmproxy.test import tflow  # noqa: E402

from addons.capture import (  # noqa: E402
    CaptureAddon,
    extract_timing_marks,
    extract_timings,
    request_span_ms,
    timing_span,
)
from app import session as session_mod  # noqa: E402
from app.session import SessionLimits, load_session, save_session  # noqa: E402


def _timed_flow(t0: float, throttle_ms: float | None = None):
    """一条时间轴完整的 flow：建连 30ms / TLS 40ms / 发送 2ms / 等待 120ms / 接收 35ms。"""
    f = tflow.tflow(resp=True)
    f.client_conn.timestamp_start = t0
    f.server_conn.timestamp_start = t0 + 0.001
    f.server_conn.timestamp_tcp_setup = t0 + 0.031
    f.server_conn.timestamp_tls_setup = t0 + 0.071
    f.request.timestamp_start = t0 + 0.072
    f.request.timestamp_end = t0 + 0.074
    f.response.timestamp_start = t0 + 0.194
    f.response.timestamp_end = t0 + 0.229
    if throttle_ms is not None:
        f.metadata = {"mproxy_throttle_ms": throttle_ms}
    return f


class TestExtractTimings:
    def test_full_breakdown(self):
        t = extract_timings(_timed_flow(time.time() - 1))
        assert t == {
            "connect": 30.0,   # tcp_setup - conn_start
            "tls": 40.0,       # tls_setup - tcp_setup
            "send": 2.0,       # req_end - req_start
            "wait": 120.0,     # res_start - req_end（TTFB）
            "receive": 35.0,   # res_end - res_start
        }

    def test_http_plain_has_no_tls_phase(self):
        """明文 HTTP：tls_setup 为 None，TLS 段记 0（详情页据此不显示该行）。"""
        f = _timed_flow(time.time() - 1)
        f.server_conn.timestamp_tls_setup = None
        t = extract_timings(f)
        assert t["tls"] == 0.0
        assert t["connect"] == 30.0

    def test_missing_anchors_are_zero(self):
        """mock 注入的响应没有 server_conn 时间戳：连接/TLS 段为 0。"""
        f = tflow.tflow(resp=True)
        f.server_conn.timestamp_start = None
        f.server_conn.timestamp_tcp_setup = None
        f.server_conn.timestamp_tls_setup = None
        t = extract_timings(f)
        assert t["connect"] == 0.0 and t["tls"] == 0.0

    def test_negative_clamped_to_zero(self):
        """时钟跳变导致后向时间戳：钳到 0，不出现负耗时。"""
        f = _timed_flow(time.time() - 1)
        f.server_conn.timestamp_tcp_setup = f.server_conn.timestamp_start - 5
        t = extract_timings(f)
        assert t["connect"] == 0.0

    def test_summarize_includes_timings(self):
        summary = CaptureAddon.summarize(_timed_flow(time.time() - 1))
        assert summary["timings"]["wait"] == 120.0
        # duration_ms 口径 = 请求开始 → 响应结束（客户端感知的 157ms），
        # 分段里的建连/TLS 发生在请求开始之前，不计入 duration——
        # 两端口径不同是故意的（Fiddler 的 Total 也是按请求起点算）
        assert abs(summary["duration_ms"] - 157.0) < 0.5
        assert summary["timings"]["connect"] + summary["timings"]["tls"] == 70.0


class TestRequestSpan:
    """列表「耗时」列口径（request_span_ms）与耗时分析必须同源对账。"""

    def test_equals_summarize_duration(self):
        """上游真实响应：span 与 summarize.duration_ms 逐字相等。"""
        f = _timed_flow(time.time() - 1, throttle_ms=300.0)
        assert request_span_ms(f) == CaptureAddon.summarize(f)["duration_ms"]
        # = 发送 2 + 等待 120 + 接收 35 + 弱网 300
        assert request_span_ms(f) == 457.0

    def test_equals_send_wait_receive_phases(self):
        """无弱网时 span = send+wait+receive（建连/TLS 发生在请求前，不计入）。"""
        f = _timed_flow(time.time() - 1)
        t = extract_timings(f)
        assert request_span_ms(f) == round(t["send"] + t["wait"] + t["receive"], 1)
        assert request_span_ms(f) == 157.0

    def test_mock_flow_uses_current_time(self):
        """mock 响应无 timestamp_end：退化为当前时间（含已睡完的延迟）。"""
        f = tflow.tflow(resp=True)
        f.request.timestamp_start = time.time() - 0.05
        f.response.timestamp_end = None
        f.metadata = {"mproxy_throttle_ms": 100.0}
        span = request_span_ms(f)
        assert 40.0 < span < 200.0     # ≈50ms，且不把 throttle 重复计一次
        # 两次调用各自取 time.time()，允许 ms 级抖动
        assert span == pytest.approx(CaptureAddon.summarize(f)["duration_ms"], abs=1.0)

    def test_pending_flow_is_zero(self):
        """响应未返回（pending）：列表耗时列为 0。"""
        f = tflow.tflow(resp=False)
        assert request_span_ms(f) == 0.0


class TestTimingMarks:
    """「具体时刻」（绝对时钟）与分段耗时同一根时间轴。

    Fiddler 的 Timer 表同样给绝对时间：只看耗时不知道「什么时候慢的」，
    有绝对时刻才能和服务端日志、上下游链路按时间对账。
    """

    def test_marks_match_durations(self):
        """每段的「结束 - 开始」必须逐字等于耗时，不许两处各算一遍。"""
        f = _timed_flow(time.time() - 1)
        marks = extract_timing_marks(f)
        timings = extract_timings(f)
        assert set(marks) == set(timings)
        for phase, (start, end) in marks.items():
            assert start is not None and end is not None
            assert round((end - start) * 1000, 1) == timings[phase]

    def test_missing_anchors_are_none(self):
        """mock / 本地映射没有网络锚点：时刻为 None（UI 不显示该行）。"""
        f = tflow.tflow(resp=True)
        f.server_conn.timestamp_start = None
        f.server_conn.timestamp_tcp_setup = None
        f.server_conn.timestamp_tls_setup = None
        f.response.timestamp_start = None
        f.response.timestamp_end = None
        marks = extract_timing_marks(f)
        assert marks["connect"] == (None, None)
        assert marks["tls"] == (None, None)
        assert marks["wait"][1] is None        # 没有响应开始锚点
        assert marks["receive"] == (None, None)
        assert marks["send"][0] is not None    # 发送段仍有请求时间戳

    def test_span_starts_at_connection(self):
        """顶部「起点」取最早锚点（建连早于请求发送），与总耗时同起点。"""
        t0 = time.time() - 1
        f = _timed_flow(t0)
        start, end = timing_span(f)
        assert start == pytest.approx(t0 + 0.001)   # server_conn.timestamp_start
        assert end == pytest.approx(t0 + 0.229)     # response.timestamp_end

    def test_span_without_response_ends_at_request(self):
        """响应未返回：终点退化为请求发送完成时刻，不留空。"""
        t0 = time.time() - 1
        f = tflow.tflow(resp=False)
        f.server_conn.timestamp_start = t0
        f.server_conn.timestamp_tcp_setup = t0 + 0.031
        f.server_conn.timestamp_tls_setup = t0 + 0.071
        f.request.timestamp_start = t0 + 0.072
        f.request.timestamp_end = t0 + 0.074
        start, end = timing_span(f)
        assert start == pytest.approx(t0)
        assert end == pytest.approx(t0 + 0.074)


class TestClockFormat:
    """绝对时间戳 → 时钟串：毫秒精度，且不出现「.1000」这种不存在的时刻。"""

    def test_millisecond_precision(self):
        from datetime import datetime

        from app.ui.detail_panel import _fmt_clock

        ts = datetime(2026, 10, 17, 18, 42, 4, 511000).timestamp()
        assert _fmt_clock(ts) == "18:42:04.511"
        assert _fmt_clock(ts, with_date=True) == "2026-10-17 18:42:04.511"

    def test_never_formats_1000_milliseconds(self):
        """.9999 秒取小数会进位成 .1000——必须走 microsecond // 1000。"""
        from datetime import datetime

        from app.ui.detail_panel import _fmt_clock

        ts = datetime(2026, 1, 1, 0, 0, 0, 999999).timestamp()
        assert _fmt_clock(ts).endswith(".999")

    def test_missing_returns_empty(self):
        from app.ui.detail_panel import _fmt_clock

        assert _fmt_clock(None) == ""
        assert _fmt_clock(0) == ""


class TestTimingsSessionRoundTrip:
    def test_saved_and_restored_flow_keeps_breakdown(self, tmp_path):
        """落盘 → 读回：恢复的 flow 仍能算出同样的分段（连接/TLS 靠
        server_conn 时间戳还原，老文件没有该字段也不炸）。"""
        f = _timed_flow(time.time() - 1)
        path = tmp_path / "s.jsonl"
        save_session(path, [f], limits=SessionLimits())
        result = load_session(path)
        assert result.flows
        t = extract_timings(result.flows[0])
        assert t == {
            "connect": 30.0, "tls": 40.0, "send": 2.0,
            "wait": 120.0, "receive": 35.0,
        }
        # 具体时刻也要原样回来，否则恢复的会话只剩耗时、看不出何时发生
        original = extract_timing_marks(f)
        restored = extract_timing_marks(result.flows[0])
        for phase in original:
            for before, after in zip(original[phase], restored[phase]):
                assert before == pytest.approx(after)

    def test_old_record_without_server_conn_field(self, tmp_path):
        """兼容旧会话文件：没有 server_conn 字段时连接/TLS 段为 0，不抛错。"""
        f = _timed_flow(time.time() - 1)
        path = tmp_path / "s.jsonl"
        save_session(path, [f], limits=SessionLimits())
        lines = path.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[0])
        rec.pop("server_conn", None)
        path.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
        result = load_session(path)
        t = extract_timings(result.flows[0])
        assert t["connect"] == 0.0 and t["tls"] == 0.0
        assert t["wait"] == 120.0


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestTimingsPane:
    def test_full_flow_shows_five_phase_rows(self, qapp):
        from app.ui.detail_panel import DetailPanel

        panel = DetailPanel()
        panel.show_flow(_timed_flow(time.time() - 1, throttle_ms=300.0))
        assert len(panel.timings_pane._rows) == 5
        assert panel.tabs.isTabVisible(panel.timings_index)
        assert "527.0" in panel.timings_pane.total_label.text()
        assert "300.0" in panel.timings_pane.total_label.text()   # 弱网单列

    def test_rows_show_absolute_clock(self, qapp):
        """每行带「开始时刻」绝对时钟 + 表头 + 顶部起止，光有耗时不够用。"""
        from datetime import datetime

        from app.ui.detail_panel import DetailPanel

        base = datetime(2026, 10, 17, 18, 42, 4).timestamp()
        panel = DetailPanel()
        panel.show_flow(_timed_flow(base))
        pane = panel.timings_pane

        assert not pane.header.isHidden()
        assert pane.axis_label.text().startswith("起点 2026-10-17 18:42:04.001")
        assert "终点 18:42:04.229" in pane.axis_label.text()   # 同一天省日期

        clocks = [row["clock"].text() for row in pane._rows]
        assert clocks[0] == "18:42:04.001"      # server_conn.timestamp_start
        assert clocks[-1] == "18:42:04.194"     # response.timestamp_start
        assert clocks == sorted(clocks)         # 时间轴单调递增

        tip = pane._rows[0]["clock"].toolTip()
        assert "开始：2026-10-17 18:42:04.001" in tip
        assert "结束：2026-10-17 18:42:04.031" in tip
        assert "相对起点：+0.0 ms" in tip

    def test_gap_between_span_and_phases_is_explained(self, qapp):
        """时刻跨度大于各段之和时，备注必须说明差额落在哪。

        真实抓包里 TLS 完成后到客户端真正发请求常有几十毫秒间隙；不解释
        的话，「时刻从 .187 走到 .354（167ms）但总耗时 92.9ms」看着像算错。
        """
        from app.ui.detail_panel import DetailPanel

        f = _timed_flow(time.time() - 1)
        # 在 TLS 完成与请求发送之间插入 74ms 间隙（各段耗时不变，只拉开墙钟）
        for attr in ("timestamp_start", "timestamp_end"):
            setattr(f.request, attr, getattr(f.request, attr) + 0.074)
            setattr(f.response, attr, getattr(f.response, attr) + 0.074)

        panel = DetailPanel()
        panel.show_flow(f)
        pane = panel.timings_pane
        assert "时段跨度" in pane.axis_label.text()
        assert "不属于上述任何分段" in pane.note_label.text()
        assert "其中 75.0 ms" in pane.note_label.text()   # 74 新增 + 原有 1ms 间隙

    def test_clock_header_translated_in_english(self, qapp):
        """新增列头也要有英文——否则英文界面里冒出中文列名。"""
        from PySide6.QtWidgets import QLabel

        from app.i18n import load_language
        from app.ui.detail_panel import DetailPanel

        load_language(qapp, "en")
        try:
            panel = DetailPanel()
            panel.show_flow(_timed_flow(time.time() - 1))
            labels = [
                w.text()
                for w in panel.timings_pane.header.findChildren(QLabel)
            ]
            assert "Phase" in labels
            assert "Start time" in labels
            assert "Duration" in labels
            assert panel.timings_pane.axis_label.text().startswith("Start ")
        finally:
            load_language(qapp, "zh_CN")

    def test_zero_phases_hidden(self, qapp):
        """没走过的阶段（明文 HTTP 无 TLS）不出行——不拿 0 伪装成很快。"""
        from app.ui.detail_panel import DetailPanel

        f = _timed_flow(time.time() - 1)
        f.server_conn.timestamp_tls_setup = None
        panel = DetailPanel()
        panel.show_flow(f)
        assert len(panel.timings_pane._rows) == 4

    def test_mock_flow_notes_explain_missing_phases(self, qapp):
        """mock 响应（无连接锚点、无响应时间戳）：有说明备注，
        不静默显示半截数据。"""
        from app.ui.detail_panel import DetailPanel

        f = tflow.tflow(resp=True)
        # 对齐真实 mock：request 钩子注入的响应没有 server_conn 与响应时间戳
        f.server_conn.timestamp_start = None
        f.server_conn.timestamp_tcp_setup = None
        f.server_conn.timestamp_tls_setup = None
        f.response.timestamp_start = None
        f.response.timestamp_end = None
        panel = DetailPanel()
        panel.show_flow(f)
        assert "mock" in panel.timings_pane.note_label.text()
        # 只剩「发送请求」一段，连接/TLS/等待/接收都不显示
        assert len(panel.timings_pane._rows) == 1

    def test_pending_flow_notes_waiting(self, qapp):
        """响应未返回：备注说明「等待/接收」暂缺。"""
        from app.ui.detail_panel import DetailPanel

        f = tflow.tflow(resp=False)
        panel = DetailPanel()
        panel.show_flow(f)
        assert "尚未返回" in panel.timings_pane.note_label.text()

    def test_clear_hides_tab(self, qapp):
        from app.ui.detail_panel import DetailPanel

        panel = DetailPanel()
        panel.show_flow(_timed_flow(time.time() - 1))
        assert panel.tabs.isTabVisible(panel.timings_index)
        panel.clear()
        assert not panel.tabs.isTabVisible(panel.timings_index)
        assert panel.timings_pane._rows == []

    def test_phase_labels_translate_in_english(self, qapp):
        """新页面必须中英俱全：en 模式下分段名是英文。"""
        from PySide6.QtCore import QCoreApplication

        from app.i18n import load_language
        from app.ui.detail_panel import PHASE_LABELS, DetailPanel

        load_language(qapp, "en")
        try:
            panel = DetailPanel()
            panel.show_flow(_timed_flow(time.time() - 1))
            labels = [row["name"].text() for row in panel.timings_pane._rows]
            assert "TLS handshake" in labels
            assert "Waiting for response (TTFB)" in labels
            # 上下文命中：直接 translate 也应拿到同一译文
            assert QCoreApplication.translate(
                "TimingsPane", PHASE_LABELS["wait"]
            ) == "Waiting for response (TTFB)"
        finally:
            load_language(qapp, "zh_CN")
