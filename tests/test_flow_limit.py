"""「保存条数」上限设置 + mock 命中行着色（见 DESIGN.md 3.2）。

覆盖：
- 档位常量（100/200/500/1000/2000/3000/5000，上限 5000）；
- settings.json 存取与非法值收敛；
- FlowStore 改上限时立即从最旧一端裁剪、且恰好停在上限（不再批量掉档）；
- CaptureAddon 跨线程约束（运行中只改数值，停止时才直接裁）；
- mock 行整行背景/文字着色，状态列语义色优先，REPLAY 行不参与着色。
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-flowlimit-test-home")

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

_app = None


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


from addons.capture import CaptureAddon  # noqa: E402
from app import settings as settings_mod  # noqa: E402
from app.settings import (  # noqa: E402
    DEFAULT_MAX_FLOWS,
    FLOW_LIMIT_CHOICES,
    Settings,
    load_settings,
    sanitize_max_flows,
    save_settings,
)
from app.ui.flow_store import (  # noqa: E402
    COL_HOST,
    COL_MARK,
    COL_STATUS,
    MAX_ROWS,
    MOCK_ROW_BG,
    MOCK_ROW_FG,
    FlowStore,
    status_color,
)


def _row(**kw):
    """最小行的摘要 dict（FlowStore / 着色逻辑用到的键）。"""
    return {
        "id": kw.get("id", "f1"),
        "method": "GET",
        "scheme": "http",
        "host": "api.example.com",
        "server_ip": "127.0.0.1",
        "path": "/v1/user",
        "url": "http://api.example.com/v1/user",
        "status": kw.get("status", 200),
        "size": 1024,
        "duration_ms": 12.0,
        "content_type": "application/json",
        "marked": kw.get("marked", ""),
        "is_replay": kw.get("is_replay", False),
        "timestamp": 0.0,
        "is_connect": False,
    }


class TestLimitChoices:
    def test_choice_list(self):
        assert FLOW_LIMIT_CHOICES == (100, 200, 500, 1000, 2000, 3000, 5000)
        assert FLOW_LIMIT_CHOICES == tuple(sorted(FLOW_LIMIT_CHOICES))

    def test_hard_cap_is_5000(self):
        assert MAX_ROWS == 5000
        assert DEFAULT_MAX_FLOWS == 5000


class TestSanitizeMaxFlows:
    @pytest.mark.parametrize("value", list(FLOW_LIMIT_CHOICES))
    def test_valid_values_kept(self, value):
        assert sanitize_max_flows(value) == value

    def test_numeric_string(self):
        assert sanitize_max_flows("200") == 200

    def test_between_choices_snaps_to_nearest(self):
        assert sanitize_max_flows(800) == 1000
        assert sanitize_max_flows(2600) == 3000

    def test_above_cap_snaps_down(self):
        assert sanitize_max_flows(99999) == 5000

    @pytest.mark.parametrize("bad", [None, "abc", [], {}])
    def test_garbage_falls_back_to_default(self, bad):
        assert sanitize_max_flows(bad) == DEFAULT_MAX_FLOWS


class TestSettingsPersistence:
    def test_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
        save_settings(Settings(max_flows=500))
        assert load_settings().max_flows == 500

    def test_missing_key_uses_default(self):
        assert Settings.from_dict({}).max_flows == DEFAULT_MAX_FLOWS

    def test_invalid_value_sanitized(self):
        assert Settings.from_dict({"max_flows": "x"}).max_flows == DEFAULT_MAX_FLOWS

    def test_to_dict_contains_max_flows(self):
        assert Settings(max_flows=1000).to_dict()["max_flows"] == 1000


class TestStoreLimit:
    def test_default_limit(self):
        assert FlowStore().max_rows == 5000

    def test_append_stops_at_limit_and_drops_oldest(self):
        store = FlowStore()
        store.set_max_rows(100)
        for i in range(150):
            store.append(_row(id=f"f{i}"))
        assert store.rowCount() == 100
        assert store.rows[0]["id"] == "f50"      # 最旧的 50 条被丢弃
        assert store.rows[-1]["id"] == "f149"

    def test_lowering_limit_trims_immediately(self):
        store = FlowStore()
        for i in range(10):
            store.append(_row(id=f"f{i}"))
        store.set_max_rows(3)
        assert store.rowCount() == 3
        assert [r["id"] for r in store.rows] == ["f7", "f8", "f9"]

    def test_exactly_at_limit_not_evicted(self):
        """恰好等于上限时不应提前淘汰（旧实现到上限+1 才批量删 10%）。"""
        store = FlowStore()
        store.set_max_rows(200)
        for i in range(200):
            store.append(_row(id=f"f{i}"))
        assert store.rowCount() == 200
        assert store.rows[0]["id"] == "f0"

    def test_clamped_to_hard_cap(self):
        store = FlowStore()
        store.set_max_rows(99999)
        assert store.max_rows == MAX_ROWS

    def test_raising_limit_keeps_existing_rows(self):
        store = FlowStore()
        store.set_max_rows(100)
        for i in range(120):
            store.append(_row(id=f"f{i}"))
        assert store.rowCount() == 100
        store.set_max_rows(5000)
        assert store.rowCount() == 100        # 已丢的不恢复，但不再继续丢


class TestCaptureLimit:
    def _fake_flow(self, flow_id):
        return SimpleNamespace(id=flow_id)

    def test_running_proxy_only_updates_number(self):
        """代理运行中：只改上限，不动 dict（避免跨线程遍历）。"""
        cap = CaptureAddon()
        for i in range(5):
            cap.response(self._fake_flow(f"f{i}"))
        cap.set_max_flows(2)
        assert len(cap.flows) == 5            # 立即可见地还没裁
        cap.response(self._fake_flow("f5"))   # 下一次 response 里裁
        assert list(cap.flows) == ["f4", "f5"]

    def test_trim_now_when_proxy_stopped(self):
        cap = CaptureAddon()
        for i in range(5):
            cap.response(self._fake_flow(f"f{i}"))
        cap.set_max_flows(2, trim_now=True)
        assert list(cap.flows) == ["f3", "f4"]

    def test_set_max_flows_ignores_garbage_min(self):
        cap = CaptureAddon()
        cap.set_max_flows(0)
        assert cap._max_flows == 1


class TestMockRowColoring:
    def test_marked_row_gets_background_on_every_column(self):
        store = FlowStore()
        store.append(_row(marked="MOCK:rule-a"))
        for col in (0, COL_HOST, COL_STATUS, COL_MARK):
            bg = store.data(store.index(0, col), Qt.ItemDataRole.BackgroundRole)
            assert bg == MOCK_ROW_BG, col

    def test_unmarked_row_has_no_background(self):
        store = FlowStore()
        store.append(_row())
        assert store.data(store.index(0, COL_HOST), Qt.ItemDataRole.BackgroundRole) is None

    def test_marked_row_text_color_on_data_columns(self):
        store = FlowStore()
        store.append(_row(marked="MOCK:rule-a"))
        fg = store.data(store.index(0, COL_HOST), Qt.ItemDataRole.ForegroundRole)
        assert fg == MOCK_ROW_FG

    def test_status_semantic_color_wins_over_mock_color(self):
        """状态列保留绿/橙/红语义色，不被 mock 行色盖掉。"""
        store = FlowStore()
        store.append(_row(marked="MOCK:rule-a", status=503))
        fg = store.data(store.index(0, COL_STATUS), Qt.ItemDataRole.ForegroundRole)
        assert fg == status_color(503)

    def test_mock_badge_still_shown_and_bold(self):
        store = FlowStore()
        store.append(_row(marked="MOCK:rule-a"))
        assert store.data(store.index(0, COL_MARK)) == "MOCK:rule-a"
        font = store.data(store.index(0, COL_MARK), Qt.ItemDataRole.FontRole)
        assert font is not None and font.bold()

    def test_replay_only_row_not_colored(self):
        """只重放、未命中 mock 的行不着色（着色专属于 mock 命中）。"""
        store = FlowStore()
        store.append(_row(is_replay=True))
        assert store.data(store.index(0, COL_HOST), Qt.ItemDataRole.BackgroundRole) is None
        assert store.data(store.index(0, COL_MARK)) == "REPLAY"
