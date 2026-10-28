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
    # 无响应（pending）时响应 pane 显示明确占位，不报错、不显示「未选择会话」
    assert "尚未收到响应" in dlg.response_pane.summary_label.text()
    dlg.deleteLater()


def test_dialog_close_button(qapp):
    dlg = FlowDetailDialog(_fake_flow())
    # 关闭按钮存在且默认按钮
    btns = dlg.findChildren(QPushButton)
    assert any(b.text() == "关闭" for b in btns)
    dlg.deleteLater()


def test_dialog_raw_pane_shows_full_message(qapp):
    # Raw 页（对齐 Fiddler Raw inspector）在双击弹窗里同样可用：首行带 HTTP 版本、
    # 含全部头与 body，与主面板 detail_panel 取值完全一致。
    flow = _fake_flow()
    flow.request.http_version = "HTTP/1.1"
    flow.response.http_version = "HTTP/1.1"
    dlg = FlowDetailDialog(flow)

    raw_req = dlg.request_pane.raw_pane.text.toPlainText()
    assert raw_req.startswith("GET https://example.com/api HTTP/1.1")
    assert "Host: example.com" in raw_req
    assert "Accept: */*" in raw_req

    raw_res = dlg.response_pane.raw_pane.text.toPlainText()
    assert raw_res.startswith("HTTP/1.1 200 OK")
    assert "Content-Type: application/json" in raw_res
    assert '{"ok":1}' in raw_res
    dlg.deleteLater()


# ---------------------------------------------------------------- 生命周期回归
#
# 以下用例锁的是 Windows 崩溃那次的根因，防止以后改回去：
# 每双击一次泄漏一整套隐藏对话框（大响应几百 MB），以及关闭后流式 QTimer
# 仍在往看不见的编辑器里写。两者叠加最终表现为「卡一下，然后进程无声退出」。


def _big_flow(size_mb: int = 8):
    """构造 body 远超 RENDER_TEXT_LIMIT 的 flow，保证走流式渲染路径。

    8MB 是刻意的：2MB 只需两个 tick 就渲染完，「渲染中途关闭」根本测不到。
    """
    body = b"A" * (size_mb * 1024 * 1024)
    flow = _fake_flow()
    flow.request.headers = {"Host": "example.com", "Content-Type": "text/plain"}
    flow.request.raw_content = body
    flow.request.get_content = lambda strict=False: body
    flow.response.headers = {"Content-Type": "text/plain"}
    flow.response.raw_content = body
    flow.response.get_content = lambda strict=False: body
    return flow


def _live_dialogs(qapp) -> list:
    return [w for w in qapp.topLevelWidgets() if isinstance(w, FlowDetailDialog)]


def _drain(qapp, rounds: int = 30) -> None:
    """推进事件循环，并真正执行 deleteLater。

    注意 ``processEvents()`` 默认**不处理** DeferredDelete 事件——不显式投递的话，
    WA_DeleteOnClose 的对象会一直挂着，断言「已回收」永远失败。
    """
    from PySide6.QtCore import QEvent

    for _ in range(rounds):
        qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_dialog_is_destroyed_after_close(qapp):
    """关闭即销毁：否则每双击一次就留下一整套隐藏对话框。"""
    dlg = FlowDetailDialog(_fake_flow())
    dlg.show()
    dlg.close()
    _drain(qapp)

    with pytest.raises(RuntimeError):
        dlg.objectName()          # 访问已删的 C++ 对象 → RuntimeError


def test_repeated_open_close_does_not_accumulate(qapp):
    """连续开关 5 次，不该剩下任何对话框实例。"""
    for _ in range(5):
        dlg = FlowDetailDialog(_fake_flow())
        dlg.show()
        _drain(qapp, 5)
        dlg.close()
        _drain(qapp, 10)

    assert _live_dialogs(qapp) == []


def test_close_stops_stream_timers(qapp):
    """大 body 正在流式渲染时关闭，定时器必须立刻停。

    停表要发生在 closeEvent 里（对象销毁之前），不能指望析构兜底——否则
    interval=0 的 timer 会继续往一个看不见的编辑器里把剩下几 MB 写完。
    """
    dlg = FlowDetailDialog(_big_flow())
    dlg.show()
    qapp.processEvents()          # 只推进一轮：8MB 这时候远没渲染完

    raw_panes = [dlg.request_pane.raw_pane, dlg.response_pane.raw_pane]
    assert any(p._timer.isActive() for p in raw_panes), "大 body 应走流式渲染"

    dlg.close()               # 只 close，先不给 deleteLater 执行机会
    for pane in raw_panes:
        assert not pane._timer.isActive()
        assert pane._active is False
    for body_pane in (dlg.request_pane.body_pane, dlg.response_pane.body_pane):
        assert not body_pane._stream_timer.isActive()
        assert body_pane._stream_active is False

    _drain(qapp)


def test_exec_returns_and_dialog_is_gone(qapp):
    """``exec()`` 搭配 WA_DeleteOnClose：返回后对象已删，调用方不得再访问。

    主窗口的 ``_open_flow_detail`` 正是这个用法——exec() 之后只记耗时，
    不碰 dlg。这个用例保证该约定成立，改动接口时能立刻发现。
    """
    from PySide6.QtCore import QTimer

    dlg = FlowDetailDialog(_fake_flow())
    QTimer.singleShot(0, dlg.reject)

    rc = dlg.exec()

    assert rc == 0
    with pytest.raises(RuntimeError):
        dlg.result()


def test_dialog_is_window_modal_not_application_modal(qapp):
    """应用模态会冻住整个进程（含拖出的浮窗），必须只锁父窗口。"""
    from PySide6.QtCore import Qt

    dlg = FlowDetailDialog(_fake_flow())
    assert dlg.windowModality() == Qt.WindowModality.WindowModal
    dlg.deleteLater()
