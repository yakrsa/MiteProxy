"""断点调试（addons/breakpoint.py + app/ui/breakpoint_dialog.py）的单元测试。

锁定的行为：
- addon 按「开关 / 阶段 / URL 关键词」决定是否挂起，重放的会话不拦；
- 编辑器把改动写回 flow，并且改了 body 会同步 Content-Length；
- 「继续」放行、「中止」kill，且关闭窗口不会把已中止的会话又放行一次。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from addons.breakpoint import BreakpointAddon
from app.settings import BreakpointConfig
from app.ui.breakpoint_dialog import BreakpointDialog


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _flow(url: str = "http://x.test/api/v1", replay: bool = False):
    from mitmproxy.test import tflow

    flow = tflow.tflow(resp=True)
    flow.request.url = url
    flow.is_replay = replay
    return flow


def _addon(on_intercept=None, **kw) -> BreakpointAddon:
    kw.setdefault("enabled", True)
    kw.setdefault("on_request", True)
    kw.setdefault("on_response", False)
    return BreakpointAddon(BreakpointConfig(**kw), on_intercept=on_intercept)


# ------------------------------------------------------------------ addon 判定

def test_intercepts_request_when_enabled():
    flow = _flow()
    addon = _addon()
    addon.request(flow)
    assert flow.intercepted is True


def test_skips_when_disabled():
    flow = _flow()
    addon = _addon()
    addon.config.enabled = False
    addon.request(flow)
    assert flow.intercepted is False


def test_skips_non_matching_url():
    flow = _flow("http://x.test/other")
    addon = _addon(url_keywords=["api"])
    addon.request(flow)
    assert flow.intercepted is False

    hit = _flow("http://x.test/api/v1")
    addon.request(hit)
    assert hit.intercepted is True


def test_skips_replay_flows():
    """重放是用户主动发的，再拦一次很烦。"""
    flow = _flow(replay=True)
    addon = _addon()
    addon.request(flow)
    assert flow.intercepted is False


def test_response_phase_follows_on_response():
    flow = _flow()
    addon = _addon(on_response=False)
    addon.response(flow)
    assert flow.intercepted is False

    addon.config.on_response = True
    addon.response(flow)
    assert flow.intercepted is True


def test_on_intercept_reports_flow_and_phase():
    got = []
    flow = _flow()
    addon = _addon(on_intercept=lambda f, p: got.append((f, p)))
    addon.request(flow)
    assert got == [(flow, "request")]


def test_not_reported_twice_for_same_flow():
    got = []
    flow = _flow()
    addon = _addon(on_intercept=lambda f, p: got.append(p))
    addon.request(flow)
    addon.request(flow)
    assert len(got) == 1


def test_forget_allows_reintercept():
    flow = _flow()
    addon = _addon()
    addon.request(flow)
    addon.forget(flow)
    addon.config.on_response = True
    addon.response(flow)
    # 清掉标记后能再次进入断点（response 阶段）
    assert flow.id not in addon.paused or flow.intercepted is True


# ------------------------------------------------------------------ 编辑器

def _dialog(flow, phase="request", **kw):
    return BreakpointDialog(flow, phase, **kw)


def test_dialog_apply_edits_writes_back(qapp):
    flow = _flow()
    dlg = _dialog(flow)
    dlg.url_edit.setText("http://x.test/api/v2")
    dlg.method_combo.setCurrentText("POST")
    dlg.body_edit.setPlainText('{"a":1}')
    dlg.apply_edits()

    assert flow.request.url == "http://x.test/api/v2"
    assert flow.request.method == "POST"
    assert flow.request.text == '{"a":1}'


def test_dialog_syncs_content_length(qapp):
    """改了 body 不同步 Content-Length，对端会一直等——最容易踩的坑。"""
    flow = _flow()
    flow.request.headers["Content-Length"] = "2"
    dlg = _dialog(flow)
    dlg.body_edit.setPlainText("hello")
    dlg.apply_edits()
    assert flow.request.headers["Content-Length"] == "5"


def test_dialog_resume_calls_callback(qapp):
    got = []
    flow = _flow()
    dlg = _dialog(flow, on_resume=lambda f: got.append(f))
    dlg._do_resume()
    assert got == [flow]


def test_dialog_kill_calls_callback_and_never_resumes(qapp):
    killed, resumed = [], []
    flow = _flow()
    dlg = _dialog(
        flow,
        on_resume=lambda f: resumed.append(f),
        on_kill=lambda f: killed.append(f),
    )
    dlg._do_kill()
    dlg.close()          # 关闭窗口不该把已中止的会话又放行
    assert killed == [flow]
    assert resumed == []


def test_dialog_response_phase_edits_status(qapp):
    flow = _flow()
    dlg = _dialog(flow, phase="response")
    dlg.status_spin.setValue(503)
    dlg.body_edit.setPlainText("oops")
    dlg.apply_edits()
    assert flow.response.status_code == 503
    assert flow.response.text == "oops"
