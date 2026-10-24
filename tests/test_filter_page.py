"""过滤页（FilterPanel）+ 左侧导航悬停展开 + 右键加黑白名单 的 UI 级测试。

数据模型层（FilterConfig / 代理模型 / 迁移）在 test_filter_model.py，
预设生命周期在 test_filter_presets.py；这里只测三块「壳」：
- 详情面板里的「过滤」页签：常驻可见、能跳转、与顶部栏同源同步；
- 右键菜单的「把域名加入黑/白名单」：增量 + 去重 + 切开关；
- NavRail：默认收起、展开/收起、与 QTabWidget 双向同步。
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QEvent, QEventLoop
from PySide6.QtWidgets import QApplication

from app.ui.filter_model import LIST_BLACK, LIST_WHITE, FilterConfig
from app.ui.main_window import MainWindow
from app.ui.nav_rail import ANIM_MS, COLLAPSED_WIDTH, NavRail
from app.ui.theme import apply as apply_theme


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    apply_theme("light")
    w = MainWindow(restore_prompt=False)
    yield w
    w.close()


def _make_flow(url: str):
    from mitmproxy.test.tflow import tflow

    flow = tflow()
    flow.request.url = url
    return flow


def _pump(ms: int) -> None:
    """真跑一小段事件循环，让动画有机会把 finished 信号发出去。

    offscreen 下 processEvents() 本身不推进动画计时，得真睡一会儿。
    """
    app = QApplication.instance()
    deadline = time.monotonic() + ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        time.sleep(0.01)


def _animated(rail, expanded: bool, timeout: float = 15.0) -> None:
    """以动画方式展开/收起，并等状态收敛（沙箱里动画推进很慢，要轮询）。

    真实 150ms 动画在这里可能一帧要几十毫秒墙钟时间才走一格，所以给足 15s：
    收敛条件是「宽度到位 + 收起时文字已抠掉」，两者都由 `_on_anim_value`
    就地同步处理，不依赖 Qt 的 finished 信号（那东西被打断就不发）。
    """
    rail.set_expanded(expanded)
    target = rail.expanded_width() if expanded else COLLAPSED_WIDTH

    def settled() -> bool:
        if rail.width() != target:
            return False
        return expanded or rail._buttons[0].text() == ""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _pump(30)
        if settled():
            return
    raise AssertionError(
        f"rail 动画没收敛到 {'展开' if expanded else '收起'}："
        f"width={rail.width()} target={target} "
        f"text={rail._buttons[0].text()!r}"
    )


# ---------------------------------------------------------------- 过滤页签

def test_filter_tab_exists_and_always_visible(win):
    dp = win.detail_panel
    assert hasattr(dp, "filter_panel") and hasattr(dp, "filter_index")
    assert dp.tabs.tabText(dp.filter_index) == "过滤"
    # 过滤页不是 per-flow 页签：不受 setTabVisible 显隐逻辑影响
    assert dp.tabs.isTabVisible(dp.filter_index)


def test_show_filter_page_switches_tab(win):
    dp = win.detail_panel
    dp.show_filter_page()
    assert dp.tabs.currentIndex() == dp.filter_index


def test_filter_panel_config_roundtrip(win):
    cfg = FilterConfig(
        blacklist=["a.test", "b.test"],
        whitelist=["c.test"],
        enabled=True,
        active_list=LIST_WHITE,
        hide_connect=True,
        hide_image=True,
    )
    panel = win.detail_panel.filter_panel
    panel.load_config(cfg)
    assert panel.to_config().to_dict() == cfg.to_dict()


def test_filter_panel_off_switch(win):
    panel = win.detail_panel.filter_panel
    panel.load_config(FilterConfig(blacklist=["a.test"], enabled=False))
    out = panel.to_config()
    assert out.enabled is False
    assert out.blacklist == ["a.test"]  # 关掉开关不清列表


def test_filter_panel_add_incremental_and_dedup(win):
    panel = win.detail_panel.filter_panel
    panel.load_config(FilterConfig(blacklist=["a.test"]))
    panel.black_input.setText("b.test, A.TEST;  c.test")
    panel._on_add(LIST_BLACK)
    # 归一化（小写、去空白）+ 去重 + 追加，不覆盖已有内容
    assert panel.to_config().blacklist == ["a.test", "b.test", "c.test"]
    # 再加一次同样的 → 无变化
    panel.black_input.setText("b.test")
    panel._on_add(LIST_BLACK)
    assert panel.to_config().blacklist == ["a.test", "b.test", "c.test"]


def test_filter_panel_delete_selected(win):
    panel = win.detail_panel.filter_panel
    panel.load_config(FilterConfig(blacklist=["a.test", "b.test"]))
    panel.black_table.selectRow(0)
    panel._on_delete(LIST_BLACK)
    assert panel.to_config().blacklist == ["b.test"]


def test_filter_panel_counts_follow_subdomains(win):
    from collections import Counter

    panel = win.detail_panel.filter_panel
    panel.load_config(FilterConfig(blacklist=["a.test"], whitelist=["x.com"]))
    panel.update_counts(Counter({"api.a.test": 3, "a.test": 1, "x.com": 2,
                                 "nox.com": 5}))
    assert panel.black_table.item(0, 1).text() == "4"   # 含子域
    assert panel.white_table.item(0, 1).text() == "2"


def test_bar_edit_syncs_panel_and_persists(win):
    # 顶部栏改 → settings + 过滤页同步（单一事实源在主窗口）
    win.filter_bar.mode_combo.setCurrentIndex(1)  # 黑名单
    win.filter_bar.keywords_edit.setText("sync.test")
    assert win.settings.filter.enabled is True
    assert win.settings.filter.active_list == LIST_BLACK
    assert win.settings.filter.blacklist == ["sync.test"]
    assert win.detail_panel.filter_panel.to_config().to_dict() == \
        win.settings.filter.to_dict()
    # 过滤页改 → 顶部栏同步
    panel = win.detail_panel.filter_panel
    panel.switch_combo.setCurrentIndex(2)  # 白名单
    assert win.settings.filter.active_list == LIST_WHITE
    assert win.settings.filter.enabled is True


# ---------------------------------------------------------------- 右键动作

def test_context_menu_blacklist_incremental(win):
    win._commit_filter_config(FilterConfig(
        whitelist=["keep.test"], enabled=False, active_list=LIST_WHITE))
    flow = _make_flow("http://api.example.com/a")
    menu = win._build_table_context_menu([flow])
    action = next(a for a in menu.actions() if "加入黑名单" in a.text())
    action.trigger()
    cfg = win.settings.filter
    assert cfg.blacklist == ["api.example.com"]
    assert cfg.whitelist == ["keep.test"]      # 另一个列表原样保留
    assert cfg.enabled is True                 # 点了就该生效
    assert cfg.active_list == LIST_BLACK


def test_context_menu_whitelist_switches_and_keeps_black(win):
    win._commit_filter_config(FilterConfig(
        blacklist=["gone.test"], enabled=True, active_list=LIST_BLACK))
    flows = [_make_flow("http://x.test/1"), _make_flow("http://x.test/2"),
             _make_flow("http://y.test/3")]
    menu = win._build_table_context_menu(flows)
    action = next(a for a in menu.actions() if "加入白名单" in a.text())
    action.trigger()
    cfg = win.settings.filter
    assert cfg.whitelist == ["x.test", "y.test"]  # 多选批量 + 去重
    assert cfg.blacklist == ["gone.test"]
    assert cfg.enabled is True
    assert cfg.active_list == LIST_WHITE          # 「仅显示」的意图


def test_context_menu_duplicate_add_no_dup(win):
    flow = _make_flow("http://dup.test/a")
    win._add_domains_to_filter(["dup.test"], "blacklist")
    win._add_domains_to_filter(["dup.test"], "blacklist")
    assert win.settings.filter.blacklist == ["dup.test"]


# ---------------------------------------------------------------- NavRail

def test_bar_switch_list_keeps_the_other_list(win):
    """回归：顶部栏切列表不许把另一份列表抹掉。

    曾经的 bug：切列表时先发 changed，输入框里还是**上一个列表**的内容，
    于是白名单 a.test 切到黑名单，存着的黑名单 b.test 当场被顶掉。
    """
    win._commit_filter_config(FilterConfig(
        blacklist=["b.test"], whitelist=["a.test"],
        enabled=True, active_list=LIST_WHITE))
    bar = win.filter_bar

    bar.mode_combo.setCurrentIndex(1)          # → 黑名单
    cfg = win.settings.filter
    assert cfg.blacklist == ["b.test"]         # 老黑名单保住了
    assert cfg.whitelist == ["a.test"]
    assert cfg.active_list == LIST_BLACK
    assert bar.keywords_edit.text() == "b.test"   # 输入框跟着换源

    bar.mode_combo.setCurrentIndex(0)          # → 关闭
    cfg = win.settings.filter
    assert cfg.enabled is False
    assert cfg.blacklist == ["b.test"] and cfg.whitelist == ["a.test"]


def test_counts_refresh_when_filter_tab_opened(win):
    """回归：手动点开过滤页要补一次命中数（不可见期间所有刷新都被跳过）。"""
    win.resize(1000, 700)
    win.show()
    _pump(50)
    rows = [
        dict(id=i, method="GET", host="api.example.com", path="/x",
             url="http://api.example.com/x", status=200, req_size=0, size=1,
             duration_ms=1.0, server_ip="1.2.3.4", marked="",
             content_type="application/json", timestamp=float(i), comment="",
             is_websocket=False, ws_messages=0, is_replay=False, throttle_ms=0)
        for i in range(6)
    ]
    win.flow_store.beginResetModel()
    win.flow_store.rows = rows
    win.flow_store.endResetModel()
    win._commit_filter_config(FilterConfig(
        blacklist=["example.com"], enabled=True, active_list=LIST_BLACK))

    panel = win.detail_panel.filter_panel
    assert panel.black_table.item(0, 1).text() == ""   # 页面不可见 → 压根没算
    win.detail_panel.tabs.setCurrentIndex(win.detail_panel.filter_index)
    _pump(900)                                        # 等 400ms 防抖定时器
    assert panel.black_table.item(0, 1).text() == "6"


def test_rail_defaults_collapsed(qapp):
    rail = NavRail()
    rail.add_page(rail.style().standardIcon(
        rail.style().StandardPixmap.SP_ComputerIcon),
        rail.style().standardIcon(
            rail.style().StandardPixmap.SP_ComputerIcon), "流量")
    rail.finish()
    assert rail.is_expanded() is False
    assert rail.width() == COLLAPSED_WIDTH
    # 收起态文字清空，靠 tooltip 兜底
    assert rail._buttons[0].text() == ""
    assert rail._buttons[0].toolTip() == "流量"
    rail.deleteLater()


def test_rail_expand_collapse_roundtrip(qapp):
    rail = NavRail()
    rail.add_page(rail.style().standardIcon(
        rail.style().StandardPixmap.SP_ComputerIcon),
        rail.style().standardIcon(
            rail.style().StandardPixmap.SP_ComputerIcon), "Mock 规则")
    rail.finish()
    rail.set_expanded(True, animate=False)
    assert rail.is_expanded() is True
    assert rail.width() == rail.expanded_width()
    assert rail._buttons[0].text() == "Mock 规则"
    assert rail.expanded_width() >= COLLAPSED_WIDTH
    rail.set_expanded(False, animate=False)
    assert rail.is_expanded() is False
    assert rail.width() == COLLAPSED_WIDTH
    assert rail._buttons[0].text() == ""
    rail.deleteLater()


def test_rail_expand_idempotent(qapp):
    rail = NavRail()
    rail.add_page(rail.style().standardIcon(
        rail.style().StandardPixmap.SP_ComputerIcon),
        rail.style().standardIcon(
            rail.style().StandardPixmap.SP_ComputerIcon), "工具")
    rail.finish()
    rail.set_expanded(True, animate=False)
    w1 = rail.width()
    rail.set_expanded(True, animate=False)  # 重复展开不再变
    assert rail.width() == w1
    rail.deleteLater()


def test_rail_syncs_with_tabs_both_ways(win):
    rail = win.nav_rail
    # QTabWidget → rail
    win.tabs.setCurrentWidget(win.stats_panel)
    assert rail._current == win.tabs.currentIndex()
    # rail → QTabWidget
    rail._buttons[2].click()
    assert win.tabs.currentIndex() == 2
    assert win.tabs.widget(2) is not None


def test_rail_page_count_matches_tabs(win):
    assert len(win.nav_rail._buttons) == win.tabs.count() == 7


def test_rail_hover_events_drive_expansion(win):
    """真 enter/leave 事件 → 展开拉宽，移走 → 收起并抠掉文字。"""
    rail = win.nav_rail
    QApplication.sendEvent(rail, QEvent(QEvent.Type.Enter))
    assert rail.is_expanded() is True   # 意图立刻定下来
    _animated(rail, True)
    assert rail.width() == rail.expanded_width()
    assert rail._buttons[0].text() == "流量"

    QApplication.sendEvent(rail, QEvent(QEvent.Type.Leave))
    assert rail.is_expanded() is False
    _animated(rail, False)
    assert rail.width() == COLLAPSED_WIDTH
    assert rail._buttons[0].text() == ""


def test_rail_collapse_is_repeatable(win):
    """回归：收起必须每次都清文字，多轮也不能衰减。

    初版把清文字挂在 `finished` 信号上、还在回调里 `disconnect(self)`
    （且只连一次），第一次收起后信号就断了——之后只缩宽度不抠文字，
    第二轮才发现。现在改成「宽度到位就清」，这条用例守住这个行为。
    """
    rail = win.nav_rail
    for _ in range(3):
        rail.set_expanded(True, animate=False)
        assert rail.width() == rail.expanded_width()
        assert rail._buttons[0].text() == "流量"
        rail.set_expanded(False, animate=False)
        assert rail.width() == COLLAPSED_WIDTH
        assert rail._buttons[0].text() == ""


def test_rail_mid_collapse_keeps_text(win):
    """收到一半（宽度还没到位）就该还看得见文字，别提前抠掉。"""
    rail = win.nav_rail
    rail.set_expanded(True, animate=False)
    rail.set_expanded(False)      # 收起动画开跑
    rail._on_anim_value(70)       # 模拟动画走到中间帧
    assert rail.width() == 70
    assert rail._buttons[0].text() == "流量"
    rail._on_anim_value(COLLAPSED_WIDTH)   # 走到底
    assert rail._buttons[0].text() == ""
    # 半路又把手挪回来：能正常重新展开，不会卡在中间宽度
    rail.set_expanded(True, animate=False)
    assert rail.width() == rail.expanded_width()
    assert rail._buttons[0].text() == "流量"


# ------------------------------------------------------------ 状态栏过滤原因

def test_status_bar_shows_filter_reason(win):
    """过滤条件生效时状态栏要说明「是谁在藏流量」，不能只给个数字。"""
    win._commit_filter_config(FilterConfig(
        blacklist=["a.test", "b.test"], enabled=True,
        active_list=LIST_BLACK, hide_image=True))
    win._update_status()
    text = win.count_label.text()
    assert "域名黑名单 2 条" in text
    assert "隐藏图片" in text

    # 白名单口径
    win._commit_filter_config(FilterConfig(
        whitelist=["x.test"], enabled=True, active_list=LIST_WHITE))
    win._update_status()
    assert "域名白名单 1 条" in win.count_label.text()

    # 类型隐藏单独出现
    win._commit_filter_config(FilterConfig(hide_connect=True))
    win._update_status()
    text = win.count_label.text()
    assert "隐藏 CONNECT" in text
    assert "域名黑名单" not in text and "域名白名单" not in text

    # 全关后不再出现
    win._commit_filter_config(FilterConfig())
    win._update_status()
    assert "隐藏 CONNECT" not in win.count_label.text()


# ------------------------------------------------------------ 命中数（索引化）

def test_update_counts_matches_bruteforce(win):
    """索引化命中数必须和暴力比对逐格一致——优化不能优化出另一套语义。"""
    import random

    from app.ui.filter_model import host_matches, normalize_domain

    panel = win.detail_panel.filter_panel
    random.seed(11)
    hosts = ["a.test", "b.a.test", "x.a.test", "c.com", "nota.test",
             "zz.top", "a.test.evil.com", "deep.b.a.test"]
    entries = ["a.test", "c.com", "top", "zz", "evil.com", "", "  A.TEST  "]
    counts = {h: i + 1 for i, h in enumerate(hosts)}
    panel.load_config(FilterConfig(blacklist=entries, whitelist=entries))
    panel.update_counts(counts)
    for table in (panel.black_table, panel.white_table):
        for r in range(table.rowCount()):
            entry = normalize_domain(table.item(r, 0).text())
            expected = sum(
                n for h, n in counts.items()
                if entry and host_matches(h, entry)
            )
            got = table.item(r, 1).text()
            assert got == (str(expected) if expected else "")


def test_update_counts_empty_clears(win):
    """流量清空后计数要归零清空，不能留着上一次的旧数字。"""
    panel = win.detail_panel.filter_panel
    panel.load_config(FilterConfig(blacklist=["a.test"]))
    panel.update_counts({"a.test": 3})
    assert panel.black_table.item(0, 1).text() == "3"
    panel.update_counts({})
    assert panel.black_table.item(0, 1).text() == ""


def test_host_provider_wired_to_main_window(win):
    """过滤页的取数口必须接到主窗口的会话统计（命中数与「从流量选」共用）。"""
    panel = win.detail_panel.filter_panel
    # 绑定方法每次访问都是新对象，用 == 比较语义等价（同函数同实例）
    assert panel._host_provider == win._current_host_counts
    rows = [
        dict(id=i, method="GET", host="api.example.com", path="/x",
             url="http://api.example.com/x", status=200, req_size=0, size=1,
             duration_ms=1.0, server_ip="1.2.3.4", marked="",
             content_type="application/json", timestamp=float(i), comment="",
             is_websocket=False, ws_messages=0, is_replay=False, throttle_ms=0)
        for i in range(3)
    ]
    win.flow_store.beginResetModel()
    win.flow_store.rows = rows
    win.flow_store.endResetModel()
    assert win._current_host_counts() == {"api.example.com": 3}


# ------------------------------------------------------------ 从流量挑域名

def test_domain_picker_lists_sorted_and_skips_covered(qapp):
    """已在名单里 / 被现有条目覆盖的域名不列；其余按条数倒序。"""
    from app.ui.filter_panel import _DomainPickerDialog

    dlg = _DomainPickerDialog(
        {"api.a.test": 5, "b.test": 2, "c.com": 9, "sub.b.a.test": 4},
        ["a.test"],  # api.a.test / sub.b.a.test 都被 a.test 覆盖
    )
    rows = [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
    assert rows == ["c.com", "b.test"]          # 条数倒序
    dlg.table.selectRow(0)
    assert dlg.selected_domains() == ["c.com"]
    # 被搜索过滤隐藏的行不算选中
    dlg.filter_edit.setText("b")
    assert dlg.selected_domains() == []
    dlg.filter_edit.setText("")
    dlg.table.selectRow(1)
    # selectRow 会把选择换成第 1 行（ExtendedSelection 下单行选择替换多选）
    assert dlg.selected_domains() == ["b.test"]


def test_domain_picker_empty_state(qapp):
    from PySide6.QtWidgets import QDialogButtonBox

    from app.ui.filter_panel import _DomainPickerDialog

    dlg = _DomainPickerDialog({"a.test": 1}, ["a.test"])
    assert dlg.table.rowCount() == 0
    ok = dlg.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled()
    assert "都已经" in dlg.summary.text()


def test_pick_domains_appends_via_provider(win, monkeypatch):
    """「从流量选…」全链路：取数 → 弹窗（打桩）→ 批量增量入列表。"""
    import app.ui.filter_panel as fp

    panel = win.detail_panel.filter_panel
    panel.load_config(FilterConfig())
    panel.set_host_provider(lambda: {"x.test": 3, "y.test": 1})

    captured = {}

    class FakeDlg:
        def __init__(self, counts, existing, parent=None):
            captured["counts"] = counts
            captured["existing"] = existing

        def exec(self):
            return 1  # QDialog.DialogCode.Accepted

        def selected_domains(self):
            return ["x.test", "sub.x.test", "x.test"]   # 带重复，验证去重

    monkeypatch.setattr(fp, "_DomainPickerDialog", FakeDlg)
    panel._on_pick(LIST_BLACK)
    cfg = win.settings.filter
    assert cfg.blacklist == ["x.test", "sub.x.test"]
    assert captured["existing"] == []
    assert captured["counts"] == {"x.test": 3, "y.test": 1}

    # 用户取消：什么都不加
    class CancelDlg(FakeDlg):
        def exec(self):
            return 0

    monkeypatch.setattr(fp, "_DomainPickerDialog", CancelDlg)
    panel._on_pick(LIST_BLACK)
    assert win.settings.filter.blacklist == ["x.test", "sub.x.test"]


# ------------------------------------------------------------ 导航栏钉住/快捷键

def test_rail_pin_keeps_expanded_and_persists(win):
    """钉住 = 移开鼠标也不收，且状态进 settings（下次开屏恢复）。"""
    rail = win.nav_rail
    assert rail.is_pinned() is False
    rail._pin_btn.click()
    assert rail.is_pinned() is True
    assert rail.is_expanded() is True
    QApplication.sendEvent(rail, QEvent(QEvent.Type.Leave))
    assert rail.is_expanded() is True          # 移走不收
    assert win.settings.nav_rail_pinned is True

    rail._pin_btn.click()
    QApplication.sendEvent(rail, QEvent(QEvent.Type.Leave))
    assert rail.is_pinned() is False
    assert rail.is_expanded() is False
    assert win.settings.nav_rail_pinned is False


def test_rail_set_pinned_restore_path(win):
    """启动恢复路径：emit=False 不触发保存信号，animate=False 不甩动画。"""
    rail = win.nav_rail
    got: list = []
    rail.pin_toggled.connect(got.append)
    rail.set_pinned(True, emit=False, animate=False)
    assert got == []
    assert rail.is_pinned() is True
    assert rail.width() == rail.expanded_width()
    assert rail._buttons[0].text() == "流量"
    # 用户真实点击（走 toggled）才发信号
    rail._pin_btn.click()
    assert got == [False]
    rail._pin_btn.click()
    assert got == [False, True]


def test_rail_set_pinned_expands_immediately(win):
    """回归：钉住必须立刻展开到位。

    初版 set_pinned 里按钮的 toggled 回调先按默认方式（带动画）展开，等
    set_pinned 自己按 animate=False 再置状态时已成了同状态 no-op——宽度停在
    收起值，钉了跟没钉一样。
    """
    rail = win.nav_rail
    rail.set_pinned(True, animate=False)
    assert rail.width() == rail.expanded_width()
    rail.set_pinned(False, animate=False)
    assert rail.width() == COLLAPSED_WIDTH


def test_rail_shortcut_hints_in_tooltips(qapp):
    rail = NavRail()
    rail.add_page(rail.style().standardIcon(
        rail.style().StandardPixmap.SP_ComputerIcon),
        rail.style().standardIcon(
            rail.style().StandardPixmap.SP_ComputerIcon), "统计")
    rail.finish()
    rail.set_shortcut_hints(["Ctrl+7"])
    assert rail._buttons[0].toolTip() == "统计（Ctrl+7）"
    rail.deleteLater()


def test_nav_shortcuts_registered_and_work(win):
    """Ctrl+1…7 已注册且能真的切页。"""
    from PySide6.QtGui import QShortcut

    shortcuts = {
        sc.key().toString(): sc
        for sc in win.findChildren(QShortcut)
        if sc.key().toString().startswith("Ctrl+")
        and sc.key().toString()[-1].isdigit()
    }
    for i in range(1, win.tabs.count() + 1):
        assert f"Ctrl+{i}" in shortcuts
    win.tabs.setCurrentIndex(0)
    shortcuts["Ctrl+7"].activated.emit()
    assert win.tabs.currentIndex() == 6
    shortcuts["Ctrl+2"].activated.emit()
    assert win.tabs.currentIndex() == 1
