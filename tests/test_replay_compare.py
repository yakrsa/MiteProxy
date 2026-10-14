"""重放并对比测试：CompareDialog 行为（offscreen Qt + tflow 造响应）。

对齐 Fiddler Compare：左右双栏 + 差异报告；JSON 走键级 diff，
非 JSON 走行级 diff，二进制只报同/不同。
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-compare-test-home")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.compare_dialog import CompareDialog, diff_headers  # noqa: E402


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _flow(url: str = "http://a.com/api/x", method: str = "GET", replay: bool = False):
    from mitmproxy.test import tflow

    flow = tflow.tflow(resp=True)
    flow.request.method = method
    flow.request.url = url
    if replay:
        flow.is_replay = True
    return flow


def _set_json(flow, obj: dict, status: int = 200) -> None:
    import json

    flow.response.status_code = status
    flow.response.headers["content-type"] = "application/json"
    flow.response.content = json.dumps(obj).encode("utf-8")


# ---------------------------------------------------------------- diff_headers


class TestDiffHeaders:
    def test_no_difference(self):
        items = [("a", "1"), ("b", "2")]
        assert diff_headers(items, items) == []

    def test_added_and_removed(self):
        old = [("keep", "1"), ("gone", "x")]
        new = [("keep", "1"), ("fresh", "y")]
        lines = diff_headers(old, new)
        assert "+ fresh: y" in lines
        assert "- gone: x" in lines

    def test_changed_value(self):
        lines = diff_headers([("ct", "a")], [("ct", "b")])
        assert lines == ["~ ct: a → b"]

    def test_multi_value_same_set_not_a_difference(self):
        old = [("set-cookie", "a=1"), ("set-cookie", "b=2")]
        new = [("set-cookie", "b=2"), ("set-cookie", "a=1")]
        assert diff_headers(old, new) == []

    def test_multi_value_changed(self):
        old = [("set-cookie", "a=1")]
        new = [("set-cookie", "a=2")]
        assert diff_headers(old, new) == ["~ set-cookie: a=1 → a=2"]


# ---------------------------------------------------------------- 对话框


class TestCompareDialog:
    def test_identical_json(self, qapp):
        old = _flow()
        new = _flow()
        _set_json(old, {"a": 1})
        _set_json(new, {"a": 1})
        dialog = CompareDialog(old, new)
        assert "完全一致" in dialog.summary_label.text()
        assert "两个响应完全一致" in dialog.report_text

    def test_json_structured_diff(self, qapp):
        old = _flow()
        new = _flow()
        _set_json(old, {"user": {"name": "tom", "age": 1}, "gone": True})
        _set_json(new, {"user": {"name": "jerry", "age": 1}, "added": 5})
        dialog = CompareDialog(old, new)
        assert "3 处差异（JSON 键级）" in dialog.summary_label.text()
        report = dialog.report_text
        assert '~ $.user.name: "tom" → "jerry"' in report
        assert "+ $.added = 5" in report
        assert "- $.gone = true" in report

    def test_status_change_shown_in_summary(self, qapp):
        old = _flow()
        new = _flow()
        _set_json(old, {"a": 1}, status=200)
        _set_json(new, {"a": 2}, status=500)
        dialog = CompareDialog(old, new)
        assert "200" in dialog.summary_label.text()
        assert "500" in dialog.summary_label.text()
        # 右栏展示的是新响应
        assert "500" in dialog.new_pane.summary_label.text()

    def test_headers_only_difference(self, qapp):
        old = _flow()
        new = _flow()
        _set_json(old, {"a": 1})
        _set_json(new, {"a": 1})
        new.response.headers["X-New"] = "yes"
        dialog = CompareDialog(old, new)
        assert "body 一致，headers 有差异" in dialog.summary_label.text()
        assert "+ X-New: yes" in dialog.report_text

    def test_text_diff_for_non_json(self, qapp):
        old = _flow()
        new = _flow()
        old.response.headers["content-type"] = "text/plain"
        old.response.content = b"line1\nline2\nline3"
        new.response.headers["content-type"] = "text/plain"
        new.response.content = b"line1\nLINE2\nline3"
        dialog = CompareDialog(old, new)
        assert "文本有差异" in dialog.summary_label.text()
        assert "-line2" in dialog.report_text
        assert "+LINE2" in dialog.report_text

    def test_binary_difference(self, qapp):
        old = _flow()
        new = _flow()
        old.response.headers["content-type"] = "application/octet-stream"
        old.response.content = bytes(range(256))
        new.response.headers["content-type"] = "application/octet-stream"
        new.response.content = bytes(range(255, -1, -1))
        dialog = CompareDialog(old, new)
        assert "二进制内容不同" in dialog.summary_label.text()
        assert "二进制" in dialog.report_text

    def test_missing_response_falls_back_to_request(self, qapp):
        old = _flow()
        new = _flow()
        new.response = None
        new.error = "connection refused"
        dialog = CompareDialog(old, new)
        # 新栏没有响应时展示请求而不是空白
        assert "无响应" in dialog.new_pane.summary_label.text()
        assert "无响应" in dialog.summary_label.text()

    def test_copy_button_copies_report(self, qapp):
        old = _flow()
        new = _flow()
        _set_json(old, {"a": 1})
        _set_json(new, {"a": 2})
        dialog = CompareDialog(old, new)
        dialog._copy_report()
        clipboard = QApplication.clipboard()
        assert clipboard.text() == dialog.report_text
        assert "$.a" in clipboard.text()


# ---------------------------------------------------------------- 主窗口接线


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    from app.ui.main_window import MainWindow

    win = MainWindow(restore_prompt=False)
    yield win
    win.close()


def _running_proxy(monkeypatch, proxy):
    """让 proxy.running 恒为 True（不真起代理线程）。"""
    monkeypatch.setattr(type(proxy), "running", property(lambda self: True))


class _FakeReplayDialog:
    """假编辑对话框：直接确认、不改请求。"""

    def __init__(self, request, parent=None, compare=False):
        self.compare = compare

    def exec(self):
        return True

    def result(self):
        return {"method": "GET", "url": "", "headers": None, "body": None}


class TestPendingCompare:
    def test_register_adds_pending_and_starts_timer(self, window):
        copy = _flow()
        window._register_pending_compare("origin-1", copy)
        assert len(window._pending_compare) == 1
        pending = window._pending_compare[0]
        assert pending["origin_id"] == "origin-1"
        assert pending["copy_id"] == copy.id
        assert pending["url"] == "http://a.com/api/x"
        assert window._compare_timer.isActive()

    def test_replay_copy_arrival_opens_dialog(self, window):
        original = _flow()
        new = _flow(replay=True)
        _set_json(original, {"a": 1})
        _set_json(new, {"a": 2}, status=500)
        window.capture.flows[original.id] = original
        window.capture.flows[new.id] = new
        window._register_pending_compare(original.id, new)

        window._on_flow_arrived(window.capture.summarize(new))

        assert window._pending_compare == []
        assert len(window._compare_dialogs) == 1
        dialog = window._compare_dialogs[0]
        assert "500" in dialog.summary_label.text()
        assert "1 处差异（JSON 键级）" in dialog.summary_label.text()
        # 新 flow 也进了流量列表
        assert window.flow_store.rowCount() == 1
        assert not window._compare_timer.isActive()

    def test_non_replay_summary_does_not_open(self, window):
        original = _flow()
        new = _flow()
        window.capture.flows[original.id] = original
        window.capture.flows[new.id] = new
        window._register_pending_compare(original.id, new)

        # 普通抓包 flow（is_replay=False）不该触发对比
        window._on_flow_arrived(window.capture.summarize(original))

        assert len(window._pending_compare) == 1
        assert window._compare_dialogs == []

    def test_unrelated_replay_does_not_open(self, window):
        original = _flow()
        new = _flow(replay=True)
        other = _flow(url="http://a.com/other", replay=True)
        window.capture.flows[original.id] = original
        window.capture.flows[new.id] = new
        window._register_pending_compare(original.id, new)

        # 是重放但 id 不匹配（别的来源的重放）
        window._on_flow_arrived(window.capture.summarize(other))

        assert len(window._pending_compare) == 1
        assert window._compare_dialogs == []

    def test_timeout_expires_pending(self, window):
        window._register_pending_compare("origin-1", _flow())
        # 把时间戳改到超时之前
        window._pending_compare[0]["at"] -= 30
        window._expire_pending_compare()
        assert window._pending_compare == []
        assert not window._compare_timer.isActive()
        assert "超时" in window.status_bar.currentMessage()

    def test_fresh_pending_survives_timer_tick(self, window):
        window._register_pending_compare("origin-1", _flow())
        window._expire_pending_compare()
        assert len(window._pending_compare) == 1
        assert window._compare_timer.isActive()

    def test_missing_flows_reports_failure(self, window):
        # 原会话/新会话都没进缓存（被淘汰）→ 提示而不崩
        window._register_pending_compare("gone-1", _flow())
        window._match_pending_compare(
            {"id": window._pending_compare[0]["copy_id"], "is_replay": True}
        )
        assert window._pending_compare == []
        assert window._compare_dialogs == []
        assert "对比失败" in window.status_bar.currentMessage()

    def test_dialog_keep_limit(self, window):
        for i in range(7):
            original = _flow(url=f"http://a.com/p{i}")
            new = _flow(url=f"http://a.com/p{i}", replay=True)
            window.capture.flows[original.id] = original
            window.capture.flows[new.id] = new
            window._register_pending_compare(original.id, new)
            window._match_pending_compare(window.capture.summarize(new))
        assert len(window._compare_dialogs) == 5


class TestReplayAndCompareEntry:
    def test_registers_pending_with_copy_id(self, window, monkeypatch):
        import app.ui.main_window as mw

        _running_proxy(monkeypatch, window.proxy)
        replayed = []
        monkeypatch.setattr(
            window.proxy, "replay_flow", lambda copy: replayed.append(copy) or True
        )
        monkeypatch.setattr(mw, "ReplayEditDialog", _FakeReplayDialog)
        flow = _flow()
        window.capture.flows[flow.id] = flow
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])

        window._replay_selected(edit=True, compare=True)

        assert len(window._pending_compare) == 1
        assert window._pending_compare[0]["origin_id"] == flow.id
        # copy id 与投入重放队列的副本一致（关联的锚点）
        assert window._pending_compare[0]["copy_id"] == replayed[0].id
        assert replayed[0].id != flow.id

    def test_cancelled_dialog_registers_nothing(self, window, monkeypatch):
        import app.ui.main_window as mw

        _running_proxy(monkeypatch, window.proxy)

        class _CancelDialog(_FakeReplayDialog):
            def exec(self):
                return False

        monkeypatch.setattr(mw, "ReplayEditDialog", _CancelDialog)
        flow = _flow()
        window.capture.flows[flow.id] = flow
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])

        window._replay_selected(edit=True, compare=True)
        assert window._pending_compare == []

    def test_plain_replay_does_not_register(self, window, monkeypatch):
        _running_proxy(monkeypatch, window.proxy)
        monkeypatch.setattr(window.proxy, "replay_flow", lambda copy: True)
        flow = _flow()
        window.capture.flows[flow.id] = flow
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])

        window._replay_selected(edit=False)
        assert window._pending_compare == []

    def test_proxy_not_running_no_pending(self, window, monkeypatch):
        import app.ui.main_window as mw

        monkeypatch.setattr(
            mw.QMessageBox, "information", staticmethod(lambda *a, **k: None)
        )
        flow = _flow()
        window.capture.flows[flow.id] = flow
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])

        window._replay_selected(edit=True, compare=True)
        assert window._pending_compare == []
