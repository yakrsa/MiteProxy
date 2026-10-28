"""崩溃诊断上报对话框（app.ui.crash_dialog）测试。

网络不发真请求：注入假 transport，经 finish_transport 回流。
"""

from __future__ import annotations

import pytest

from app import crashreport
from app import feedback as fb

pytest.importorskip("PySide6.QtWidgets")

from app.ui.crash_dialog import CrashReportDialog  # noqa: E402


@pytest.fixture()
def qapp():
    """本仓库没有 pytest-qt，各测试文件自备 QApplication 夹具。"""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


SUMMARY = {
    "detected_at": "2026-10-29T00:40:00",
    "started_at": "启动于 2026-10-28 20:40:11 pid=4321",
    "version": "3.0.1",
    "excerpt": "Windows fatal exception: access violation",
    "hang": "",
    "actions": ["20:42:58 open_detail | GET https://admin.yxzq.com/o?token=SECRET 8MB"],
    "prompted": False,
}


@pytest.fixture()
def dialog(qapp, tmp_path, monkeypatch):
    """隔离日志目录 + 注入假 transport，并记录发出去的请求。"""
    monkeypatch.setattr(crashreport, "_log_dir", lambda: tmp_path)
    sent: list[tuple[str, dict, dict]] = []
    dlg = CrashReportDialog(SUMMARY, transport=lambda u, d, h: sent.append((u, d, h)))
    dlg.sent = sent                   # 便于断言
    yield dlg
    dlg.deleteLater()


# ---------------------------------------------------------------- 预览

def test_preview_shows_body_on_open(dialog):
    preview = dialog.preview.toPlainText()
    assert "v3.0.1" in preview
    assert "崩溃" in preview
    assert "access violation" in preview


def test_preview_hides_token_by_default(dialog):
    """默认不带请求地址，所以 URL query 里的 token 也不能出现在预览里。"""
    assert "SECRET" not in dialog.preview.toPlainText()
    assert dialog.urls_check.isChecked() is False


def test_toggling_urls_reveals_domain_but_not_token(dialog):
    dialog.urls_check.setChecked(True)
    text = dialog.preview.toPlainText()
    assert "admin.yxzq.com" in text
    assert "SECRET" not in text        # 值一律抹掉，只留域名与参数名


def test_toggling_actions_removes_action_block(dialog):
    dialog.actions_check.setChecked(False)
    assert "最近操作" not in dialog.preview.toPlainText()


# ---------------------------------------------------------------- 发送

def test_send_uses_bug_label_and_auto_title(dialog):
    dialog._on_send()
    assert len(dialog.sent) == 1
    url, data, headers = dialog.sent[0]
    assert url == fb.ISSUES_API
    assert data["labels"] == ["bug"]
    assert data["title"].startswith("[自动上报]")
    assert "v3.0.1" in data["title"]
    assert headers["Authorization"].startswith("Bearer")


def test_send_disables_button_while_pending(dialog):
    dialog._on_send()
    assert dialog.send_btn.isEnabled() is False
    dialog._on_send()                 # 重复点击不该再发一单
    assert len(dialog.sent) == 1


def test_success_clears_pending_and_accepts(dialog, tmp_path):
    crashreport._pending_file().write_text('{"prompted": false}', encoding="utf-8")
    dialog._on_send()

    dialog.finish_transport(201, b'{"html_url": "https://github.com/x/y/issues/1"}')

    assert dialog.result() == CrashReportDialog.DialogCode.Accepted
    assert crashreport.pending_crash() is None
    assert "https://github.com/x/y/issues/1" in dialog.status_label.text()


def test_failure_keeps_dialog_and_reenables_button(dialog):
    dialog._on_send()
    dialog.finish_transport(401, b"")

    assert dialog.result() != CrashReportDialog.DialogCode.Accepted
    assert dialog.send_btn.isEnabled() is True
    # 对话框本身没 show()（测试里不需要真窗口），子控件 isVisible() 恒为 False，
    # 所以这里判「未被显式隐藏」而不是「可见」。
    assert dialog.status_label.isHidden() is False
    assert "401" in dialog.status_label.text() or "凭证" in dialog.status_label.text()


# ---------------------------------------------------------------- 结局分支

def test_mute_clears_pending_and_emits_signal(dialog):
    crashreport._pending_file().write_text('{"prompted": false}', encoding="utf-8")
    fired = []
    dialog.mute_requested.connect(lambda: fired.append(True))

    dialog._on_mute()

    assert fired == [True]
    assert crashreport.pending_crash() is None
    assert dialog.result() == CrashReportDialog.DialogCode.Rejected


def test_dismissing_marks_prompted_not_deleted(dialog):
    """「稍后再说」只标记已提示，摘要留着，可从菜单补发。"""
    crashreport._pending_file().write_text('{"prompted": false}', encoding="utf-8")

    dialog.reject()

    summary = crashreport.pending_crash()
    assert summary is not None
    assert summary["prompted"] is True


def test_dialog_survives_empty_summary(qapp, tmp_path, monkeypatch):
    """摘要是坏数据/空的时候也不能崩——它出现在启动路径上。"""
    monkeypatch.setattr(crashreport, "_log_dir", lambda: tmp_path)
    dlg = CrashReportDialog({}, transport=lambda *a: None)
    assert dlg.preview.toPlainText()
    dlg.deleteLater()
