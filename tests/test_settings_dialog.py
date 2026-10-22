"""设置对话框（app/ui/settings_dialog.py）与主窗口接线的单元测试。

覆盖：
1. 对话框按当前 settings 回填各控件、values() 交出编辑结果；
2. 主窗口 _apply_settings：确认后落盘 + 工具栏/菜单/详情页同步；
3. _open_settings 接线：取消不读 values、确认才应用；
4. 运行中改代理端口走「询问是否重启」通路（dialogs.question 打桩）；
5. 语言切换弹重启提示（dialogs.information 打桩，避免 offscreen 模态挂死）。
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QDialog,
    QMessageBox,
)

from app import settings as settings_mod
from app.settings import Settings
from app.ui import dialogs
from app.ui.main_window import MainWindow
from app.ui.settings_dialog import SettingsDialog


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def window(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    win = MainWindow(restore_prompt=False)
    yield win
    win.proxy.stop()


def _values(**over) -> dict:
    """主窗口 _apply_settings 的完整入参（默认值与 Settings 默认值一致）。"""
    base = {
        "proxy_port": 8888,
        "cert_port": 8081,
        "auto_system_proxy": True,
        "max_flows": 5000,
        "auto_scroll": True,
        "newest_first": False,
        "body_wrap": True,
        "theme": "system",
        "language": "zh_CN",
        "auto_save_session": False,
        "check_update_on_startup": True,
    }
    base.update(over)
    return base


# ====================================================================== 对话框本身


class TestDialogFillsFromSettings:
    def test_values_roundtrip_current_settings(self, qapp):
        s = Settings(
            proxy_port=9099,
            cert_port=9092,
            max_flows=200,
            auto_scroll=False,
            newest_first=True,
            body_wrap=False,
            auto_system_proxy=False,
            theme="dark",
            language="en",
            auto_save_session=True,
            check_update_on_startup=False,
        )
        dlg = SettingsDialog(s)
        try:
            assert dlg.proxy_port_spin.value() == 9099
            assert dlg.cert_port_spin.value() == 9092
            assert dlg.limit_combo.currentData() == 200
            assert dlg.auto_scroll_cb.isChecked() is False
            assert dlg.newest_first_cb.isChecked() is True
            assert dlg.body_wrap_cb.isChecked() is False
            assert dlg.sysproxy_cb.isChecked() is False
            assert dlg.theme_combo.currentData() == "dark"
            assert dlg.lang_combo.currentData() == "en"
            assert dlg.autosave_cb.isChecked() is True
            assert dlg.check_update_cb.isChecked() is False

            # values() 与回填一致（改回去再交还）
            assert dlg.values() == {
                "proxy_port": 9099,
                "cert_port": 9092,
                "auto_system_proxy": False,
                "max_flows": 200,
                "auto_scroll": False,
                "newest_first": True,
                "body_wrap": False,
                "theme": "dark",
                "language": "en",
                "auto_save_session": True,
                "check_update_on_startup": False,
                # 断点：默认「请求前暂停 + 不限制 URL」
                "breakpoint": {
                    "on_request": True,
                    "on_response": False,
                    "url_keywords": [],
                },
                # MCP：默认只监听本机 8899，写操作默认关
                "mcp_host": "127.0.0.1",
                "mcp_port": 8899,
                "mcp_write_enabled": False,
            }
        finally:
            dlg.deleteLater()

    def test_port_spin_blocks_arrows_and_wheel(self, qapp):
        dlg = SettingsDialog(Settings())
        try:
            spin = dlg.proxy_port_spin
            # 无上下微调按钮（误点改端口太容易）
            assert spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
            assert spin.maximum() == 65535 and spin.minimum() == 1024
            # 滚轮事件被丢弃：值不变
            from PySide6.QtCore import QPoint, QPointF
            from PySide6.QtGui import QWheelEvent

            before = spin.value()
            spin.wheelEvent(
                QWheelEvent(
                    QPointF(10, 10),          # pos
                    QPointF(10, 10),          # globalPos
                    QPoint(0, 0),             # pixelDelta
                    QPoint(0, 120),           # angleDelta
                    Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier,
                    Qt.ScrollPhase.NoScrollPhase,
                    False,
                )
            )
            assert spin.value() == before
        finally:
            dlg.deleteLater()

    def test_category_switch_shows_matching_page(self, qapp):
        dlg = SettingsDialog(Settings())
        try:
            assert dlg.pages.currentIndex() == 0
            dlg.category_list.setCurrentRow(3)      # 「会话」
            assert dlg.pages.currentIndex() == 3
            dlg.category_list.setCurrentRow(1)      # 「流量列表」
            assert dlg.pages.currentIndex() == 1
        finally:
            dlg.deleteLater()


# ====================================================================== 主窗口应用


class TestApplySettings:
    def test_apply_updates_settings_saves_and_syncs_ui(
        self, window, tmp_path
    ):
        dlg = SettingsDialog(window.settings)
        dlg.proxy_port_spin.setValue(19081)
        dlg.cert_port_spin.setValue(18082)
        dlg.limit_combo.setCurrentIndex(dlg.limit_combo.findData(100))
        dlg.auto_scroll_cb.setChecked(False)
        dlg.newest_first_cb.setChecked(True)
        dlg.body_wrap_cb.setChecked(False)
        dlg.sysproxy_cb.setChecked(False)
        dlg.theme_combo.setCurrentIndex(dlg.theme_combo.findData("dark"))
        dlg.autosave_cb.setChecked(True)
        dlg.check_update_cb.setChecked(False)
        values = dlg.values()
        dlg.deleteLater()

        window._apply_settings(values)

        # -- 内存设置
        assert window.settings.proxy_port == 19081
        assert window.settings.cert_port == 18082
        assert window.settings.max_flows == 100
        assert window.settings.auto_scroll is False
        assert window.settings.newest_first is True
        assert window.settings.body_wrap is False
        assert window.settings.auto_system_proxy is False
        assert window.settings.theme == "dark"
        assert window.settings.auto_save_session is True
        assert window.settings.check_update_on_startup is False

        # -- 落盘（settings.json 是单一事实源）
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["proxy_port"] == 19081
        assert saved["cert_port"] == 18082
        assert saved["max_flows"] == 100
        assert saved["newest_first"] is True
        assert saved["theme"] == "dark"
        assert saved["auto_save_session"] is True
        assert saved["check_update_on_startup"] is False

        # -- 工具栏 / 菜单 / 详情页同步（界面即真相；端口已无工具栏控件，
        #    以 settings 与代理按钮提示为准）
        assert window.settings.proxy_port == 19081
        assert window.settings.cert_port == 18082
        assert "19081" in window.proxy_btn.toolTip()
        assert window.limit_combo.currentData() == 100
        assert window.auto_scroll_cb.isChecked() is False
        assert window.order_combo.currentData() is True
        assert window.sysproxy_cb.isChecked() is False
        assert window.autosave_action.isChecked() is True
        assert window._theme_actions["dark"].isChecked()
        assert window.detail_panel.wrap_default is False

        # -- 保存条数真正裁到列表与捕获缓存
        assert window.flow_store.max_rows == 100
        assert window.capture._max_flows == 100

    def test_apply_same_values_is_noop(self, window, tmp_path):
        # 默认值全量应用一遍：不崩、不写坏文件、界面不动
        window._apply_settings(_values())
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["proxy_port"] == 8888
        assert saved["max_flows"] == 5000
        assert window.settings.proxy_port == 8888
        assert window._theme_actions["system"].isChecked()

    def test_body_wrap_pushed_to_detail_panel(self, window):
        window._apply_settings(_values(body_wrap=False))
        assert window.settings.body_wrap is False
        # 详情页当前各 Body 面板的「换行」勾选框跟着掉
        assert window.detail_panel.request_pane.body_pane.wrap_cb.isChecked() is False
        assert window.detail_panel.response_pane.body_pane.wrap_cb.isChecked() is False


class TestOpenSettingsWiring:
    def test_cancel_does_not_apply(self, window, monkeypatch):
        class _RejectedDlg:
            def __init__(self, settings, parent=None):
                pass

            def exec(self):
                return QDialog.DialogCode.Rejected

            def values(self):
                raise AssertionError("取消后不应读取编辑结果")

        monkeypatch.setattr("app.ui.main_window.SettingsDialog", _RejectedDlg)
        window._open_settings()
        assert window.settings.proxy_port == 8888
        assert window.settings.max_flows == 5000

    def test_accept_applies_values(self, window, monkeypatch):
        class _AcceptedDlg:
            def __init__(self, settings, parent=None):
                pass

            def exec(self):
                return QDialog.DialogCode.Accepted

            def values(self):
                return _values(proxy_port=19083, max_flows=1000)

        monkeypatch.setattr("app.ui.main_window.SettingsDialog", _AcceptedDlg)
        window._open_settings()
        assert window.settings.proxy_port == 19083
        assert "19083" in window.proxy_btn.toolTip()
        assert window.settings.max_flows == 1000
        assert window.limit_combo.currentData() == 1000

    def test_language_switch_prompts_restart(self, window, monkeypatch):
        shown = []
        monkeypatch.setattr(
            dialogs, "information", lambda *a, **k: shown.append(a)
        )
        window._apply_settings(_values(language="en"))
        assert window.settings.language == "en"
        assert window._lang_actions["en"].isChecked()
        assert shown and "重启" in shown[0][2]

    def test_language_same_value_no_prompt(self, window, monkeypatch):
        shown = []
        monkeypatch.setattr(
            dialogs, "information", lambda *a, **k: shown.append(a)
        )
        window._apply_settings(_values(language="zh_CN"))
        assert not shown


class TestPortChangeWhileRunning:
    """运行中改端口（设置对话框确认后）：询问是否立即重启。"""

    def _fake_running_proxy(self, window, monkeypatch):
        class _Running:
            running = True

            def stop(self, timeout=None):
                pass

        monkeypatch.setattr(window, "proxy", _Running())

    def test_running_asks_restart_and_no_keeps_new_port(self, window, monkeypatch):
        self._fake_running_proxy(window, monkeypatch)
        asked = []
        monkeypatch.setattr(
            dialogs,
            "question",
            lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.No,
        )
        window._apply_settings(_values(proxy_port=19084))
        assert asked, "运行中改端口应询问是否重启"
        assert window.settings.proxy_port == 19084     # 否 = 下次启动生效
        assert "19084" in window.proxy_btn.toolTip()

    def test_running_yes_restarts_app(self, window, monkeypatch):
        self._fake_running_proxy(window, monkeypatch)
        monkeypatch.setattr(
            dialogs,
            "question",
            lambda *a, **k: QMessageBox.StandardButton.Yes,
        )
        restarted = []
        monkeypatch.setattr(
            window, "_restart_app_for_port", lambda port: restarted.append(port)
        )
        window._apply_settings(_values(proxy_port=19085))
        assert restarted == [19085]


# ====================================================================== MCP 监听地址


class TestMcpHostSettings:
    def test_defaults_to_localhost(self, qapp):
        dlg = SettingsDialog(Settings())
        try:
            assert dlg.mcp_host_combo.currentData() == "127.0.0.1"
            assert dlg.mcp_port_spin.value() == 8899
            assert dlg.values()["mcp_host"] == "127.0.0.1"
            assert "局域网" not in dlg.mcp_exposed_hint.text()
        finally:
            dlg.deleteLater()

    def test_choose_wildcard_warns_and_travels(self, qapp):
        dlg = SettingsDialog(Settings())
        try:
            datas = [dlg.mcp_host_combo.itemData(i)
                     for i in range(dlg.mcp_host_combo.count())]
            assert datas[:2] == ["127.0.0.1", "0.0.0.0"]
            dlg.mcp_host_combo.setCurrentIndex(1)
            assert dlg.values()["mcp_host"] == "0.0.0.0"
            # 安全提示必须当场变脸，不能只在 tooltip 里藏着
            assert "警告" in dlg.mcp_exposed_hint.text()
            # 切回仅本机，提示也要恢复
            dlg.mcp_host_combo.setCurrentIndex(0)
            assert "警告" not in dlg.mcp_exposed_hint.text()
        finally:
            dlg.deleteLater()

    def test_manual_ip_is_kept(self, qapp):
        dlg = SettingsDialog(Settings(mcp_host="192.168.1.7", mcp_port=9100))
        try:
            assert dlg.mcp_host_combo.currentText() == "192.168.1.7"
            assert dlg.values()["mcp_host"] == "192.168.1.7"
            assert dlg.values()["mcp_port"] == 9100
        finally:
            dlg.deleteLater()

    def test_apply_updates_host_without_starting(self, window):
        """改地址≠开服务：MCP 默认关，改配置不该偷偷起端口。"""
        window._apply_settings(_values(mcp_host="0.0.0.0", mcp_port=9101))
        assert window.settings.mcp_host == "0.0.0.0"
        assert window.settings.mcp_port == 9101
        assert not window.mcp.running
        assert window.mcp.host == "0.0.0.0" or window.mcp.host == "127.0.0.1"
