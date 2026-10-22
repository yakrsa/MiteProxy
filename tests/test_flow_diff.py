"""两条会话对比（FlowDiffDialog）测试。"""

import pytest
from PySide6.QtWidgets import QApplication

from app.ui.flow_diff_dialog import FlowDiffDialog
from app.ui.main_window import MainWindow


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    win = MainWindow(restore_prompt=False)
    yield win
    win.close()


def _flow(url="http://x.test/api", body=b'{"a": 1, "b": 2}', status=200):
    from mitmproxy.test import tflow

    flow = tflow.tflow(resp=True)
    flow.request.url = url
    flow.response.status_code = status
    if body is not None:
        flow.response.content = body
    return flow


def _dialog(flow_a, flow_b):
    return FlowDiffDialog(flow_a, flow_b)


# ---------------------------------------------------------------- 报告内容


def test_identical_flows_report_no_difference(qapp):
    a = _flow()
    b = _flow()
    dlg = _dialog(a, b)
    assert dlg.report_text == ""
    assert "完全一致" in dlg.summary_label.text()


def test_json_body_diff_uses_structured_report(qapp):
    a = _flow(body=b'{"a": 1, "b": 2}')
    b = _flow(body=b'{"a": 1, "b": 3, "c": 4}')
    dlg = _dialog(a, b)
    report = dlg.report_text
    assert "【Body】" in report
    assert "$.b" in report            # 键级 diff 标出变化的字段
    assert "+ $.c = 4" in report      # 新增字段
    assert "JSON 键级" in dlg.summary_label.text()


def test_status_and_headers_diff_in_report(qapp):
    a = _flow(status=200)
    b = _flow(status=500)
    a.response.headers["x-tag"] = "one"
    b.response.headers["x-tag"] = "two"
    dlg = _dialog(a, b)
    report = dlg.report_text
    assert "【响应状态行】" in report
    assert "200" in report and "500" in report
    assert "【响应 Headers】" in report
    assert "x-tag" in report


def test_request_line_diff_in_report(qapp):
    a = _flow(url="http://x.test/api/a")
    b = _flow(url="http://x.test/api/b", status=200)
    b.request.method = "POST"
    dlg = _dialog(a, b)
    report = dlg.report_text
    assert "【请求行】" in report
    assert "方法: GET → POST" in report
    assert "/api/a" in report and "/api/b" in report


def test_text_body_diff_fallback(qapp):
    a = _flow(body=b"line1\nline2\n")
    b = _flow(body=b"line1\nline2-changed\n")
    dlg = _dialog(a, b)
    report = dlg.report_text
    assert "【Body】" in report
    assert "-line2" in report and "+line2-changed" in report


def test_binary_body_only_reports_difference(qapp):
    a = _flow(body=b"\x00\x01\x02\xff")
    b = _flow(body=b"\x00\x01\x03\xff")
    a.response.headers["content-type"] = "application/octet-stream"
    b.response.headers["content-type"] = "application/octet-stream"
    dlg = _dialog(a, b)
    assert "仅确认两者不同" in dlg.report_text
    assert "二进制内容不同" in dlg.summary_label.text()


def test_missing_response_on_one_side(qapp):
    a = _flow()
    b = _flow()
    b.response = None
    dlg = _dialog(a, b)
    assert "一边有响应、一边没有" in dlg.report_text


# ---------------------------------------------------------------- 主窗口接线


def _diff_action(menu):
    return next(a for a in menu.actions() if "对比两条会话" in a.text())


def test_context_menu_diff_enabled_with_two(window, monkeypatch):
    flows = [_flow(), _flow()]
    menu = window._build_table_context_menu(flows)
    assert _diff_action(menu).isEnabled()


def test_context_menu_diff_disabled_with_one_or_three(window):
    one = [_flow()]
    three = [_flow(), _flow(), _flow()]
    assert not _diff_action(window._build_table_context_menu(one)).isEnabled()
    assert not _diff_action(window._build_table_context_menu(three)).isEnabled()


def test_open_flow_diff_opens_dialog(window, monkeypatch):
    flows = [_flow(), _flow()]
    window._open_flow_diff(flows[0], flows[1])
    assert len(window._diff_dialogs) == 1
    dialog = window._diff_dialogs[0]
    assert dialog.isVisible() or not dialog.isHidden()
    # 关闭后引用被清掉（不会无限攒对话框）
    dialog.close()
    assert window._diff_dialogs == []
