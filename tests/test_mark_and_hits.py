"""Mock 命中计数 + 会话标记备注（DESIGN 3.3 / 3.2）。

盯这些点：
1. 命中计数必须在代理线程安全（MockAddon 在 asyncio 线程调 record_hit）；
2. 计数**不持久化**——每次命中写盘会把热路径拖慢，重启归零可接受；
3. 备注走 flow.comment（mitmproxy 原生字段），与 marked（MOCK/REPLAY 徽标）
   分开，两者不能互相覆盖；
4. 备注列显示优先级：用户备注 > MOCK 徽标 > WS > REPLAY；
5. 备注要能过会话保存/恢复（活会话的一部分）。
"""

import asyncio
import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-mark-test-home")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from addons.capture import CaptureAddon  # noqa: E402
from addons.mock import MockAddon  # noqa: E402
from app import session as session_mod  # noqa: E402
from app.rules import Match, Rule, RuleStore  # noqa: E402
from app.ui.flow_store import COL_MARK, FlowStore  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
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


def _mock_rule(store: RuleStore, name: str = "测试规则") -> Rule:
    rule = Rule.create(name)
    rule.match = Match(type="contains", value="/api/")
    return store.add(rule)


# ---------------------------------------------------------------- 命中计数


class TestRuleHitCounting:
    def test_record_hit_increments_and_times(self, store):
        rule = _mock_rule(store)
        before = time.time()
        store.record_hit(rule.id)
        store.record_hit(rule.id)
        after = time.time()
        assert rule.hits == 2
        assert before <= rule.last_hit <= after

    def test_callback_fires_with_rule_id(self, store):
        seen = []
        store.set_callbacks(on_rule_hit=lambda rid: seen.append(rid))
        rule = _mock_rule(store)
        store.record_hit(rule.id)
        assert seen == [rule.id]

    def test_unknown_rule_id_is_noop(self, store):
        seen = []
        store.set_callbacks(on_rule_hit=lambda rid: seen.append(rid))
        store.record_hit("r_nonexistent")
        assert seen == []

    def test_hits_not_persisted(self, store, tmp_path):
        """每次命中都写盘会拖慢热路径——计数只在内存，重启归零。"""
        rule = _mock_rule(store)
        store.record_hit(rule.id)
        reloaded = RuleStore(path=tmp_path / "rules.json")
        reloaded.load()
        assert reloaded.get(rule.id).hits == 0
        # to_dict 里也不该出现 hits（保持 rules.json 是可迁移的干净资产）
        assert "hits" not in rule.to_dict()

    def test_callback_exception_does_not_break_proxy_thread(self, store):
        def boom(_rid):
            raise RuntimeError("UI 崩了也不能拖累代理线程")

        store.set_callbacks(on_rule_hit=boom)
        rule = _mock_rule(store)
        store.record_hit(rule.id)  # 不抛
        assert rule.hits == 1

    def test_concurrent_hits_are_counted(self, store):
        rule = _mock_rule(store)
        threads = [
            threading.Thread(target=store.record_hit, args=(rule.id,))
            for _ in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert rule.hits == 20


class TestMockAddonRecordsHits:
    def test_hit_recorded_on_match(self, store):
        from mitmproxy.test import tflow

        addon = MockAddon(store)
        rule = _mock_rule(store, "命中规则")
        flow = tflow.tflow(resp=False)
        flow.request.url = "http://example.com/api/user"
        asyncio.run(addon.request(flow))
        assert rule.hits == 1
        assert flow.response is not None  # 确实造了响应

    def test_no_hit_when_no_match(self, store):
        from mitmproxy.test import tflow

        addon = MockAddon(store)
        _mock_rule(store)
        flow = tflow.tflow(resp=False)
        flow.request.url = "http://example.com/other"
        asyncio.run(addon.request(flow))
        assert flow.response is None

    def test_disabled_rule_not_hit(self, store):
        from mitmproxy.test import tflow

        addon = MockAddon(store)
        rule = _mock_rule(store)
        store.update(rule.id, enabled=False)
        flow = tflow.tflow(resp=False)
        flow.request.url = "http://example.com/api/user"
        asyncio.run(addon.request(flow))
        assert rule.hits == 0


# ---------------------------------------------------------------- 备注字段


class TestCommentField:
    def test_summarize_includes_comment(self):
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        flow.comment = "可疑请求，待查"
        summary = CaptureAddon.summarize(flow)
        assert summary["comment"] == "可疑请求，待查"

    def test_summarize_comment_defaults_empty(self):
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        assert CaptureAddon.summarize(flow)["comment"] == ""

    def test_comment_survives_session_round_trip(self, tmp_path):
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        flow.comment = "恢复后还要在"
        path = tmp_path / "s.jsonl"
        result = session_mod.save_session(path, [flow])
        assert result.ok
        loaded = session_mod.load_session(path)
        assert loaded.ok and loaded.count == 1
        assert loaded.flows[0].comment == "恢复后还要在"


# ---------------------------------------------------------------- 列表模型


def _summary(**kw):
    base = {
        "id": "f1",
        "method": "GET",
        "host": "x.test",
        "server_ip": "1.2.3.4",
        "path": "/p",
        "url": "http://x.test/p",
        "status": 200,
        "size": 10,
        "duration_ms": 1.0,
        "content_type": "text/plain",
        "marked": "",
        "is_replay": False,
        "timestamp": 0.0,
        "is_connect": False,
    }
    base.update(kw)
    return base


class TestFlowStoreComment:
    def test_comment_shown_over_mock_badge(self):
        store = FlowStore()
        store.append(_summary(marked="MOCK:规则A", comment="我写的"))
        idx = store.index(0, COL_MARK)
        assert idx.data() == "我写的"

    def test_badge_shown_when_no_comment(self):
        store = FlowStore()
        store.append(_summary(marked="MOCK:规则A"))
        assert store.index(0, COL_MARK).data() == "MOCK:规则A"

    def test_comment_over_replay_badge(self):
        store = FlowStore()
        store.append(_summary(is_replay=True, comment="重放验证"))
        assert store.index(0, COL_MARK).data() == "重放验证"

    def test_tooltip_has_both_comment_and_badge(self):
        store = FlowStore()
        store.append(_summary(marked="MOCK:规则A", comment="我写的"))
        tip = store.index(0, COL_MARK).data(Qt.ItemDataRole.ToolTipRole)
        assert "备注: 我写的" in tip
        assert "MOCK:规则A" in tip

    def test_set_comment_updates_in_place(self):
        store = FlowStore()
        store.append(_summary())
        assert store.set_comment("f1", "第一条")
        assert store.index(0, COL_MARK).data() == "第一条"
        # 同值重复设置不算变化（避免无谓的 dataChanged）
        assert store.set_comment("f1", "第一条")

    def test_set_comment_unknown_id(self):
        store = FlowStore()
        store.append(_summary())
        assert store.set_comment("nope", "x") is False

    def test_set_comment_emits_data_changed(self):
        store = FlowStore()
        store.append(_summary())
        seen = []
        store.dataChanged.connect(lambda *a: seen.append(a))
        store.set_comment("f1", "改一下")
        assert len(seen) == 1
        assert seen[0][0].column() == COL_MARK

    def test_sort_key_includes_comment(self):
        store = FlowStore()
        store.append(_summary(id="a", comment="bbb"))
        store.append(_summary(id="b", marked="MOCK:x"))
        key_a = store.index(0, COL_MARK).data(Qt.ItemDataRole.UserRole + 1)
        key_b = store.index(1, COL_MARK).data(Qt.ItemDataRole.UserRole + 1)
        assert key_a == "bbb"
        assert key_b == "mock:x"

    def test_update_summary_keeps_comment(self):
        """WS 增量更新整行替换时，备注不能丢（summarize 带着 comment）。"""
        store = FlowStore()
        store.append(_summary())
        store.set_comment("f1", "WS 会话备注")
        store.update(_summary(id="f1", is_websocket=True, ws_messages=3,
                               comment="WS 会话备注"))
        assert store.index(0, COL_MARK).data() == "WS 会话备注"


# ---------------------------------------------------------------- 规则面板


class TestRulesPanelHits:
    def test_column_added(self, qapp, store):
        panel = RulesPanel(store)
        assert panel.table.columnCount() == 6
        assert panel.table.horizontalHeaderItem(5).text() == "命中"

    def test_refresh_shows_dash_for_zero(self, qapp, store):
        rule = _mock_rule(store)
        panel = RulesPanel(store)
        assert panel.table.item(0, 5).text() == "—"
        assert panel.table.item(0, 5).toolTip() == ""

    def test_refresh_shows_count(self, qapp, store):
        rule = _mock_rule(store)
        rule.hits = 7
        rule.last_hit = time.time()
        panel = RulesPanel(store)
        assert panel.table.item(0, 5).text() == "7"
        assert "最近命中" in panel.table.item(0, 5).toolTip()

    def test_update_hit_live(self, qapp, store):
        rule = _mock_rule(store)
        panel = RulesPanel(store)
        rule.hits = 3
        rule.last_hit = time.time()
        panel.update_hit(rule.id)
        assert panel.table.item(0, 5).text() == "3"

    def test_update_hit_unknown_rule_noop(self, qapp, store):
        _mock_rule(store)
        panel = RulesPanel(store)
        panel.update_hit("r_nope")  # 不抛
        assert panel.table.item(0, 5).text() == "—"


# ---------------------------------------------------------------- 主窗口接线


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    if not home.exists():
        home.mkdir(parents=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    win = MainWindow(restore_prompt=False)
    yield win
    win.close()


class TestMainWindowMark:
    def _flow(self):
        from mitmproxy.test import tflow

        flow = tflow.tflow(resp=True)
        flow.request.url = "http://x.test/api/a"
        return flow

    def test_mark_selected_writes_comment(self, window, monkeypatch):
        import app.ui.main_window as mw

        flow = self._flow()
        window.flow_store.append(window.capture.summarize(flow))
        window.detail_panel.show_flow(flow)
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])
        monkeypatch.setattr(
            mw.QInputDialog, "getText",
            staticmethod(lambda *a, **k: ("盯着这条", True)),
        )
        window._mark_selected()
        assert flow.comment == "盯着这条"
        # 列表行内更新（不重建行）
        row = window.flow_store.row_data(0)
        assert row["comment"] == "盯着这条"
        assert window.flow_store.index(0, COL_MARK).data() == "盯着这条"
        # 详情面板备注条同步显出（offscreen 下判 isHidden，isVisible 恒 False）
        assert not window.detail_panel.comment_label.isHidden()
        assert "盯着这条" in window.detail_panel.comment_label.text()

    def test_mark_cancelled_keeps_old(self, window, monkeypatch):
        import app.ui.main_window as mw

        flow = self._flow()
        window.flow_store.append(window.capture.summarize(flow))
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])
        monkeypatch.setattr(
            mw.QInputDialog, "getText",
            staticmethod(lambda *a, **k: ("", False)),
        )
        window._mark_selected()
        assert flow.comment == ""

    def test_clear_mark(self, window, monkeypatch):
        flow = self._flow()
        flow.comment = "旧备注"
        window.flow_store.append(window.capture.summarize(flow))
        window.detail_panel.show_flow(flow)
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])
        window._clear_mark_selected()
        assert flow.comment == ""
        assert window.detail_panel.comment_label.isHidden()

    def test_mark_requires_single_selection(self, window):
        from mitmproxy.test import tflow

        flows = [tflow.tflow(resp=True), tflow.tflow(resp=True)]
        window._selected_flows = lambda: flows  # type: ignore[method-assign]
        window._mark_selected()  # 多条直接返回，不弹窗不崩
        assert all(f.comment == "" for f in flows)

    def test_rule_hit_signal_reaches_panel(self, window, qapp):
        """代理线程命中 → record_hit → 信号桥 → 规则页计数器（完整链路）。"""
        rule = window.rule_store.add(Rule.create("链路规则"))
        rule.match = Match(type="contains", value="/api/")
        window.rule_store.save()
        window.rules_panel.refresh()
        # 按 id 找行，不假设在第 0 行（store 里可能有别的用例遗留的规则）
        row = [r.id for r in window.rule_store.all()].index(rule.id)
        assert window.rules_panel.table.item(row, 5).text() == "—"
        window.rule_store.record_hit(rule.id)
        qapp.processEvents()
        assert window.rules_panel.table.item(row, 5).text() == "1"
        assert "最近命中" in window.rules_panel.table.item(row, 5).toolTip()

    def test_mark_flow_without_row_falls_back(self, window, monkeypatch):
        """列表里没有这一行（理论边界）时退回整行刷新，不崩。"""
        import app.ui.main_window as mw

        flow = self._flow()
        window.capture.flows[flow.id] = flow
        monkeypatch.setattr(window, "_selected_flows", lambda: [flow])
        monkeypatch.setattr(
            mw.QInputDialog, "getText",
            staticmethod(lambda *a, **k: ("备注", True)),
        )
        window._mark_selected()
        assert flow.comment == "备注"
