"""统计页 UI + 主窗口接线（offscreen Qt）。

聚合逻辑本身在 test_stats.py；这里盯三件只有 UI 才出的事：
1. 面板把聚合结果正确铺进各表格/卡片（空态、有数据、无响应行）；
2. 双击慢请求 → flow_activated 带出正确的 flow id；
3. 主窗口侧：统计范围跟随列表（删行不计入）、防抖/懒刷新、
   双击跳转会选中流量列表对应行。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-stats-panel-test-home")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

_app = None


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.stats_panel import StatsPanel  # noqa: E402


def _flows(count=4, host="x.test", status=200, duration_ms=50.0):
    from mitmproxy.test import tflow

    out = []
    for i in range(count):
        f = tflow.tflow(resp=True)
        f.request.url = f"http://{host}/api/{i}"
        f.request.method = "GET" if i % 2 == 0 else "POST"
        f.response.status_code = status if i else 500
        f.request.timestamp_start = 1000.0 + i
        f.response.timestamp_end = 1000.0 + i + duration_ms / 1000.0
        out.append(f)
    return out


def _panel(flows):
    panel = StatsPanel(flow_provider=lambda: list(flows))
    return panel


# ====================================================================== 面板


class TestPanel:
    def test_empty_provider_shows_placeholder(self):
        panel = _panel([])
        assert panel.hosts_table.rowCount() == 0
        assert panel.slow_table.rowCount() == 0
        assert panel._cards["cards"]["total"][0].text() == "0"
        assert panel._cards["cards"]["error_rate"][0].text() == "—"
        # 直方图空态：有提示文案、没有柱子
        assert panel.histogram._buckets == []
        assert panel.histogram._empty_text

    def test_tables_filled_from_aggregation(self):
        panel = _panel(_flows(count=4))
        assert panel.hosts_table.rowCount() == 1
        assert panel.hosts_table.item(0, 0).text() == "x.test"
        assert panel.hosts_table.item(0, 1).text() == "4"          # 请求数
        assert panel.hosts_table.item(0, 2).text() == "1"          # 错误数
        assert panel.status_table.rowCount() == 2                  # 200 + 500
        assert panel.method_table.rowCount() == 2                  # GET + POST
        assert panel.slow_table.rowCount() == 4
        assert panel._cards["cards"]["total"][0].text() == "4"
        assert panel._cards["cards"]["error_rate"][0].text() == "25.0%"

    def test_pending_flow_shows_hint_and_status_row(self):
        """没有响应的会话：状态表给「无响应」行 + 卡片下方出提示。"""
        flows = _flows(count=1)
        flows[0].response = None
        panel = _panel(flows)
        labels = [panel.status_table.item(r, 0).text()
                  for r in range(panel.status_table.rowCount())]
        assert "无响应" in labels
        assert not panel.pending_hint.isHidden()

    def test_slow_row_double_click_emits_flow_id(self):
        flows = _flows(count=3)
        panel = _panel(flows)
        got = []
        panel.flow_activated.connect(got.append)
        row = panel.slow_table.rowCount() - 1
        panel.slow_table.doubleClicked.emit(
            panel.slow_table.model().index(row, 0)
        )
        assert got and got[0] in {f.id for f in flows}

    def test_refresh_picks_up_new_flows(self):
        holder = []
        panel = StatsPanel(flow_provider=lambda: holder)
        assert panel._cards["cards"]["total"][0].text() == "0"
        holder.extend(_flows(count=2))
        panel.refresh()
        assert panel._cards["cards"]["total"][0].text() == "2"

    def test_provider_exception_is_survived(self):
        """flow_provider 抛异常不能把界面带崩（降级成空统计）。"""

        def boom():
            raise RuntimeError("dict changed size during iteration")

        panel = StatsPanel(flow_provider=boom)
        assert panel._cards["cards"]["total"][0].text() == "0"


# ====================================================================== 主窗口接线


@pytest.fixture()
def window():
    w = MainWindow(restore_prompt=False)
    yield w
    w.close()


class TestMainWindowWiring:
    def test_stats_tab_registered(self, window):
        titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert titles[-1] == "统计"
        assert window.tabs.widget(window.tabs.count() - 1) is window.stats_panel

    def test_stats_scope_follows_the_list(self, window):
        """统计范围 = 列表里的行：删掉的行不计入（与 MCP 全量快照刻意不同）。"""
        flows = _flows(count=3)
        for f in flows:
            window.capture.flows[f.id] = f
            window.flow_store.append(window.capture.summarize(f))
        assert len(window._stats_flows()) == 3
        window.flow_store.remove_ids([flows[0].id])
        remaining = window._stats_flows()
        assert [f.id for f in remaining] == [flows[1].id, flows[2].id]

    def test_refresh_only_when_tab_is_current(self, window):
        """别的页忙着时白算纯浪费；切回来由 currentChanged 补刷新。"""
        flows = _flows(count=2)
        for f in flows:
            window.capture.flows[f.id] = f
            window.flow_store.append(window.capture.summarize(f))
        window.tabs.setCurrentWidget(window.traffic_page)
        window._refresh_stats()
        assert window.stats_panel._cards["cards"]["total"][0].text() == "0"
        # 切到统计页 → 自动补一次
        window.tabs.setCurrentWidget(window.stats_panel)
        assert window.stats_panel._cards["cards"]["total"][0].text() == "2"

    def test_flow_arrival_triggers_debounced_refresh(self, window):
        window.tabs.setCurrentWidget(window.stats_panel)
        f = _flows(count=1)[0]
        window.capture.flows[f.id] = f
        window._on_flow_arrived(window.capture.summarize(f))
        # 防抖中：还没算
        assert window._stats_timer.isActive()
        window._stats_timer.stop()
        window._refresh_stats()
        assert window.stats_panel._cards["cards"]["total"][0].text() == "1"

    def test_clear_refreshes_stats(self, window):
        flows = _flows(count=2)
        for f in flows:
            window.capture.flows[f.id] = f
            window.flow_store.append(window.capture.summarize(f))
        window.tabs.setCurrentWidget(window.stats_panel)
        assert window.stats_panel._cards["cards"]["total"][0].text() == "2"
        window._on_clear()
        assert window.stats_panel._cards["cards"]["total"][0].text() == "0"

    def test_reveal_flow_selects_the_row(self, window):
        """统计页双击慢请求 → 流量列表切回来并选中对应行。"""
        flows = _flows(count=3)
        for f in flows:
            window.capture.flows[f.id] = f
            window.flow_store.append(window.capture.summarize(f))
        window.tabs.setCurrentWidget(window.stats_panel)
        window._reveal_flow(flows[2].id)
        assert window.tabs.currentWidget() is window.traffic_page
        selected = window._selected_flows()
        assert [f.id for f in selected] == [flows[2].id]
