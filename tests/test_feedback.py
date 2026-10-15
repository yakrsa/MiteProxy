"""意见反馈测试（v1.15）：纯函数层 + 反馈对话框 UI + 菜单入口。

网络不发真实请求：UI 测试注入假 transport，经 finish_transport 回流。
"""

import json
from pathlib import Path

import pytest

from app import feedback as fb

pytest.importorskip("PySide6.QtWidgets")


# ---------------------------------------------------------------- 纯函数层

class TestPayloadAndHeaders:
    def test_payload_strips_title_and_sets_label(self):
        p = fb.payload("  标题  ", "正文")
        assert p["title"] == "标题"
        assert p["body"] == "正文"
        assert "feedback" in p["labels"]

    def test_payload_title_length_capped(self):
        p = fb.payload("x" * 500, "")
        assert len(p["title"]) == 200

    def test_headers_require_auth(self):
        h = fb.headers("tok123")
        assert h["Authorization"] == "Bearer tok123"
        assert "User-Agent" in h


class TestDiagnostics:
    def test_contains_version_and_os(self):
        diag = fb.collect_diagnostics()
        assert fb.APP_VERSION in diag
        import platform

        assert platform.system() in diag

    def test_body_merges_diag_in_code_block(self):
        body = fb.build_issue_body("反馈内容", "- App 版本: v1.15")
        assert body.startswith("反馈内容")
        assert "```text" in body and "- App 版本: v1.15" in body

    def test_body_without_diag_is_plain(self):
        assert fb.build_issue_body("内容", "") == "内容"
        assert fb.build_issue_body("  内容  ", "   ") == "内容"


class TestParseResponse:
    def test_created(self):
        raw = json.dumps({"html_url": "https://github.com/yakrsa/MiteProxy/issues/9"}).encode()
        ok, msg, url = fb.parse_issue_response(201, raw)
        assert ok and url.endswith("/issues/9")

    def test_created_with_bad_json_still_ok(self):
        ok, msg, url = fb.parse_issue_response(201, b"not-json")
        assert ok and url == ""

    def test_unauthorized(self):
        ok, msg, _ = fb.parse_issue_response(401, b"{}")
        assert not ok and "凭证" in msg

    def test_forbidden_rate_limit(self):
        ok, msg, _ = fb.parse_issue_response(403, b"", "rate limit exceeded")
        assert not ok and "限流" in msg

    def test_network_error_status_zero(self):
        ok, msg, _ = fb.parse_issue_response(0, b"", "timed out")
        assert not ok and "网络" in msg

    def test_server_error(self):
        ok, msg, _ = fb.parse_issue_response(502, b"")
        assert not ok and "502" in msg


class TestToken:
    def test_env_overrides_embedded(self, monkeypatch):
        monkeypatch.setenv(fb.TOKEN_ENV, "env-token")
        assert fb.get_token() == "env-token"

    def test_empty_env_falls_back_to_embedded(self, monkeypatch):
        monkeypatch.setenv(fb.TOKEN_ENV, "  ")
        assert fb.get_token() == fb.EMBEDDED_FEEDBACK_TOKEN

    def test_token_file_between_env_and_embedded(self, monkeypatch, tmp_path):
        token_file = tmp_path / "feedback_token"
        token_file.write_text("file-token\n")
        monkeypatch.setattr(fb, "TOKEN_FILE", token_file)
        assert fb.get_token() == "file-token"  # 无 env 时用文件
        monkeypatch.setenv(fb.TOKEN_ENV, "env-token")
        assert fb.get_token() == "env-token"  # env 优先

    def test_missing_token_file_falls_back(self, monkeypatch, tmp_path):
        monkeypatch.setattr(fb, "TOKEN_FILE", tmp_path / "nope")
        monkeypatch.delenv(fb.TOKEN_ENV, raising=False)
        assert fb.get_token() == fb.EMBEDDED_FEEDBACK_TOKEN


# ---------------------------------------------------------------- 对话框

class FakeTransport:
    """记录请求并允许测试手动回流结果。"""

    def __init__(self):
        self.calls: list[tuple[str, dict, dict]] = []

    def __call__(self, url: str, data: dict, headers: dict) -> None:
        self.calls.append((url, data, headers))


@pytest.fixture()
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def dialog(qapp, monkeypatch):
    monkeypatch.setenv(fb.TOKEN_ENV, "test-token")
    from app.ui.feedback_dialog import FeedbackDialog

    d = FeedbackDialog(transport=None)
    d._transport = FakeTransport()
    yield d
    d.deleteLater()


class TestFeedbackDialog:
    def test_diagnostics_shown_readonly(self, dialog):
        assert dialog.diag_view.isReadOnly()
        assert fb.APP_VERSION in dialog.diag_view.toPlainText()

    def test_empty_fields_rejected(self, dialog):
        dialog._on_submit()
        assert not dialog.status_label.isHidden()
        assert dialog._transport.calls == []  # 未发请求

    def test_submit_sends_payload_with_diag(self, dialog):
        dialog.title_edit.setText("崩溃")
        dialog.body_edit.setPlainText("启动就崩")
        dialog._on_submit()
        assert len(dialog._transport.calls) == 1
        url, data, headers = dialog._transport.calls[0]
        assert url == fb.ISSUES_API
        assert data["title"] == "崩溃"
        assert "启动就崩" in data["body"]
        assert "```text" in data["body"]
        assert headers["Authorization"] == "Bearer test-token"

    def test_success_flow_accepts(self, dialog, monkeypatch):
        # 吞掉结果弹窗
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(QMessageBox, "exec", lambda self: None)
        dialog.title_edit.setText("建议")
        dialog.body_edit.setPlainText("加个功能")
        dialog._on_submit()
        raw = json.dumps({"html_url": "https://github.com/yakrsa/MiteProxy/issues/7"}).encode()
        dialog.finish_transport(201, raw)
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_failure_shows_error_and_reenables(self, dialog):
        dialog.title_edit.setText("x")
        dialog.body_edit.setPlainText("y")
        dialog._on_submit()
        dialog.finish_transport(401, b"{}")
        assert not dialog.result() == dialog.DialogCode.Accepted
        assert dialog.submit_btn.isEnabled()
        assert "凭证" in dialog.status_label.text()

    def test_no_token_disables_submit(self, qapp, monkeypatch):
        monkeypatch.delenv(fb.TOKEN_ENV, raising=False)
        monkeypatch.setattr(fb, "EMBEDDED_FEEDBACK_TOKEN", "")
        # 本机可能存在 ~/.miteproxy/feedback_token（开发机联调用），一并屏蔽
        monkeypatch.setattr(fb, "TOKEN_FILE", Path("/nonexistent/feedback_token"))
        from app.ui.feedback_dialog import FeedbackDialog

        d = FeedbackDialog()
        assert not d.submit_btn.isEnabled()
        assert "issues/new" in d.status_label.text()
        d.deleteLater()


# ---------------------------------------------------------------- 菜单入口

class TestMenuEntry:
    @pytest.fixture()
    def window(self, qapp, tmp_path, monkeypatch):
        from app import settings as settings_mod
        from app.ui.main_window import MainWindow

        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
        win = MainWindow(restore_prompt=False)
        yield win
        win.proxy.stop()
        win.deleteLater()

    def test_help_menu_has_feedback_action(self, window):
        help_menu = None
        for action in window.menuBar().actions():
            if action.text() == "帮助":
                help_menu = action.menu()
                break
        assert help_menu is not None
        texts = [a.text() for a in help_menu.actions() if a.text()]
        assert "意见反馈…" in texts
