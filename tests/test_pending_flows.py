"""pending 流程可见性（请求一发出就入列，响应回来再原地补完）。

- CaptureAddon.request → on_flow（append，pending 行）
- CaptureAddon.response → on_update（update，按 id 原地替换，不重复）
- FlowStore.append 后再 update 同一 id 仍是 1 行
- pending 详情弹窗响应半边显示「尚未收到响应…」占位
"""

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from addons.capture import CaptureAddon
from app.ui.flow_detail_dialog import FlowDetailDialog
from app.ui.flow_store import FlowStore


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _pending_flow(flow_id="p1"):
    req = SimpleNamespace(
        method="GET",
        pretty_url="https://example.com/api",
        scheme="https",
        pretty_host="example.com",
        path="/api",
        timestamp_start=1.0,
        raw_content=b"",
        headers={"Host": "example.com"},
    )
    req.get_content = lambda strict=False: b""
    return SimpleNamespace(
        id=flow_id,
        request=req,
        response=None,
        websocket=None,
        metadata={},
        marked="",
        is_replay=False,
        comment="",
    )


def _completed_flow(flow_id="p1"):
    flow = _pending_flow(flow_id)
    res = SimpleNamespace(
        status_code=200,
        reason="OK",
        headers={"Content-Type": "application/json"},
        raw_content=b'{"ok":1}',
    )
    flow.response = res
    return flow


def test_request_hook_emits_pending_via_on_flow():
    seen = []
    addon = CaptureAddon(
        on_flow=lambda s: seen.append(s),
        on_update=lambda s: seen.append(("upd", s)),
    )
    addon.request(_pending_flow())
    # 只有一条、且走 on_flow 通道、状态为 0（pending）
    assert len(seen) == 1
    assert seen[0]["id"] == "p1"
    assert seen[0]["status"] == 0


def test_response_hook_emits_via_on_update():
    seen = []
    addon = CaptureAddon(
        on_flow=lambda s: seen.append(("new", s)),
        on_update=lambda s: seen.append(("upd", s)),
    )
    addon.response(_completed_flow())
    assert seen == [("upd", seen[0][1])]
    assert seen[0][1]["status"] == 200


def test_request_then_response_no_duplicate_row(qapp):
    store = FlowStore()
    # request 阶段 append 一行 pending
    store.append(CaptureAddon.summarize(_pending_flow()))
    assert len(store.rows) == 1
    # response 阶段 update 同一 id，应原地替换而非新增
    store.update(CaptureAddon.summarize(_completed_flow()))
    assert len(store.rows) == 1
    assert store.rows[0]["status"] == 200


def test_pending_dialog_shows_response_placeholder(qapp):
    dlg = FlowDetailDialog(_pending_flow())
    assert "GET" in dlg.request_pane.summary_label.text()
    assert "尚未收到响应" in dlg.response_pane.summary_label.text()
    dlg.deleteLater()
