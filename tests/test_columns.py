"""流量列表列显隐与可选列测试（路线图 #6）。"""

import pytest
from PySide6.QtWidgets import QApplication

from app.ui.flow_store import (
    COLUMN_KEYS,
    COLUMNS,
    COL_COMMENT,
    COL_CONTENT_TYPE,
    COL_STARTED,
    DEFAULT_HIDDEN_COLUMNS,
    FlowStore,
    column_index,
    format_clock,
)
from app.ui.main_window import MainWindow


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    win = MainWindow(restore_prompt=False)
    yield win
    win.close()


def _summary():
    from mitmproxy.test import tflow

    flow = tflow.tflow(resp=True)
    flow.request.url = "http://x.test/api?a=1"
    flow.response.headers["content-type"] = "application/json; charset=utf-8"
    flow.comment = "my note"
    return flow


# ---------------------------------------------------------------- 模型


def test_column_keys_match_columns():
    assert len(COLUMN_KEYS) == len(COLUMNS)
    assert len(set(COLUMN_KEYS)) == len(COLUMN_KEYS)


def test_optional_columns_in_data(qapp):
    from addons.capture import CaptureAddon

    store = FlowStore()
    flow = _summary()
    store.append(CaptureAddon.summarize(flow))
    row = store.rows[0]

    idx_ct = store.index(0, COL_CONTENT_TYPE)
    assert "application/json" in store.data(idx_ct)
    assert store.data(store.index(0, COL_COMMENT)) == "my note"
    # 开始时刻：HH:MM:SS.mmm 形态
    clock = store.data(store.index(0, COL_STARTED))
    assert len(clock) == 12 and clock[2] == ":" and clock[-4] == "."


def test_content_type_dash_without_response(qapp):
    store = FlowStore()
    from addons.capture import CaptureAddon
    from mitmproxy.test import tflow

    flow = tflow.tflow()          # 无响应
    store.append(CaptureAddon.summarize(flow))
    assert store.data(store.index(0, COL_CONTENT_TYPE)) == "-"
    # 开始时刻：tflow 的请求带 timestamp_start，正常给时钟（无时间戳给 - 由
    # format_clock 单测覆盖）
    assert store.data(store.index(0, COL_STARTED)) != "-"


def test_sort_role_for_new_columns(qapp):
    from addons.capture import CaptureAddon
    from PySide6.QtCore import Qt

    store = FlowStore()
    flow = _summary()
    store.append(CaptureAddon.summarize(flow))
    from app.ui.flow_store import SORT_ROLE

    assert isinstance(store.data(store.index(0, COL_STARTED), SORT_ROLE), float)
    assert isinstance(store.data(store.index(0, COL_COMMENT), SORT_ROLE), str)
    assert "application/json" in store.data(store.index(0, COL_CONTENT_TYPE), SORT_ROLE)


def test_format_clock():
    assert format_clock(0) == "-"
    assert format_clock(None) == "-"
    # 毫秒截断（不四舍五入）：.1239 → 123
    import time
    from datetime import datetime

    dt = datetime(2026, 10, 22, 8, 30, 15, 123900)
    ts = dt.timestamp()
    assert format_clock(ts) == "08:30:15.123"


def test_column_index_unknown():
    assert column_index("nope") is None
    assert column_index("mark") == 9


# ---------------------------------------------------------------- 设置持久化


def test_settings_hidden_columns_roundtrip(tmp_path, monkeypatch):
    from app.settings import Settings

    s = Settings()
    s.hidden_columns = ["method", "content_type"]
    d = s.to_dict()
    assert d["hidden_columns"] == ["method", "content_type"]
    assert Settings.from_dict(d).hidden_columns == ["method", "content_type"]


def test_settings_hidden_columns_sanitize():
    from app.settings import Settings

    s = Settings.from_dict({"hidden_columns": ["method", "bogus", 42]})
    assert s.hidden_columns == ["method"]


def test_settings_default_hides_optional_columns():
    from app.settings import Settings

    assert Settings.from_dict({}).hidden_columns == list(DEFAULT_HIDDEN_COLUMNS)


# ---------------------------------------------------------------- 主窗口接线


def test_window_applies_default_hidden_columns(window):
    # 可选列默认隐藏；其余默认可见
    assert window.traffic_table.isColumnHidden(column_index("content_type"))
    assert window.traffic_table.isColumnHidden(column_index("started"))
    assert window.traffic_table.isColumnHidden(column_index("comment"))
    assert not window.traffic_table.isColumnHidden(column_index("path"))


def test_toggle_column_shows_and_persists(window, tmp_path):
    import json

    window._toggle_column("content_type", True)     # 勾选 = 显示
    assert not window.traffic_table.isColumnHidden(column_index("content_type"))
    assert "content_type" not in window.settings.hidden_columns

    # 落盘：重新加载设置后仍在
    from app.settings import SETTINGS_PATH, load_settings

    data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    assert "content_type" not in data["hidden_columns"]
    assert load_settings().hidden_columns == window.settings.hidden_columns

    # 再取消勾选 → 重新隐藏
    window._toggle_column("content_type", False)
    assert window.traffic_table.isColumnHidden(column_index("content_type"))
    assert "content_type" in load_settings().hidden_columns


def test_column_menu_has_all_columns_checkable(window):
    menu = window._build_column_menu()
    actions = [a for a in menu.actions() if a.isCheckable()]
    assert len(actions) == len(COLUMN_KEYS)
    # 默认隐藏的列是未勾选态
    hidden = {a.text() for a in actions if not a.isChecked()}
    assert "内容类型" in hidden or "Content type" in hidden


def test_restart_keeps_column_visibility(qapp, tmp_path, monkeypatch):
    """重启（重新构造 MainWindow）后列显隐保持——持久化真正生效。"""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    win1 = MainWindow(restore_prompt=False)
    win1._toggle_column("started", True)      # 显示开始时刻
    win1._toggle_column("method", False)      # 隐藏方法列
    win1.close()

    win2 = MainWindow(restore_prompt=False)
    try:
        assert not win2.traffic_table.isColumnHidden(column_index("started"))
        assert win2.traffic_table.isColumnHidden(column_index("method"))
    finally:
        win2.close()
