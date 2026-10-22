"""网络模拟面板 + 持久化 + 主窗口接线（offscreen Qt）。

纯函数逻辑在 test_network.py；这里盯三件容易出错的事：
1. 面板值 ↔ 配置对象的双向一致（含"档位 vs 自定义"的切换语义）；
2. settings.json 往返（弱网档位 + 域名映射规则）；
3. 主窗口把配置正确推给代理：addon 齐、map_remote 选项带上、改动即时落盘。
"""

import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-network-panel-test-home")

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


from addons.throttle import ThrottleAddon  # noqa: E402
from app import settings as settings_mod  # noqa: E402
from app.network import MAP_SPEC_SEP, MapRule, ThrottleConfig  # noqa: E402
from app.settings import Settings, load_settings, save_settings  # noqa: E402
from app.ui.network_panel import NetworkPanel  # noqa: E402


# ====================================================================== 面板


class TestPanel:
    def test_load_config_reflects_values(self):
        panel = NetworkPanel()
        panel.load_config(
            ThrottleConfig(preset="custom", latency_ms=250, rate_kbps=512),
            [MapRule("api.prod.com", "127.0.0.1:8080"), MapRule("x.test", "127.0.0.1:9", enabled=False)],
        )
        cfg = panel.to_throttle()
        assert (cfg.preset, cfg.latency_ms, cfg.rate_kbps) == ("custom", 250, 512)
        rules = panel.to_rules()
        assert [(r.source, r.target, r.enabled) for r in rules] == [
            ("api.prod.com", "127.0.0.1:8080", True),
            ("x.test", "127.0.0.1:9", False),
        ]
        assert panel.map_table.rowCount() == 2

    def test_preset_switch_fills_numbers_and_disables_custom(self):
        panel = NetworkPanel()
        idx = panel.preset_combo.findData("3g")
        panel.preset_combo.setCurrentIndex(idx)
        cfg = panel.to_throttle()
        assert (cfg.latency_ms, cfg.rate_kbps) == (200, 400)
        assert not panel.latency_spin.isEnabled()
        assert not panel.rate_spin.isEnabled()

    def test_off_preset_is_disabled(self):
        panel = NetworkPanel()
        panel.load_config(ThrottleConfig(preset="off"), [])
        assert not panel.to_throttle().enabled
        assert "未启用" in panel.throttle_state.text()

    def test_editing_numbers_switches_to_custom(self):
        """手改数字若不切到「自定义」，下次加载会被档位表覆盖，用户会觉得"改了没用"。"""
        panel = NetworkPanel()
        panel.preset_combo.setCurrentIndex(panel.preset_combo.findData("3g"))
        assert panel.preset_combo.currentData() == "3g"
        panel.latency_spin.setValue(1234)
        assert panel.preset_combo.currentData() == "custom"
        assert panel.latency_spin.isEnabled()
        cfg = panel.to_throttle()
        assert (cfg.preset, cfg.latency_ms) == ("custom", 1234)
        assert cfg.enabled

    def test_add_and_delete_rows(self):
        panel = NetworkPanel()
        panel.load_config(ThrottleConfig(), [])
        panel.add_btn.click()
        assert panel.map_table.rowCount() == 1
        panel.map_table.item(0, 1).setText("api.prod.com")
        panel.map_table.item(0, 2).setText("127.0.0.1:8080")
        panel.add_btn.click()
        panel.map_table.item(1, 1).setText("gw.prod.com")
        panel.map_table.item(1, 2).setText("127.0.0.1:8081")
        assert [r.source for r in panel.to_rules()] == ["api.prod.com", "gw.prod.com"]

        panel.map_table.selectRow(0)
        panel.del_btn.click()
        assert [r.source for r in panel.to_rules()] == ["gw.prod.com"]

    def test_checkbox_toggles_enabled(self):
        panel = NetworkPanel()
        panel.load_config(ThrottleConfig(), [MapRule("a.test", "127.0.0.1:1")])
        assert panel.to_rules()[0].enabled is True
        panel.map_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        assert panel.to_rules()[0].enabled is False

    def test_invalid_row_marked_and_reported(self):
        panel = NetworkPanel()
        panel.load_config(ThrottleConfig(), [MapRule("a.test", "不是目标")])
        item = panel.map_table.item(0, 1)
        assert item.background().color().isValid() and item.background().style() != Qt.BrushStyle.NoBrush
        assert "填写不完整" in panel.map_state.text()

    def test_empty_row_not_marked_invalid(self):
        panel = NetworkPanel()
        panel.load_config(ThrottleConfig(), [])
        panel.add_btn.click()                     # 空行
        assert panel.map_table.item(0, 1).background().style() == Qt.BrushStyle.NoBrush
        assert "填写不完整" not in panel.map_state.text()

    def test_changed_signal_fires_on_edits(self):
        panel = NetworkPanel()
        panel.load_config(ThrottleConfig(), [])
        seen = []
        panel.changed.connect(lambda: seen.append(1))
        panel.preset_combo.setCurrentIndex(panel.preset_combo.findData("3g"))
        panel.add_btn.click()
        panel.map_table.item(0, 1).setText("a.test")
        assert len(seen) >= 3

    def test_load_config_does_not_emit_changed(self):
        """加载配置（灌初始值）不能当成用户编辑，否则启动时会反手覆盖用户配置。"""
        panel = NetworkPanel()
        seen = []
        panel.changed.connect(lambda: seen.append(1))
        panel.load_config(
            ThrottleConfig(preset="custom", latency_ms=100, rate_kbps=100),
            [MapRule("a.test", "127.0.0.1:1")],
        )
        assert seen == []

    def test_status_text(self):
        panel = NetworkPanel()
        panel.set_status("已立即生效")
        assert panel.status_label.text() == "已立即生效"

    def test_enabled_summary_text(self):
        panel = NetworkPanel()
        panel.load_config(ThrottleConfig(preset="3g"), [])
        assert "延迟 200 ms" in panel.throttle_state.text()
        assert "限速 400 kbps" in panel.throttle_state.text()


# ====================================================================== 持久化


class TestSettingsPersistence:
    def test_throttle_and_rules_roundtrip(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
        s = Settings(
            throttle=ThrottleConfig(preset="custom", latency_ms=321, rate_kbps=654),
            map_rules=[MapRule("api.prod.com", "127.0.0.1:8080"), MapRule("b.test", "127.0.0.1:2", enabled=False)],
        )
        save_settings(s)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["throttle"] == {"preset": "custom", "latency_ms": 321, "rate_kbps": 654}
        assert raw["map_remote"][0] == {"source": "api.prod.com", "target": "127.0.0.1:8080", "enabled": True}

        again = load_settings()
        assert again.throttle.preset == "custom"
        assert again.throttle.latency_ms == 321
        assert [(r.source, r.enabled) for r in again.map_rules] == [
            ("api.prod.com", True), ("b.test", False),
        ]

    def test_defaults_when_keys_missing(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        path.write_text('{"proxy_port": 9999}', encoding="utf-8")
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
        s = load_settings()
        assert s.throttle.preset == "off"
        assert s.map_rules == []
        # 缺键时的缺省必须与字段默认值一致（from_dict 曾用 True，与
        # dataclass 的 False 打架：全新装默认关、老用户升级默认开）
        assert s.auto_save_session is False
        assert s.auto_save_session == Settings().auto_save_session

    def test_junk_in_map_rules_ignored(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps({"map_remote": [None, "x", {"source": "a.test", "target": "127.0.0.1:1"}]}),
            encoding="utf-8",
        )
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
        assert [r.source for r in load_settings().map_rules] == ["a.test"]


# ====================================================================== 主窗口接线


@pytest.fixture()
def window(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    from app.ui.main_window import MainWindow

    win = MainWindow(restore_prompt=False)
    yield win
    win.proxy.stop()


class TestMainWindowWiring:
    def test_proxy_has_all_addons(self, window):
        from addons.capture import CaptureAddon
        from addons.mock import MockAddon

        kinds = [type(a) for a in window.proxy._addons]
        assert MockAddon in kinds
        assert CaptureAddon in kinds
        assert ThrottleAddon in kinds

    def test_proxy_built_from_saved_rules(self, window, tmp_path, monkeypatch):
        window.settings.map_rules = [MapRule("api.prod.com", "127.0.0.1:8080")]
        proxy = window._make_proxy(18080)
        specs = proxy._options["map_remote"]
        assert len(specs) == 1
        # spec 形如 "<sep>^https?://api\.prod\.com(?::\d+)?/<sep>http://127.0.0.1:8080/"
        subject, replacement = specs[0].split(MAP_SPEC_SEP)[1:3]
        assert replacement == "http://127.0.0.1:8080/"

        # mitmproxy MapRemote 就是 re.sub(subject, replacement, pretty_url)：
        # 只改写 scheme + 域名 + 端口，路径与 query 原样保留
        assert (
            re.sub(subject, replacement, "https://api.prod.com/v1/u?id=1")
            == "http://127.0.0.1:8080/v1/u?id=1"
        )
        # 显式带端口也能命中
        assert (
            re.sub(subject, replacement, "http://api.prod.com:8443/v1")
            == "http://127.0.0.1:8080/v1"
        )
        # 域名里的 . 已转义成字面量：apiXprodYcom 不能被误伤
        assert (
            re.sub(subject, replacement, "https://apiXprodYcom/v1")
            == "https://apiXprodYcom/v1"
        )

    def test_panel_change_persists_and_pushes_to_addon(self, window, tmp_path):
        panel = window.network_panel
        panel.preset_combo.setCurrentIndex(panel.preset_combo.findData("custom"))
        panel.latency_spin.setValue(300)
        panel.rate_spin.setValue(200)
        panel.add_btn.click()
        panel.map_table.item(0, 1).setText("api.prod.com")
        panel.map_table.item(0, 2).setText("127.0.0.1:8080")

        # 限速即刻推给 addon（代理没启动也能生效）
        assert window.throttle.config.latency_ms == 300
        assert window.throttle.config.rate_kbps == 200

        # 落盘
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["throttle"]["latency_ms"] == 300
        assert saved["map_remote"][0]["source"] == "api.prod.com"

        # 域名映射：代理未启动 → 记在 options 里，等启动生效
        assert window.proxy._options["map_remote"]
        assert "弱网" in window.network_panel.status_label.text()
        assert "代理启动后生效" in window.network_panel.status_label.text()

    def test_status_bar_mentions_throttle(self, window):
        panel = window.network_panel
        panel.preset_combo.setCurrentIndex(panel.preset_combo.findData("3g"))
        assert "弱网模拟中" in window.count_label.text()

    def test_disabling_clears_mapping_and_mention(self, window):
        panel = window.network_panel
        panel.preset_combo.setCurrentIndex(panel.preset_combo.findData("3g"))
        assert window.throttle.config.enabled
        panel.preset_combo.setCurrentIndex(panel.preset_combo.findData("off"))
        assert not window.throttle.config.enabled
        assert "弱网模拟中" not in window.count_label.text()

    def test_saved_settings_applied_on_startup(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps({
                "throttle": {"preset": "3g", "latency_ms": 200, "rate_kbps": 400},
                "map_remote": [{"source": "api.prod.com", "target": "127.0.0.1:8080", "enabled": True}],
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
        from app.ui.main_window import MainWindow

        win = MainWindow(restore_prompt=False)
        try:
            assert win.throttle.config.preset == "3g"
            assert win.proxy._options["map_remote"]
            assert win.network_panel.map_table.rowCount() == 1
            assert "弱网模拟中" in win.count_label.text()
        finally:
            win.proxy.stop()
