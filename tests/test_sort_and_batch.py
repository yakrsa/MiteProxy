"""列表排序 + 多选批量导出（本轮新增功能）。

排序的两条硬要求：
1. 「大小」「耗时」「状态」按**原始数值**排，不能按 `4.2 KB` 这种格式化文本排；
2. 不排序时保持抓包到达顺序（表头指示器为 -1）。
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-sort-test-home")

import pytest

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


from app.export import (  # noqa: E402
    FORMAT_BODY,
    FORMAT_HAR,
    FORMAT_RAW,
    FORMAT_RESPONSE,
    SINGLE_ONLY_FORMATS,
    as_flow_list,
    build_curl_many,
    build_har,
    build_raw,
    build_response,
    default_filename,
    export_bytes,
    session_banner,
)
from app.ui.filter_model import FlowFilterProxyModel  # noqa: E402
from app.ui.flow_store import COL_DURATION, COL_RESP_SIZE, COL_STATUS, FlowStore  # noqa: E402
from app.ui.traffic_table import TrafficTable  # noqa: E402


def _row(**kw):
    base = {
        "id": kw.get("id", "f1"),
        "method": "GET",
        "scheme": "https",
        "host": "api.example.com",
        "server_ip": "127.0.0.1",
        "path": "/v1/user",
        "url": "https://api.example.com/v1/user",
        "status": 200,
        "size": 100,
        "duration_ms": 1.0,
        "content_type": "application/json",
        "marked": "",
        "is_replay": False,
        "timestamp": 0.0,
        "is_connect": False,
    }
    base.update(kw)
    return base


def _store(rows):
    store = FlowStore()
    for r in rows:
        store.append(r)
    return store


def _proxy(store):
    p = FlowFilterProxyModel()
    p.setSourceModel(store)
    return p


def _order(proxy, col=0):
    return [proxy.data(proxy.index(i, col), Qt.ItemDataRole.DisplayRole)
            for i in range(proxy.rowCount())]


class TestSortRole:
    def test_size_sorted_by_bytes_not_display_text(self):
        """`1.3 MB` 必须排在 `812 B` 之后（按文本排会反过来）。"""
        store = _store([
            _row(id="a", size=1_363_148),   # 1.3 MB
            _row(id="b", size=812),         # 812 B
            _row(id="c", size=4_300),       # 4.2 KB
        ])
        proxy = _proxy(store)
        proxy.sort(COL_RESP_SIZE, Qt.SortOrder.AscendingOrder)
        assert _order(proxy, COL_RESP_SIZE) == ["812 B", "4.2 KB", "1.3 MB"]
        proxy.sort(COL_RESP_SIZE, Qt.SortOrder.DescendingOrder)
        assert _order(proxy, COL_RESP_SIZE)[0] == "1.3 MB"

    def test_duration_numeric_not_string(self):
        """按字符串排 `9.0` 会排到 `10.0` 后面。"""
        store = _store([
            _row(id="a", duration_ms=10.0),
            _row(id="b", duration_ms=9.0),
            _row(id="c", duration_ms=100.0),
        ])
        proxy = _proxy(store)
        proxy.sort(COL_DURATION, Qt.SortOrder.AscendingOrder)
        assert _order(proxy, COL_DURATION) == [9.0, 10.0, 100.0]

    def test_status_numeric_and_zero_first(self):
        store = _store([
            _row(id="a", status=503),
            _row(id="b", status=200),
            _row(id="c", status=0),        # 无响应 → 显示 -
            _row(id="d", status=404),
        ])
        proxy = _proxy(store)
        proxy.sort(COL_STATUS, Qt.SortOrder.AscendingOrder)
        assert _order(proxy, COL_STATUS) == ["-", 200, 404, 503]
        proxy.sort(COL_STATUS, Qt.SortOrder.DescendingOrder)
        assert _order(proxy, COL_STATUS)[0] == 503

    def test_sort_keeps_arrival_ordinal_in_first_column(self):
        """排序后 `#` 仍是抓包到达序号（源行号 + 1），便于按序号回查。"""
        store = _store([_row(id="a", size=900), _row(id="b", size=100)])
        proxy = _proxy(store)
        proxy.sort(COL_RESP_SIZE, Qt.SortOrder.AscendingOrder)
        assert _order(proxy, 0) == [2, 1]          # b 是第 2 条到达，排在最前
        assert _order(proxy, COL_RESP_SIZE) == ["100 B", "900 B"]

    def test_empty_server_ip_first_in_ascending(self):
        store = _store([
            _row(id="a", server_ip=""),
            _row(id="b", server_ip="10.0.0.1"),
        ])
        proxy = _proxy(store)
        proxy.sort(3, Qt.SortOrder.AscendingOrder)
        assert _order(proxy, 3) == ["-", "10.0.0.1"]

    def test_mixed_types_do_not_raise(self):
        """不同列混排时 lessThan 不能抛 TypeError（防御性用例）。"""
        store = _store([_row(id="a"), _row(id="b", marked="MOCK:x")])
        proxy = _proxy(store)
        left = store.index(0, COL_STATUS)
        right = store.index(1, 8)             # 标记列是字符串
        assert proxy.lessThan(left, right) in (True, False)


class TestTrafficTableSorting:
    def test_multiselect_enabled(self):
        from PySide6.QtWidgets import QAbstractItemView
        table = TrafficTable()
        assert table.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection

    def test_starts_unsorted_then_sorts(self):
        table = TrafficTable()
        proxy = _proxy(_store([_row(id="a", size=900), _row(id="b", size=100)]))
        table.setModel(proxy)
        assert table.is_sorted() is False
        assert _order(proxy, COL_RESP_SIZE) == ["900 B", "100 B"]   # 到达顺序
        # 真实交互路径：点表头 → 指示器 + 排序同时发生
        table.sortByColumn(COL_RESP_SIZE, Qt.SortOrder.AscendingOrder)
        assert _order(proxy, COL_RESP_SIZE) == ["100 B", "900 B"]
        assert table.is_sorted() is True
        # 再点一次反向
        table.sortByColumn(COL_RESP_SIZE, Qt.SortOrder.DescendingOrder)
        assert _order(proxy, COL_RESP_SIZE) == ["900 B", "100 B"]

    def test_new_rows_land_in_sorted_position(self):
        """排序后继续抓包，新行插入到正确位置（dynamicSortFilter）。"""
        store = _store([_row(id="a", size=900), _row(id="b", size=100)])
        proxy = _proxy(store)
        proxy.sort(COL_RESP_SIZE, Qt.SortOrder.AscendingOrder)
        store.append(_row(id="c", size=300))
        assert _order(proxy, COL_RESP_SIZE) == ["100 B", "300 B", "900 B"]


class TestBatchExport:
    def _flows(self):
        from mitmproxy.http import HTTPFlow, Request, Response

        out = []
        for i in range(3):
            req = Request.make("GET", f"https://api.example.com/v1/item/{i}", headers={"Host": "api.example.com"})
            res = Response.make(200, content=f'{{"n":{i}}}'.encode(), headers={"Content-Type": "application/json"})
            flow = HTTPFlow(client_conn=None, server_conn=None)
            flow.request = req
            flow.response = res
            out.append(flow)
        return out

    def test_as_flow_list_normalizes(self):
        flow = self._flows()[0]
        assert as_flow_list(None) == []
        assert as_flow_list(flow) == [flow]
        assert as_flow_list([flow, None]) == [flow]

    def test_har_multi_entries(self):
        flows = self._flows()
        doc = build_har(flows)
        entries = doc["log"]["entries"]
        assert len(entries) == 3
        assert [e["response"]["content"]["text"] for e in entries] == [
            '{"n":0}', '{"n":1}', '{"n":2}',
        ]

    def test_har_single_is_one_entry(self):
        assert len(build_har(self._flows()[0])["log"]["entries"]) == 1

    def test_raw_multi_has_banners(self):
        flows = self._flows()
        text = build_raw(flows)
        assert "########## 会话 1/3 · GET https://api.example.com/v1/item/0 ##########" in text
        assert "########## 会话 3/3" in text
        assert text.count("===== 响应 =====") == 3

    def test_raw_single_unchanged(self):
        """单条输出不带 banner，保持与旧行为逐字一致。"""
        text = build_raw(self._flows()[0])
        assert "##########" not in text
        assert text.startswith("===== 请求 =====\n")

    def test_response_multi_sections(self):
        data = build_response(self._flows()[:2])
        assert data.count(b"HTTP/1.1 200 OK") == 2
        assert b"########## \xe4\xbc\x9a\xe8\xaf\x9d 2/2" in data

    def test_response_single_unchanged(self):
        assert build_response(self._flows()[0]).startswith(b"HTTP/1.1 200 OK")

    def test_body_rejects_multi(self):
        with pytest.raises(ValueError):
            export_bytes(self._flows(), FORMAT_BODY)

    def test_body_single_ok(self):
        assert export_bytes(self._flows()[0], FORMAT_BODY) == b'{"n":0}'

    def test_body_in_single_only_formats(self):
        assert FORMAT_BODY in SINGLE_ONLY_FORMATS
        assert FORMAT_HAR not in SINGLE_ONLY_FORMATS

    def test_export_bytes_all_formats_multi(self):
        flows = self._flows()
        assert len(__import__("json").loads(export_bytes(flows, FORMAT_HAR))["log"]["entries"]) == 3
        assert export_bytes(flows, FORMAT_RAW).count(b"===== \xe5\x93\x8d\xe5\xba\x94 =====") == 3
        assert export_bytes(flows, FORMAT_RESPONSE).count(b"HTTP/1.1 200 OK") == 3

    def test_default_filename_marks_count(self):
        flows = self._flows()
        assert default_filename(flows, FORMAT_HAR) == "api.example.com_v1_item_0_3条.har"
        assert default_filename(flows[0], FORMAT_HAR) == "api.example.com_v1_item_0.har"

    def test_session_banner(self):
        assert session_banner(2, 5, self._flows()[0]) == (
            "########## 会话 2/5 · GET https://api.example.com/v1/item/0 ##########"
        )


class TestBatchCurl:
    def _flows(self):
        return TestBatchExport()._flows()

    def test_single_unchanged(self):
        line = build_curl_many(self._flows()[:1])
        assert "\n" not in line
        assert line.startswith("curl 'https://api.example.com/v1/item/0'")

    def test_multi_has_comment_header_per_session(self):
        text = build_curl_many(self._flows())
        lines = text.splitlines()
        assert lines[0].startswith("# 会话 1/3 · GET https://api.example.com/v1/item/0")
        assert lines[1].startswith("curl ")
        assert sum(1 for ln in lines if ln.startswith("curl ")) == 3
        assert sum(1 for ln in lines if ln.startswith("# ")) == 3

    def test_cmd_style_uses_rem(self):
        text = build_curl_many(self._flows(), style="cmd")
        assert text.startswith("REM 会话 1/3")
        assert 'curl "https://api.example.com/v1/item/0"' in text

    def test_empty_list(self):
        assert build_curl_many([]) == ""
