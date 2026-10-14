"""RuleEditorDialog UI 测试：方法过滤下拉 + 重定向模式（v1.12）。"""

import pytest

from app.rules import Action, Match, Rule

pytest.importorskip("PySide6.QtWidgets")


class TestRuleEditorDialog:
    @pytest.fixture()
    def dialog(self, store, qt_or_app):
        from app.ui.rule_editor import RuleEditorDialog

        app = qt_or_app
        from app.ui.rule_editor import RuleEditorDialog as _D

        return _D(store)

    @pytest.fixture()
    def qt_or_app(self):
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_method_combo_present_default_any(self, store, qt_or_app):
        from app.ui.rule_editor import RuleEditorDialog

        d = RuleEditorDialog(store)
        assert d.method_combo.count() >= 8
        assert d.method_combo.currentData() == ""  # 默认任意方法
        d.deleteLater()

    def test_method_selection_saved(self, store, qt_or_app):
        from app.ui.rule_editor import RuleEditorDialog

        d = RuleEditorDialog(store)
        d.name_edit.setText("只 POST")
        d.match_value_edit.setText("/api/")
        idx = d.method_combo.findData("POST")
        d.method_combo.setCurrentIndex(idx)
        d.body_edit.setPlainText("ok")
        ok, msg = d._collect()
        assert ok, msg
        rule = store.all()[0]
        assert rule.match.method == "POST"
        d.deleteLater()

    def test_redirect_mode_roundtrip(self, store, qt_or_app):
        from app.ui.rule_editor import RuleEditorDialog

        rule = Rule.create("转发")
        rule.match = Match(type="contains", value="/api/")
        rule.action = Action(redirect_url="https://b.com/")
        store.add(rule)

        d = RuleEditorDialog(store, rule)
        assert d.redirect_radio.isChecked()  # 载入时按 redirect_url 识别模式
        assert d.redirect_edit.text() == "https://b.com/"
        d.redirect_edit.setText("https://staging.example.com/v2/")
        ok, msg = d._collect()
        assert ok, msg
        updated = store.all()[0]
        assert updated.action.redirect_url == "https://staging.example.com/v2/"
        assert updated.action.status == 200  # 未动状态码字段也保持默认
        d.deleteLater()

    def test_redirect_requires_http_prefix(self, store, qt_or_app):
        from app.ui.rule_editor import RuleEditorDialog

        d = RuleEditorDialog(store)
        d.name_edit.setText("坏目标")
        d.match_value_edit.setText("/api/")
        d.redirect_radio.setChecked(True)
        d._sync_source_widgets()
        d.redirect_edit.setText("ftp://x")
        ok, msg = d._collect()
        assert not ok and "http" in msg
        d.deleteLater()

    def test_redirect_disables_status_and_headers(self, store, qt_or_app):
        from app.ui.rule_editor import RuleEditorDialog

        d = RuleEditorDialog(store)
        assert d.status_edit.isEnabled()
        d.redirect_radio.setChecked(True)
        d._sync_source_widgets()
        assert not d.status_edit.isEnabled()
        assert not d.headers_table.isEnabled()
        d.deleteLater()

    def test_edit_existing_method_rule_roundtrip(self, store, qt_or_app):
        """编辑存量规则（旧版无 method）→ 保存后字段不丢。"""
        from app.ui.rule_editor import RuleEditorDialog

        rule = Rule.create("存量")
        rule.match = Match(type="contains", value="/api/")
        rule.action = Action(status=418, body="teapot")
        store.add(rule)

        d = RuleEditorDialog(store, rule)
        assert d.status_edit.text() == "418"
        assert d.method_combo.currentData() == ""
        idx = d.method_combo.findData("GET")
        d.method_combo.setCurrentIndex(idx)
        ok, msg = d._collect()
        assert ok, msg
        updated = store.all()[0]
        assert updated.match.method == "GET"
        assert updated.action.status == 418
        assert updated.action.body == "teapot"
        d.deleteLater()
