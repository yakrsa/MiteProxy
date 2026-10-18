"""Mock 规则面板：URL / 名称搜索过滤（v2.3.0）。

盯这些点：
1. 搜索按 URL 匹配值 / 名称 / 方法 / 重定向目标 / 本地文件过滤，大小写不敏感；
2. 与「只显示启用」叠加生效（两个条件取交集）；
3. 过滤到 0 条时显示空态提示并说明原因，有规则时不显示；
4. 清空搜索恢复全部；过滤中新增/命中刷新不炸。
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.rules import Action, Match, Rule, RuleStore  # noqa: E402
from app.ui.rules_panel import RulesPanel  # noqa: E402


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def store(tmp_path):
    return RuleStore(path=tmp_path / "rules.json")


def _add(store: RuleStore, name: str, url: str, **kwargs) -> Rule:
    rule = Rule.create(name)
    rule.match = Match(type="contains", value=url, **{
        k: v for k, v in kwargs.items() if k in ("method",)
    })
    return store.add(rule)


@pytest.fixture
def panel(qapp, store):
    _add(store, "用户列表", "/api/user/list")
    _add(store, "订单详情", "/api/order/detail")
    r = _add(store, "支付回调", "/api/pay/notify")
    r.enabled = False
    store.update(r.id, enabled=False)
    return RulesPanel(store)


def _visible_names(panel: RulesPanel) -> list[str]:
    return [panel.store.get(rid).name for rid in panel._display_ids]


class TestSearchFilter:
    def test_initial_shows_all(self, panel):
        assert _visible_names(panel) == ["用户列表", "订单详情", "支付回调"]

    def test_filter_by_url(self, panel):
        panel.search_edit.setText("order")
        assert _visible_names(panel) == ["订单详情"]

    def test_filter_by_name(self, panel):
        panel.search_edit.setText("用户")
        assert _visible_names(panel) == ["用户列表"]

    def test_filter_case_insensitive(self, panel):
        panel.search_edit.setText("API/USER")
        assert _visible_names(panel) == ["用户列表"]

    def test_clear_restores_all(self, panel):
        panel.search_edit.setText("order")
        panel.search_edit.setText("")
        assert _visible_names(panel) == ["用户列表", "订单详情", "支付回调"]

    def test_combined_with_only_enabled(self, panel):
        panel.only_enabled_cb.setChecked(True)
        assert _visible_names(panel) == ["用户列表", "订单详情"]
        panel.search_edit.setText("pay")
        assert _visible_names(panel) == []      # 停用的不被搜出来
        panel.only_enabled_cb.setChecked(False)
        assert _visible_names(panel) == ["支付回调"]

    def test_empty_state_hint_mentions_keyword(self, panel):
        panel.search_edit.setText("不存在的关键字")
        assert _visible_names(panel) == []
        assert not panel.empty_label.isHidden()
        assert "不存在的关键字" in panel.empty_label.text()

    def test_empty_state_hidden_when_store_empty(self, qapp, store):
        panel = RulesPanel(store)
        assert _visible_names(panel) == []
        assert panel.empty_label.isHidden()

    def test_no_match_keeps_other_columns_consistent(self, panel):
        """过滤后表格行数与 _display_ids 一致（勾选列不会错位到别的规则）。"""
        panel.search_edit.setText("user")
        assert panel.table.rowCount() == 1
        # 可见行仍是原列表里的第 1 条（序号列语义 = 全量列表位置）
        assert panel.table.item(0, 1).text() == "用户列表"

    def test_refresh_under_filter_keeps_view(self, panel):
        """代理线程命中/新增触发 refresh 时，过滤条件不丢。"""
        panel.search_edit.setText("order")
        _add(panel.store, "新订单", "/api/order/new")
        panel.refresh()
        assert _visible_names(panel) == ["订单详情", "新订单"]
