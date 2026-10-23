"""T1 第二批：命令面板 Ctrl+K / 请求概览卡 / 行密度开关。

覆盖三块功能的核心行为：
- 概览卡：set_flow 渲染方法/状态码 pill + URL + 耗时/大小/类型/IP；clear 收起；
- 命令面板：构建随状态变化的命令、按关键字实时过滤、回车执行回调；
- 行密度：流量表行高随 comfortable/compact 切换、设置项落盘与非法值回落。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.settings import Settings
from app.ui.command_palette import CommandPalette
from app.ui.overview_card import OverviewCard
from app.ui.traffic_table import TrafficTable


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    """复用 test_ui_nav 的隔离 MainWindow 构造方式（MITEPROXY_HOME 隔离）。"""
    from app.ui import theme
    from app.ui.main_window import MainWindow

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    theme.apply("light")
    w = MainWindow(restore_prompt=False)
    yield w
    w.close()


# ---------------------------------------------------------------- 概览卡

def _make_flow():
    from mitmproxy.test import tflow

    f = tflow.tflow(resp=True)
    f.request.method = "POST"
    f.response.status_code = 404
    f.response.reason = "Not Found"
    f.response.headers["content-type"] = "application/json; charset=utf-8"
    return f


def test_overview_card_shows_flow(qapp):
    card = OverviewCard()
    card.set_flow(_make_flow())
    assert not card.isHidden()
    # 方法 pill + 状态码 pill 都可见
    assert card.method_pill.isVisible()
    assert card.status_pill.isVisible()
    # URL 单行、可省略、非空白
    assert card.url_label.text().strip()
    # 耗时 / 大小 / 类型 / 服务端 四段小字都填上
    assert "耗时" in card.duration_label.text()
    assert "大小" in card.size_label.text()
    assert "类型" in card.type_label.text()
    assert "服务端" in card.ip_label.text()


def test_overview_card_status_zero_hides_pill(qapp):
    card = OverviewCard()
    f = _make_flow()
    f.response = None  # pending：无响应
    card.set_flow(f)
    # 无状态码 → 状态码 pill 收起，但 URL / 耗时仍渲染
    assert not card.status_pill.isVisible()
    assert card.url_label.text().strip()


def test_overview_card_tolerates_lightweight_stand_in(qapp):
    """详情面板的轻量替身（SimpleNamespace，缺 scheme/pretty_host 等）不能把 UI 带崩。

    回归：概览卡曾直接调 CaptureAddon.summarize，替身 flow 触发 AttributeError，
    导致 test_detail_panel 整批 10 个失败。现在应退化为空值渲染而不抛异常。
    """
    from types import SimpleNamespace

    card = OverviewCard()
    fake = SimpleNamespace(
        request=SimpleNamespace(method="GET"),
        response=None,
    )
    card.set_flow(fake)  # 不得抛
    assert card.method_pill.text() == "GET"
    assert card.url_label.text() == ""
    assert card.status_pill.isVisible() is False


def test_overview_card_clear_hides(qapp):
    card = OverviewCard()
    card.set_flow(_make_flow())
    assert not card.isHidden()
    card.clear()
    assert card.isHidden()


def test_overview_card_retheme_no_crash(qapp):
    card = OverviewCard()
    card.set_flow(_make_flow())
    card._retheme()  # 主题切换重绘不应抛异常
    assert card.url_label.text()


# ---------------------------------------------------------------- 命令面板

def _sample_commands():
    calls = []

    def _run():
        calls.append(1)

    return [
        {"id": "a", "title": "启动代理", "keywords": "proxy start", "run": _run},
        {"id": "b", "title": "清空列表", "keywords": "clear", "run": _run},
        {"id": "c", "title": "打开设置", "keywords": "settings", "run": _run},
    ], calls


def test_palette_filters_by_keyword(qapp):
    pal = CommandPalette()
    cmds, _ = _sample_commands()
    pal.set_commands(cmds)
    pal.query.setText("代理")
    pal._filter()
    assert pal.list.count() == 1
    assert pal.list.item(0).text() == "启动代理"


def test_palette_empty_query_shows_all(qapp):
    pal = CommandPalette()
    cmds, _ = _sample_commands()
    pal.set_commands(cmds)
    pal.query.setText("")
    pal._filter()
    assert pal.list.count() == len(cmds)
    assert pal.list.currentRow() == 0


def test_palette_no_match_shows_nothing(qapp):
    pal = CommandPalette()
    cmds, _ = _sample_commands()
    pal.set_commands(cmds)
    pal.query.setText("zzz-no-such-command")
    pal._filter()
    assert pal.list.count() == 0


def test_palette_run_current_invokes_callback(qapp):
    pal = CommandPalette()
    cmds, calls = _sample_commands()
    pal.set_commands(cmds)
    pal._filter()
    pal.list.setCurrentRow(1)  # 清空列表
    pal._run_current()
    assert calls == [1]


# ---------------------------------------------------------------- 行密度

def test_traffic_table_row_density_changes_height(qapp):
    table = TrafficTable()
    # 注意：Qt 样式会按最小行高对 defaultSectionSize 做钳制（macOS 下 18→19），
    # 故只断言「紧凑 < 舒适」的相对关系，不卡具体像素值。
    table.set_row_density("comfortable")
    comfort_h = table.verticalHeader().defaultSectionSize()
    table.set_row_density("compact")
    compact_h = table.verticalHeader().defaultSectionSize()
    assert compact_h < comfort_h
    # 非法模式回落舒适
    table.set_row_density("bogus")
    assert table.verticalHeader().defaultSectionSize() == comfort_h


def test_settings_density_roundtrip():
    s = Settings()
    assert s.density == "comfortable"
    d = s.to_dict()
    assert d["density"] == "comfortable"
    s2 = Settings.from_dict({"density": "compact"})
    assert s2.density == "compact"
    # 非法值回落舒适
    s3 = Settings.from_dict({"density": "huge"})
    assert s3.density == "comfortable"


def test_density_combo_reflects_settings(win):
    """工具栏密度下拉默认跟随设置（舒适）。"""
    assert win.density_combo.currentData() == win.settings.density


def test_set_density_updates_table_and_setting(win):
    # 先取舒适档实际行高作基准（Qt 会按样式钳制，不卡常量）
    win.traffic_table.set_row_density("comfortable")
    comfort_h = win.traffic_table.verticalHeader().defaultSectionSize()
    win._set_density("compact")
    assert win.traffic_table.verticalHeader().defaultSectionSize() < comfort_h
    assert win.settings.density == "compact"
    # 同步工具栏下拉
    assert win.density_combo.currentData() == "compact"


# ---------------------------------------------------------------- 命令构建

def test_build_commands_returns_runnable_list(win):
    cmds = win._build_commands()
    assert len(cmds) >= 20
    ids = {c["id"] for c in cmds}
    # 关键动作都在：代理 / 抓包 / 清除 / 主题 / 语言 / 各 tab 跳转
    for needed in ("proxy", "capture", "clear", "theme_light", "lang_en",
                   "tab_traffic", "density_compact"):
        assert needed in ids
    for c in cmds:
        assert callable(c["run"])
        assert c["title"]  # 标题已翻译、非空


def test_build_commands_proxy_title_follows_state(win, monkeypatch):
    monkeypatch.setattr(type(win.proxy), "running", True, raising=False)
    titles = {c["id"]: c["title"] for c in win._build_commands()}
    assert "停止代理" in titles["proxy"]
    monkeypatch.setattr(type(win.proxy), "running", False, raising=False)
    titles = {c["id"]: c["title"] for c in win._build_commands()}
    assert "启动代理" in titles["proxy"]


def test_ctrl_k_shortcut_registered_and_opens_palette(win):
    """Ctrl+K 快捷键必须注册到窗口且 slot 能弹出面板（懒加载首次创建）。

    注意：offscreen 下窗口不是 active window，WindowShortcut 收不到合成
    按键事件，所以这里验证注册信息 + 直接调 slot，不模拟按键。
    """
    from PySide6.QtGui import QShortcut

    hits = [sc for sc in win.findChildren(QShortcut) if sc.key().toString() == "Ctrl+K"]
    assert len(hits) == 1
    assert hits[0].isEnabled()

    assert win._command_palette is None  # 懒加载：构造时还没建
    win._open_command_palette()
    assert win._command_palette is not None
    assert win._command_palette.isVisible()
    # 再次调用复用同一实例（不重复弹窗）
    win._open_command_palette()
    assert len([sc for sc in win.findChildren(QShortcut) if sc.key().toString() == "Ctrl+K"]) == 1
