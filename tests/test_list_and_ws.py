"""列表行为（自动滚动 / 顺序）+ WebSocket 捕获接线（offscreen Qt）。

盯几件容易出错的事：
1. 行内更新（WebSocket 消息）不能新增行、不能丢排序；
2. 顺序设置要落到排序指示器上，倒序 = 最新在最上面；
3. 自动滚动只在"用户停在最新端 + 按到达顺序排"时才动滚动条；
4. WS 摘要的体积/耗时口径（101 响应没 body，得按消息体算）。
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-list-ws-test-home")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

_app = None


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


from addons.capture import CaptureAddon  # noqa: E402
from app.settings import Settings, load_settings, save_settings  # noqa: E402
from app.ui.flow_store import COL_ID, COL_MARK, COL_SIZE, FlowStore  # noqa: E402
from app.ui.signals import FlowBridge  # noqa: E402


# ====================================================================== 行内更新


def _summary(flow_id, **extra):
    base = {
        "id": flow_id,
        "method": "GET",
        "scheme": "http",
        "host": "x.test",
        "server_ip": "127.0.0.1",
        "path": "/a",
        "url": "http://x.test/a",
        "status": 200,
        "size": 10,
        "duration_ms": 1.0,
        "content_type": "text/plain",
        "marked": "",
        "is_replay": False,
        "timestamp": 1.0,
        "is_connect": False,
        "is_websocket": False,
        "ws_messages": 0,
        "ws_closed": False,
    }
    base.update(extra)
    return base


class TestFlowStoreUpdate:
    def test_update_replaces_in_place(self):
        store = FlowStore()
        store.append(_summary("f1"))
        store.append(_summary("f2"))
        assert store.update(_summary("f1", size=999, ws_messages=3)) is True
        assert store.rowCount() == 2                       # 没有新增行
        assert store.row_data(0)["size"] == 999
        assert store.row_data(1)["size"] == 10

    def test_update_unknown_id_is_noop(self):
        store = FlowStore()
        store.append(_summary("f1"))
        assert store.update(_summary("nope")) is False
        assert store.rowCount() == 1

    def test_update_emits_data_changed(self):
        store = FlowStore()
        store.append(_summary("f1"))
        seen = []
        store.dataChanged.connect(lambda a, b, *_: seen.append(a.row()))
        store.update(_summary("f1", size=5))
        assert seen == [0]

    def test_websocket_badge_shows_message_count(self):
        store = FlowStore()
        store.append(_summary("f1", is_websocket=True, ws_messages=7))
        text = store.data(store.index(0, COL_MARK), Qt.ItemDataRole.DisplayRole)
        assert text == "WS 7"

    def test_websocket_tooltip(self):
        store = FlowStore()
        store.append(_summary("f1", is_websocket=True, ws_messages=2))
        tip = store.data(store.index(0, COL_ID), Qt.ItemDataRole.ToolTipRole)
        assert "WebSocket：2 条消息" in tip
        assert "连接中" in tip

    def test_closed_websocket_tooltip(self):
        store = FlowStore()
        store.append(
            _summary("f1", is_websocket=True, ws_messages=2, ws_closed=True)
        )
        tip = store.data(store.index(0, COL_ID), Qt.ItemDataRole.ToolTipRole)
        assert "已关闭" in tip

    def test_replay_badge_still_works(self):
        store = FlowStore()
        store.append(_summary("f1", is_replay=True))
        assert store.data(
            store.index(0, COL_MARK), Qt.ItemDataRole.DisplayRole
        ) == "REPLAY"


# ====================================================================== WS 摘要


class _Msg:
    def __init__(self, content: bytes, from_client=True):
        self.content = content
        self.from_client = from_client


class _WsData:
    def __init__(self, messages, timestamp_end=None, close_code=None):
        self.messages = messages
        self.timestamp_end = timestamp_end
        self.close_code = close_code
        self.close_reason = ""
        self.closed_by_client = False


class _Req:
    method = "GET"
    scheme = "http"
    pretty_host = "x.test"
    path = "/ws"
    pretty_url = "ws://x.test/ws"
    timestamp_start = 100.0

    def __init__(self):
        self.headers = {}


class _Res:
    status_code = 101
    raw_content = b""
    timestamp_end = 100.5

    def __init__(self):
        self.headers = {"content-type": "text/plain"}


class _WsFlow:
    id = "wf1"

    def __init__(self, messages, timestamp_end=None):
        self.request = _Req()
        self.response = _Res()
        self.websocket = _WsData(messages, timestamp_end)
        self.server_conn = None


class _HttpFlow:
    id = "hf1"

    def __init__(self):
        self.request = _Req()
        self.response = _Res()
        self.response.status_code = 200
        self.response.raw_content = b"x" * 64
        self.websocket = None
        self.server_conn = None


class TestCaptureWebSocket:
    def test_handshake_row_is_marked(self):
        flow = _WsFlow([])
        s = CaptureAddon.summarize(flow)
        assert s["is_websocket"] is True
        assert s["status"] == 101
        assert s["ws_messages"] == 0

    def test_size_counts_message_payloads(self):
        """101 响应没有 body → 体积按消息体算，否则这一列永远是 0。"""
        flow = _WsFlow([_Msg(b"hello"), _Msg(b"world!")])
        s = CaptureAddon.summarize(flow)
        assert s["size"] == 11
        assert s["ws_messages"] == 2

    def test_duration_uses_connection_lifetime(self):
        flow = _WsFlow([_Msg(b"a")], timestamp_end=102.0)
        s = CaptureAddon.summarize(flow)
        assert s["duration_ms"] == pytest.approx(2000.0, abs=1.0)
        assert s["ws_closed"] is True

    def test_open_connection_not_closed(self):
        flow = _WsFlow([_Msg(b"a")])
        assert CaptureAddon.summarize(flow)["ws_closed"] is False

    def test_http_flow_unaffected(self):
        s = CaptureAddon.summarize(_HttpFlow())
        assert s["is_websocket"] is False
        assert s["size"] == 64
        assert s["status"] == 200

    def test_hooks_wire_to_update_callback(self):
        got = []
        addon = CaptureAddon(on_flow=lambda s: got.append(("new", s)),
                             on_update=lambda s: got.append(("upd", s)))
        flow = _WsFlow([])
        flow.websocket.messages.append(_Msg(b"a"))
        addon.websocket_message(flow)
        assert got[0][1]["ws_messages"] == 1
        assert got[0][1]["ws_closed"] is False      # 握手后还在连接中
        flow.websocket.timestamp_end = 102.0        # 对端关闭
        addon.websocket_end(flow)
        assert [kind for kind, _ in got] == ["upd", "upd"]
        assert got[-1][1]["ws_closed"] is True

    def test_websocket_flow_cached_for_detail_lookup(self):
        addon = CaptureAddon()
        flow = _WsFlow([_Msg(b"a")])
        addon.websocket_message(flow)
        assert addon.get_flow("wf1") is flow


# ====================================================================== 信号桥


class TestFlowBridge:
    def test_update_signal_carries_summary(self):
        bridge = FlowBridge()
        seen = []
        bridge.flow_updated.connect(seen.append)
        bridge.emit_flow_update({"id": "x"})
        assert seen == [{"id": "x"}]


# ====================================================================== 主窗口接线


@pytest.fixture()
def window(monkeypatch, tmp_path):
    from app import settings as settings_mod

    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    from app.ui.main_window import MainWindow

    win = MainWindow(restore_prompt=False)
    yield win
    win.close()


class TestListOrderAndScroll:
    def test_default_order_is_arrival(self, window):
        assert window.traffic_table.horizontalHeader().sortIndicatorSection() == -1

    def test_newest_first_sorts_by_id_desc(self, window):
        window.order_combo.setCurrentIndex(window.order_combo.findData(True))
        header = window.traffic_table.horizontalHeader()
        assert header.sortIndicatorSection() == COL_ID
        assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder

    def test_newest_first_puts_latest_on_top(self, window):
        window.order_combo.setCurrentIndex(window.order_combo.findData(True))
        for i in range(3):
            window.bridge.emit_flow(_summary(f"f{i}"))
        top = window.proxy_model.index(0, COL_ID).data()
        assert top == 3                       # 第 3 条（最新）在最上

    def test_arrival_order_puts_latest_at_bottom(self, window):
        for i in range(3):
            window.bridge.emit_flow(_summary(f"f{i}"))
        last = window.proxy_model.index(
            window.proxy_model.rowCount() - 1, COL_ID
        ).data()
        assert last == 3

    def test_order_persisted(self, window, tmp_path):
        from app import settings as settings_mod

        window.order_combo.setCurrentIndex(window.order_combo.findData(True))
        assert load_settings().newest_first is True
        assert settings_mod.SETTINGS_PATH.exists()

    def test_auto_scroll_persisted(self, window):
        window.auto_scroll_cb.setChecked(False)
        assert load_settings().auto_scroll is False

    def test_auto_scroll_follows_new_flow(self, window):
        window.settings.auto_scroll = True
        for i in range(5):
            window.bridge.emit_flow(_summary(f"f{i}"))
        # 列表没撑满视口时 at_bottom() 为真 → 会滚到最后一行
        assert window.traffic_table.at_bottom()

    def test_auto_scroll_does_not_fight_user(self, window):
        """用户手动按耗时排序后，自动滚动不该继续拽滚动条。"""
        window.settings.auto_scroll = True
        for i in range(30):
            window.bridge.emit_flow(_summary(f"f{i}", duration_ms=float(i)))
        window.traffic_table.sortByColumn(7, Qt.SortOrder.DescendingOrder)
        assert window._following_arrival() is False

    def test_body_wrap_persisted(self, window):
        from app.ui.detail_panel import BodyPane

        window.detail_panel.request_pane.body_pane.wrap_cb.setChecked(False)
        assert load_settings().body_wrap is False
        assert isinstance(window.detail_panel.request_pane.body_pane, BodyPane)


# ====================================================================== 设置往返


class TestSettingsRoundTrip:
    def test_new_fields_default(self):
        s = Settings()
        assert s.auto_scroll is True
        assert s.newest_first is False
        assert s.body_wrap is True

    def test_new_fields_roundtrip(self, tmp_path, monkeypatch):
        from app import settings as settings_mod

        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "s.json")
        s = Settings(auto_scroll=False, newest_first=True, body_wrap=False)
        save_settings(s)
        back = load_settings()
        assert (back.auto_scroll, back.newest_first, back.body_wrap) == (
            False, True, False,
        )

    def test_old_settings_file_still_loads(self, tmp_path, monkeypatch):
        """没有新字段的旧 settings.json 不能被判成损坏而丢掉全部设置。"""
        from app import settings as settings_mod

        path = tmp_path / "s.json"
        path.write_text('{"proxy_port": 9090, "max_flows": 200}', encoding="utf-8")
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
        s = load_settings()
        assert s.proxy_port == 9090
        assert s.max_flows == 200
        assert s.auto_scroll is True
