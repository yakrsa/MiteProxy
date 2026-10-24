"""多套过滤预设测试（路线图 #7）。"""

import pytest
from PySide6.QtWidgets import QApplication

from app.settings import Settings
from app.ui.filter_model import FilterConfig
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


def _config(keywords=("a.test",), mode="blacklist", hide_image=True):
    return FilterConfig(
        blacklist=list(keywords) if mode == "blacklist" else [],
        whitelist=list(keywords) if mode == "whitelist" else [],
        enabled=True,
        active_list=mode,
        hide_image=hide_image,
    )


# ---------------------------------------------------------------- 设置层


def test_settings_presets_roundtrip():
    s = Settings()
    s.filter_presets = [
        {"name": "只看 A", "config": _config(("a.test",)).to_dict()},
        {"name": "只看 B", "config": _config(("b.test",), "whitelist").to_dict()},
    ]
    s.active_preset = "只看 A"
    d = s.to_dict()
    restored = Settings.from_dict(d)
    assert [p["name"] for p in restored.filter_presets] == ["只看 A", "只看 B"]
    assert restored.active_preset == "只看 A"
    assert restored.filter_presets[0]["config"]["blacklist"] == ["a.test"]


def test_settings_presets_sanitize():
    s = Settings.from_dict({
        "filter_presets": [
            {"name": "ok", "config": {"blacklist": ["x"]}},
            {"name": ""},                      # 无名 → 丢
            "not a dict",                      # 坏类型 → 丢
            {"name": "ok", "config": {}},      # 重名 → 丢后者
            {"name": "bad-list", "config": {"active_list": "nope"}},
            {"name": "legacy", "config": {"host_mode": "whitelist",
                                          "host_keywords": ["old.test"]}},
        ],
    })
    names = [p["name"] for p in s.filter_presets]
    assert names == ["ok", "bad-list", "legacy"]
    # 非法 active_list 被收敛成 blacklist（FilterConfig.from_dict 的职责）
    assert s.filter_presets[1]["config"]["active_list"] == "blacklist"
    # 旧版 host_mode/host_keywords 迁进白名单
    assert s.filter_presets[2]["config"]["whitelist"] == ["old.test"]
    assert s.filter_presets[2]["config"]["enabled"] is True


def test_settings_presets_default_empty():
    assert Settings.from_dict({}).filter_presets == []
    assert Settings.from_dict({}).active_preset == ""


# ---------------------------------------------------------------- 主窗口


def test_save_preset_persists_and_activates(window):
    window.settings.filter = _config()
    window._save_preset("线上域名")

    assert [p["name"] for p in window.settings.filter_presets] == ["线上域名"]
    assert window.settings.active_preset == "线上域名"
    assert window.settings.filter_presets[0]["config"]["blacklist"] == ["a.test"]

    from app.settings import load_settings

    assert [p["name"] for p in load_settings().filter_presets] == ["线上域名"]


def test_save_preset_same_name_overwrites(window):
    window.settings.filter = _config(("a.test",))
    window._save_preset("P")
    window.settings.filter = _config(("b.test",))
    window._save_preset("P")
    assert len(window.settings.filter_presets) == 1
    assert window.settings.filter_presets[0]["config"]["blacklist"] == ["b.test"]


def test_apply_preset_loads_into_bar_and_model(window):
    window.settings.filter_presets = [
        {"name": "whitelist-B", "config": _config(("b.test",), "whitelist",
                                                 hide_image=False).to_dict()},
    ]
    window._apply_preset("whitelist-B")

    assert window.settings.active_preset == "whitelist-B"
    # 栏位控件同步（模式 / 关键词 / 勾选框）
    assert window.filter_bar.mode_combo.currentData() == "whitelist"
    assert window.filter_bar.keywords_edit.text() == "b.test"
    assert not window.filter_bar.hide_image_cb.isChecked()
    # 代理模型也拿到同一份配置
    assert window.proxy_model.filter_config.whitelist == ["b.test"]
    assert window.proxy_model.filter_config.active_list == "whitelist"
    assert window.proxy_model.filter_config.is_active()


def test_apply_unknown_preset_is_noop(window):
    window._apply_preset("不存在")
    assert window.settings.active_preset == ""


def test_manual_edit_clears_active_preset(window):
    window.settings.filter_presets = [
        {"name": "P", "config": _config().to_dict()},
    ]
    window.settings.filter = _config()
    window.settings.active_preset = "P"

    # 用户手改关键词 → 偏离预设 → active 清掉（预设本身保留）
    window.filter_bar.keywords_edit.setText("other.test")
    assert window.settings.active_preset == ""
    assert [p["name"] for p in window.settings.filter_presets] == ["P"]


def test_manual_edit_matching_preset_keeps_active(window):
    window.settings.filter_presets = [
        {"name": "P", "config": _config().to_dict()},
    ]
    window.settings.filter = _config()
    window.settings.active_preset = "P"
    window.filter_bar.load_config(window.settings.filter)   # 栏位与预设一致
    window._on_filter_changed()      # 配置没变，重新触发一遍
    assert window.settings.active_preset == "P"


def test_update_and_delete_preset(window):
    window.settings.filter_presets = [
        {"name": "P", "config": _config(("a.test",)).to_dict()},
    ]
    window.settings.active_preset = "P"
    window.settings.filter = _config(("c.test",))

    window._update_preset("P")
    assert window.settings.filter_presets[0]["config"]["blacklist"] == ["c.test"]

    window._delete_preset("P")
    assert window.settings.filter_presets == []
    assert window.settings.active_preset == ""      # 删的是当前套用的 → 清标记


def test_preset_menu_lists_presets_with_checks(window):
    window.settings.filter_presets = [
        {"name": "A", "config": _config(("a.test",)).to_dict()},
        {"name": "B", "config": _config(("b.test",)).to_dict()},
    ]
    window.settings.active_preset = "B"
    # 栏位加载 B 的配置 → 未偏离，菜单里不该出现「已修改」
    window.filter_bar.load_config(
        FilterConfig.from_dict(window.settings.filter_presets[1]["config"])
    )
    window._rebuild_preset_menu()
    actions = window.filter_bar.preset_menu.actions()
    labels = [a.text() for a in actions]
    assert "A" in labels and "B" in labels
    checked = [a.text() for a in actions if a.isCheckable() and a.isChecked()]
    assert checked == ["B"]
    # 有 active 时才有更新/删除项
    assert any("更新预设" in t for t in labels)
    assert any("删除预设" in t for t in labels)


def test_preset_menu_dirty_marker(window):
    window.settings.filter_presets = [
        {"name": "A", "config": _config(("a.test",)).to_dict()},
    ]
    window.settings.active_preset = "A"
    # 当前过滤条件与预设不同 → 菜单里标「已修改」
    window.settings.filter = _config(("zzz.test",))
    window._rebuild_preset_menu()
    label = next(a.text() for a in window.filter_bar.preset_menu.actions()
                 if a.isCheckable())
    assert "已修改" in label


def test_preset_menu_empty_state(window):
    window.settings.filter_presets = []
    window._rebuild_preset_menu()
    texts = [a.text() for a in window.filter_bar.preset_menu.actions()]
    assert any("没有预设" in t for t in texts)
    # 空状态也有「保存」入口
    assert any("保存当前过滤为预设" in t for t in texts)


def test_filter_bar_loads_persisted_config_on_startup(qapp, tmp_path, monkeypatch):
    """重启后过滤栏控件与持久化配置一致（修过的不同步 bug 的回归防护）。"""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    win1 = MainWindow(restore_prompt=False)
    win1.filter_bar.mode_combo.setCurrentIndex(
        win1.filter_bar.mode_combo.findData("whitelist")
    )
    win1.filter_bar.keywords_edit.setText("keep.test")
    win1.close()

    win2 = MainWindow(restore_prompt=False)
    try:
        assert win2.filter_bar.mode_combo.currentData() == "whitelist"
        assert win2.filter_bar.keywords_edit.text() == "keep.test"
        assert win2.proxy_model.filter_config.whitelist == ["keep.test"]
        assert win2.proxy_model.filter_config.enabled is True
    finally:
        win2.close()
