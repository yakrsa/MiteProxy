"""主题模块（app/ui/theme.py）：token 完整性、动态色就地更新、监听者生命周期、
设置往返与主窗口外观菜单接线（v1.14）。"""

import json

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel

from app.ui import theme


@pytest.fixture(autouse=True)
def _restore_theme_mode():
    """单测改过全局主题档位后恢复跟随系统，不污染别的用例。"""
    yield
    theme.apply("system")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _RethemeTarget(QLabel):
    """提供真绑定方法的小控件（theme.add_listener 要求绑定方法）。"""

    def __init__(self):
        super().__init__()
        self.seen = 0

    def _retheme(self) -> None:
        self.seen += 1


class TestTokens:
    def test_every_token_has_two_valid_variants(self):
        for key, (light, dark) in theme.COLORS.items():
            assert QColor(light).isValid(), key
            assert QColor(dark).isValid(), key
            if key == "sel_fg":
                continue  # 选中行文字深浅两套都刻意用白色（蓝底上最清晰）
            assert light != dark, f"{key} 两套值不应相同"

    def test_color_and_css_follow_mode(self):
        theme.apply("dark")
        assert theme.css("ok") == theme.COLORS["ok"][1].lower()
        theme.apply("light")
        assert theme.css("ok") == theme.COLORS["ok"][0].lower()

    def test_unknown_key_falls_back_to_hint(self):
        theme.apply("light")
        assert theme.color("nope").name() == theme.COLORS["hint"][0].lower()

    def test_selection_colors_explicit_not_palette_ref(self):
        """浅色模式选中行看不见的回归：选中色必须是显式 token 取色。

        旧实现 `selection-background-color: palette(highlight)` 在 macOS
        原生样式下与 highlighted-text 不同步（浅底配白字 → 整行隐形）。
        """
        theme.apply("light")
        sheet = theme.stylesheet()
        assert theme.COLORS["sel_bg"][0].lower() in sheet
        assert "palette(highlight)" not in sheet
        theme.apply("dark")
        sheet = theme.stylesheet()
        assert theme.COLORS["sel_bg"][1].lower() in sheet
        assert "palette(highlight)" not in sheet


class TestDynamicColor:
    def test_dynamic_color_updates_in_place(self):
        qc = theme.dynamic("mock_row_bg")
        light = QColor(theme.COLORS["mock_row_bg"][0])
        assert qc == light
        theme.apply("dark")
        assert qc == QColor(theme.COLORS["mock_row_bg"][1])
        theme.apply("light")
        assert qc == light

    def test_bad_mode_falls_back_to_system(self):
        theme.apply("nope")
        assert theme.current_mode() == "system"


class TestListeners:
    def test_bound_method_listener_called_and_cleaned(self, qapp):
        import gc

        t = _RethemeTarget()
        theme.add_listener(t._retheme)
        theme.notify()
        assert t.seen == 1
        # 控件被回收后 WeakMethod 失效：notify 不报错并顺手清掉死引用
        before = len(theme._listeners)
        del t
        gc.collect()
        theme.notify()
        assert len(theme._listeners) == before - 1

    def test_listener_exception_does_not_break_others(self, qapp):
        class _Bad(_RethemeTarget):
            def _retheme(self) -> None:
                raise RuntimeError("boom")

        t_bad = _Bad()
        t_ok = _RethemeTarget()
        theme.add_listener(t_bad._retheme)
        theme.add_listener(t_ok._retheme)
        theme.notify()      # 不应抛异常，后续监听者照常执行
        assert t_ok.seen == 1


class TestSettingsRoundtrip:
    def test_theme_field_roundtrip(self, tmp_path, monkeypatch):
        from app import settings as settings_mod
        from app.settings import Settings, load_settings, save_settings

        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "s.json")
        save_settings(Settings(theme="dark"))
        assert load_settings().theme == "dark"

    def test_bad_theme_value_falls_back_to_system(self, tmp_path, monkeypatch):
        from app import settings as settings_mod
        from app.settings import load_settings

        path = tmp_path / "s.json"
        path.write_text(json.dumps({"theme": "blue"}), encoding="utf-8")
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
        assert load_settings().theme == "system"


class TestMainWindowThemeMenu:
    """外观菜单：三档互斥、默认跟随系统、选择立即落盘。"""

    @pytest.fixture()
    def window(self, monkeypatch, tmp_path):
        from app import settings as settings_mod

        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
        from app.ui.main_window import MainWindow

        win = MainWindow(restore_prompt=False)
        yield win
        win.close()

    def test_default_follows_system(self, window):
        assert window.settings.theme == "system"
        assert window._theme_actions["system"].isChecked()
        assert not window._theme_actions["dark"].isChecked()

    def test_select_dark_persists_and_checks(self, window, tmp_path):
        window._theme_actions["dark"].trigger()
        assert window.settings.theme == "dark"
        assert window._theme_actions["dark"].isChecked()
        assert not window._theme_actions["system"].isChecked()
        data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert data["theme"] == "dark"

    def test_switch_back_to_system(self, window):
        window._theme_actions["dark"].trigger()
        window._theme_actions["system"].trigger()
        assert window.settings.theme == "system"
        assert window._theme_actions["system"].isChecked()
