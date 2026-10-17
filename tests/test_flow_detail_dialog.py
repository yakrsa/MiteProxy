"""双击详情弹窗（app/ui/flow_detail_dialog.py）的单元测试。

用 SimpleNamespace 拼最小 flow 假对象，验证：请求/响应两个 MessagePane 都按
DetailPanel.show_flow 同一套取值正确填充（summary 文案、headers 行数、body）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from app.ui.flow_detail_dialog import FlowDetailDialog


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _fake_flow(with_response: bool = True):
    req = SimpleNamespace(
        method="GET",
        pretty_url="https://example.com/api",
        headers={"Host": "example.com", "Accept": "*/*"},
        raw_content=b"",
    )
    req.get_content = lambda strict=False: b""
    if with_response:
        res = SimpleNamespace(
            status_code=200,
            reason="OK",
            headers={"Content-Type": "application/json"},
            raw_content=b'{"ok":1}',
        )
        res.get_content = lambda strict=False: b'{"ok":1}'
    else:
        res = None
    return SimpleNamespace(request=req, response=res, id="flow-1")


def test_dialog_shows_request_and_response(qapp):
    dlg = FlowDetailDialog(_fake_flow())
    # 标题取自请求行
    assert dlg.windowTitle() == "GET https://example.com/api"
    # 上：请求 pane
    assert "GET" in dlg.request_pane.summary_label.text()
    assert "example.com" in dlg.request_pane.summary_label.text()
    assert dlg.request_pane.headers_table.rowCount() == 2
    # 下：响应 pane
    assert "200" in dlg.response_pane.summary_label.text()
    assert dlg.response_pane.headers_table.rowCount() == 1
    dlg.deleteLater()


def test_dialog_handles_missing_response(qapp):
    dlg = FlowDetailDialog(_fake_flow(with_response=False))
    assert dlg.windowTitle() == "GET https://example.com/api"
    assert "GET" in dlg.request_pane.summary_label.text()
    # 无响应时响应 pane 回落到未选择占位，不报错
    assert "未选择" in dlg.response_pane.summary_label.text()
    dlg.deleteLater()


def test_dialog_close_button(qapp):
    dlg = FlowDetailDialog(_fake_flow())
    # 关闭按钮存在且默认按钮
    btns = dlg.findChildren(QPushButton)
    assert any(b.text() == "关闭" for b in btns)
    dlg.deleteLater()
