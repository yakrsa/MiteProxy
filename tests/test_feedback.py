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


class TestNickname:
    """昵称必填、≤64 字符，进 issue 标题（作者只能是 token 账号本人）。"""

    def test_title_prefixed_with_nickname(self):
        assert fb.build_issue_title("小明", "导入乱码") == "[小明] 导入乱码"

    def test_title_without_nickname(self):
        assert fb.build_issue_title("  ", "导入乱码") == "导入乱码"

    def test_nickname_truncated_to_64(self):
        title = fb.build_issue_title("昵" * 100, "x")
        assert title.startswith("[")
        assert title.index("]") <= fb.NICKNAME_MAX_LEN + 1

    def test_body_contains_nickname(self):
        body = fb.build_issue_body("内容", "", "user@example.com")
        assert "**反馈人：user@example.com**" in body
        assert body.index("反馈人") < body.index("内容")

    def test_dialog_maxlength(self, qapp):
        from app.ui.feedback_dialog import FeedbackDialog

        d = FeedbackDialog()
        assert d.nick_edit.maxLength() == fb.NICKNAME_MAX_LEN
        d.deleteLater()


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

    def test_missing_nickname_rejected(self, dialog):
        dialog.title_edit.setText("崩溃")
        dialog.body_edit.setPlainText("启动就崩")
        dialog._on_submit()  # 昵称未填
        assert dialog._transport.calls == []
        assert "昵称" in dialog.status_label.text()

    def test_submit_sends_payload_with_diag(self, dialog):
        dialog.nick_edit.setText("小明")
        dialog.title_edit.setText("崩溃")
        dialog.body_edit.setPlainText("启动就崩")
        dialog._on_submit()
        assert len(dialog._transport.calls) == 1
        url, data, headers = dialog._transport.calls[0]
        assert url == fb.ISSUES_API
        assert data["title"] == "[小明] 崩溃"
        assert "启动就崩" in data["body"]
        assert "**反馈人：小明**" in data["body"]
        assert "```text" in data["body"]
        assert headers["Authorization"] == "Bearer test-token"

    def test_success_flow_accepts(self, dialog, monkeypatch):
        # 吞掉结果弹窗
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(QMessageBox, "exec", lambda self: None)
        dialog.nick_edit.setText("小红")
        dialog.title_edit.setText("建议")
        dialog.body_edit.setPlainText("加个功能")
        dialog._on_submit()
        raw = json.dumps({"html_url": "https://github.com/yakrsa/MiteProxy/issues/7"}).encode()
        dialog.finish_transport(201, raw)
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_failure_shows_error_and_reenables(self, dialog):
        dialog.nick_edit.setText("x")
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


# ---------------------------------------------------------------- 崩溃报告脱敏

class TestRedact:
    """脱敏是上报的前置条件：漏一个 token 就等于把用户登录态公开到 issue 里。"""

    def test_masks_authorization_header(self):
        out = fb.redact("Authorization: Bearer abc123\nHost: a.com")
        assert "Bearer abc123" not in out
        assert "Host: a.com" in out

    def test_masks_cookie_header(self):
        out = fb.redact("Cookie: SESSION=deadbeef; uid=1")
        assert "deadbeef" not in out

    def test_masks_url_query_by_default(self):
        out = fb.redact("GET https://a.com/api?id=12&token=xyz HTTP/1.1")
        assert "xyz" not in out
        assert "id=12" not in out          # query 整体抹掉，不留参数
        assert "https://a.com/api" in out  # path 保留，便于定位接口

    def test_keeps_param_names_when_asked(self):
        out = fb.redact("GET https://a.com/api?id=12&token=xyz", keep_urls=True)
        assert "xyz" not in out
        assert "id=<已脱敏>" in out
        assert "token=<已脱敏>" in out
        assert "https://a.com/api" in out

    def test_masks_bare_secret_params_in_log_body(self):
        """``access_token`` 这类带前缀的参数曾漏网：``\\btoken`` 匹配不到下划线连接。"""
        out = fb.redact("access_token=zzz999 and refresh_token=aaa111")
        assert "zzz999" not in out
        assert "aaa111" not in out

    def test_leaves_innocent_params_alone(self):
        out = fb.redact("max_tokens=100 status=404")
        assert "max_tokens=100" in out
        assert "status=404" in out

    def test_handles_empty_input(self):
        assert fb.redact("") == ""
        assert fb.redact(None) == ""

    def test_idempotent(self):
        once = fb.redact("Authorization: Bearer abc")
        assert fb.redact(once) == once


# ---------------------------------------------------------------- 崩溃正文

SUMMARY = {
    "detected_at": "2026-10-29T00:40:00",
    "started_at": "启动于 2026-10-28 20:40:11 pid=4321",
    "version": "3.0.1",
    "excerpt": "Windows fatal exception: access violation",
    "hang": "=== 界面卡死 20:42:10 ===",
    "actions": ["20:42:58 open_detail | GET https://a.com/x?token=SECRET 8MB"],
}


class TestCrashBody:
    def test_body_lists_summary_fields(self):
        body = fb.build_crash_body(SUMMARY, "版本: 3.0.1")
        assert "崩溃" in body and "界面卡死" in body
        assert "2026-10-29T00:40:00" in body
        assert "pid=4321" in body
        assert "v3.0.1" in body

    def test_body_hides_token_from_actions(self):
        body = fb.build_crash_body(SUMMARY, "")
        assert "SECRET" not in body
        assert "<已脱敏>" in body

    def test_body_can_omit_actions(self):
        body = fb.build_crash_body(SUMMARY, "", include_actions=False)
        assert "最近操作" not in body
        assert "open_detail" not in body

    def test_body_wraps_evidence_in_details(self):
        body = fb.build_crash_body(SUMMARY, "")
        assert "<details>" in body
        assert "崩溃栈与 Qt 消息" in body

    def test_title_uses_version_and_exception(self):
        title = fb.crash_issue_title(SUMMARY)
        assert "v3.0.1" in title
        assert "access violation" in title.lower()
        assert title.startswith("[自动上报]")

    def test_title_survives_missing_fields(self):
        assert fb.crash_issue_title({}).startswith("[自动上报]")

    def test_payload_accepts_custom_labels(self):
        p = fb.payload("t", "b", labels=["bug"])
        assert p["labels"] == ["bug"]

    def test_payload_defaults_to_feedback_label(self):
        assert fb.payload("t", "b")["labels"] == ["feedback"]
