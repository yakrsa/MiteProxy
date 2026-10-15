"""「加入 Mock」改为打开预填的新建窗口（而非直接落库）的回归测试。

盯这些点：
1. 从抓包生成的预填规则（尚未在 store 中）打开对话框 → 标题为「新增 Mock 规则」，
   且 URL / 响应 body / 请求 Body / 状态码 / 匹配类型 自动带入；
2. 用户在窗口确认（accept）→ 规则才加入 store；
3. 已存在于 store 的规则再打开 → 标题为「编辑 Mock 规则」；
4. 取消（reject）不落库。
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.rules import Action, EXACT, Match, Rule, RuleStore  # noqa: E402
from app.ui.rule_editor import RuleEditorDialog  # noqa: E402


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def store(tmp_path):
    return RuleStore(path=tmp_path / "rules.json")


def _captured_rule():
    url = "https://api.example.com/v1/user/123"
    rule = Rule.create(name="GET api.example.com/v1/user/123")
    rule.match = Match(type=EXACT, value=url, method="")
    rule.action = Action(
        status=201,
        headers={"Content-Type": "application/json"},
        body_source="inline",
        body='{"id":123,"name":"x"}',
        latency_ms=0,
    )
    rule.source = "captured"
    rule.request_body = '{"q":"hello"}'
    return rule


def test_new_captured_rule_opens_as_new_with_prefill(qapp, store):
    rule = _captured_rule()
    dlg = RuleEditorDialog(store, rule, parent=None)
    assert dlg.windowTitle() == "新增 Mock 规则"
    assert dlg.match_value_edit.text() == rule.match.value
    assert dlg.body_edit.toPlainText() == '{"id":123,"name":"x"}'
    assert dlg.req_body_edit.toPlainText() == '{"q":"hello"}'
    assert dlg.status_edit.text() == "201"
    assert dlg.match_type_combo.currentData() == EXACT


def test_confirm_adds_to_store(qapp, store):
    rule = _captured_rule()
    dlg = RuleEditorDialog(store, rule, parent=None)
    before = len(store.all())
    dlg._on_accept()
    assert len(store.all()) == before + 1
    assert any(r.id == rule.id for r in store.all())


def test_existing_rule_shows_edit_title(qapp, store):
    rule = _captured_rule()
    store.add(rule)
    dlg = RuleEditorDialog(store, rule, parent=None)
    assert dlg.windowTitle() == "编辑 Mock 规则"


def test_cancel_does_not_add(qapp, store):
    rule = _captured_rule()
    dlg = RuleEditorDialog(store, rule, parent=None)
    cnt = len(store.all())
    dlg.reject()
    assert len(store.all()) == cnt
