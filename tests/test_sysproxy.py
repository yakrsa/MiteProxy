"""系统代理接管/还原（app/sysproxy.py）+ 设置持久化 + 主窗口接线（v1.13）。"""

from __future__ import annotations

import json

import pytest
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import settings as settings_mod
from app import sysproxy

_app = QApplication.instance() or QApplication([])


# ------------------------------------------------------------------ 测试替身

class FakeRunner:
    """记录 networksetup 调用并脚本化返回值。"""

    def __init__(self, services=("Wi-Fi", "Ethernet"), fail_on=None):
        self.calls: list[list[str]] = []
        self.services = list(services)
        self.fail_on = fail_on  # 命中该子串的命令返回 rc=1
        # 原始状态：每个服务 HTTP 关、HTTPS 开指向旧代理
        self.state = {
            svc: {
                False: {"enabled": False, "server": "", "port": 0},
                True: {"enabled": True, "server": "10.0.0.1", "port": 7890},
            }
            for svc in self.services
        }

    def __call__(self, cmd, timeout=15):
        self.calls.append(cmd)
        if self.fail_on and self.fail_on in " ".join(cmd):
            return 1, "", "You do not have the administrator rights"
        if cmd[1] == "-listallnetworkservices":
            lines = ["An asterisk (*) denotes that a network service is disabled."]
            lines += self.services
            lines.append("*Disabled VPN")
            return 0, "\n".join(lines) + "\n", ""
        if cmd[1] in ("-getwebproxy", "-getsecurewebproxy"):
            svc, secure = cmd[2], cmd[1] == "-getsecurewebproxy"
            st = self.state.get(svc, {})[secure]
            out = (f"Enabled: {'Yes' if st['enabled'] else 'No'}\n"
                   f"Server: {st['server']}\nPort: {st['port']}\n")
            return 0, out, ""
        if cmd[1] in ("-setwebproxy", "-setsecurewebproxy"):
            svc, secure = cmd[2], cmd[1] == "-setsecurewebproxy"
            self.state[svc][secure] = {
                "enabled": True, "server": cmd[3], "port": int(cmd[4]),
            }
            return 0, "", ""
        if cmd[1] in ("-setwebproxystate", "-setsecurewebproxystate"):
            svc, secure = cmd[2], cmd[1] == "-setsecurewebproxystate"
            self.state[svc][secure]["enabled"] = cmd[3] == "on"
            return 0, "", ""
        return 0, "", ""


@pytest.fixture
def state_path(tmp_path, monkeypatch):
    p = tmp_path / "sysproxy.json"
    monkeypatch.setattr(sysproxy, "STATE_PATH", p)
    return p


class TestTakeover:
    def test_sets_proxy_and_records_state(self, state_path):
        r = FakeRunner()
        ok, msg = sysproxy.takeover(8080, run=r)
        assert ok
        sets = [c for c in r.calls if c[1] == "-setwebproxy"]
        secure_sets = [c for c in r.calls if c[1] == "-setsecurewebproxy"]
        # 两个服务 × HTTP/HTTPS 都指向 127.0.0.1:8080
        assert len(sets) == 2 and all(c[3:] == ["127.0.0.1", "8080"] for c in sets)
        assert len(secure_sets) == 2
        # 状态落盘
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved["port"] == 8080
        assert saved["services"]["Wi-Fi"]["secure"]["server"] == "10.0.0.1"
        assert saved["services"]["Wi-Fi"]["secure"]["enabled"] is True
        assert saved["services"]["Ethernet"]["web"]["enabled"] is False

    def test_records_original_state_not_the_new_one(self, state_path):
        r = FakeRunner()
        sysproxy.takeover(8080, run=r)
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        # 记录的是接管前的值（10.0.0.1:7890），不是接管后的 127.0.0.1
        assert saved["services"]["Wi-Fi"]["web"] == {
            "enabled": False, "server": "", "port": 0,
        }

    def test_failure_rolls_back_changed_services(self, state_path):
        r = FakeRunner(fail_on="Ethernet")  # 第二个服务设置失败
        ok, msg = sysproxy.takeover(8080, run=r)
        assert not ok
        assert "Ethernet" in msg
        # Wi-Fi 已被改过 → 必须出现对 Wi-Fi 的还原命令（关掉原关闭项）
        restore_offs = [
            c for c in r.calls
            if c[1] == "-setwebproxystate" and c[2] == "Wi-Fi" and c[3] == "off"
        ]
        assert restore_offs, "失败后未回滚 Wi-Fi 的接管"
        # 状态不落盘（没有成功接管）
        assert not state_path.exists()

    def test_no_services_fails_cleanly(self, state_path):
        r = FakeRunner(services=[])
        ok, msg = sysproxy.takeover(8080, run=r)
        assert not ok and "网络服务" in msg


class TestRestore:
    def test_restores_original_values(self, state_path):
        r = FakeRunner()
        sysproxy.takeover(8080, run=r)
        r.calls.clear()
        ok, msg = sysproxy.restore(run=r)
        assert ok
        # 原来关的 HTTP 代理 → 关掉
        assert [
            c for c in r.calls
            if c[1] == "-setwebproxystate" and c[3] == "off"
        ]
        # 原来开的 HTTPS 代理 → 写回原地址端口
        back = [c for c in r.calls if c[1] == "-setsecurewebproxy"]
        assert back and all(c[3:] == ["10.0.0.1", "7890"] for c in back)
        assert not state_path.exists()  # 用完即删

    def test_without_state_is_noop(self, state_path):
        ok, msg = sysproxy.restore(run=FakeRunner())
        assert ok and "无接管记录" in msg

    def test_missing_service_skipped(self, state_path):
        r = FakeRunner()
        sysproxy.takeover(8080, run=r)
        r.services = []  # 网卡拔了
        ok, _ = sysproxy.restore(run=r)
        assert ok and not state_path.exists()

    def test_corrupt_state_cleaned_up(self, state_path):
        state_path.write_text("not json", encoding="utf-8")
        ok, msg = sysproxy.restore(run=FakeRunner())
        assert not ok and "损坏" in msg
        assert not state_path.exists()


class TestRecovery:
    def test_recover_restores_after_crash(self, state_path):
        r = FakeRunner()
        sysproxy.takeover(8080, run=r)          # 模拟崩溃：没走 restore
        assert state_path.exists()
        ok = sysproxy.recover_if_needed(run=r)  # 下次启动补还原
        assert ok
        assert not state_path.exists()

    def test_recover_noop_without_state(self, state_path):
        assert sysproxy.recover_if_needed(run=FakeRunner()) is False


class TestWindows:
    def test_win_takeover_and_restore(self, state_path, monkeypatch):
        monkeypatch.setattr(sysproxy.platform, "system", lambda: "Windows")
        calls = []

        def run(cmd, timeout=15):
            calls.append(cmd)
            if "query" in cmd:
                if any("ProxyEnable" in c for c in cmd):
                    return 0, "    ProxyEnable    REG_DWORD    0x0\n", ""
                return 0, "    ProxyServer    REG_SZ    old.proxy:8080\n", ""
            return 0, "", ""

        ok, _ = sysproxy.takeover(8080, run=run)
        assert ok
        assert ["reg", "add", sysproxy._WIN_KEY, "/v", "ProxyServer",
                "/t", "REG_SZ", "/d", "127.0.0.1:8080", "/f"] in calls
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved["saved"] == {"enabled": False, "server": "old.proxy:8080"}

        calls.clear()
        ok, _ = sysproxy.restore(run=run)
        assert ok
        # 原来是关的 → 只关不写旧地址
        assert ["reg", "add", sysproxy._WIN_KEY, "/v", "ProxyEnable",
                "/t", "REG_DWORD", "/d", "0", "/f"] in calls


class TestSettingsAutoProxy:
    def test_default_on_and_roundtrip(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
        s = settings_mod.load_settings()
        assert s.auto_system_proxy is True
        s.auto_system_proxy = False
        settings_mod.save_settings(s)
        assert settings_mod.load_settings().auto_system_proxy is False


# ====================================================================== 主窗口接线

class FakeThread:
    """同步执行的线程替身：start() 直接跑 target，便于断言。"""

    instances: list["FakeThread"] = []

    def __init__(self, target=None, daemon=False, name=None):
        self.target = target
        FakeThread.instances.append(self)

    def start(self):
        self.target()


    def join(self, timeout=None):
        pass                     # start() 已同步执行完，join 无事可做


@pytest.fixture()
def window(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    # 固定测试端口：默认 8888 与真实运行的 app 冲突（真实代理线程绑定失败
    # 会 SystemExit，running=False，整个 TestPortChange 全体崩）
    import json as _json

    (tmp_path / "settings.json").write_text(
        _json.dumps({"proxy_port": 18888, "auto_system_proxy": True})
    )
    # 只替换 main_window 命名空间里的 threading，别动全局 stdlib——
    # 全局替换会把代理线程也变成同步执行，asyncio 在主线程跑直接崩
    import threading as _real_threading

    monkeypatch.setattr(
        "app.ui.main_window.threading",
        SimpleNamespace(Thread=FakeThread, Lock=_real_threading.Lock),
    )
    FakeThread.instances.clear()
    from app.ui.main_window import MainWindow

    win = MainWindow(restore_prompt=False)
    yield win
    win.proxy.stop()
    sysproxy.restore(run=FakeRunner())


class TestMainWindowWiring:
    def test_checkbox_defaults_to_setting(self, window):
        assert window.sysproxy_cb.isChecked() is True
        assert window.settings.auto_system_proxy is True

    def test_toggle_persists_and_acts_only_when_running(self, window, tmp_path):
        calls = []
        window.sysproxy_cb.setChecked(False)  # 代理未运行 → 只存设置
        assert window.settings.auto_system_proxy is False
        assert calls == []  # 没运行就不该去动系统代理
        assert "auto_system_proxy" in json.loads(
            (tmp_path / "settings.json").read_text(encoding="utf-8")
        )

    def test_start_takes_over_stop_restores(self, window, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "app.sysproxy.takeover",
            lambda port, run=None, elevate=False: calls.append(("takeover", port)) or (True, "ok"),
        )
        monkeypatch.setattr(
            "app.sysproxy.restore",
            lambda run=None, port=None: calls.append(("restore",)) or (True, "已还原"),
        )
        monkeypatch.setattr(
            "app.sysproxy.recover_if_needed", lambda run=None, port=None: calls.append(("recover",)) or False
        )
        window.start_proxy()
        assert ("recover",) in calls
        assert ("takeover", window.proxy.port) in calls
        window.stop_proxy()
        assert ("restore",) in calls

    def test_close_restores_sync(self, window, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "app.sysproxy.restore",
            lambda run=None, port=None: calls.append(("restore",)) or (True, "已还原"),
        )
        window._restore_sysproxy_sync()
        assert calls == [("restore",)]

    def test_takeover_failure_shows_status_hint(self, window, monkeypatch, qtbot=None):
        def fail_takeover(port, run=None, elevate=False):
            return False, "设置 Wi-Fi 代理失败: no rights"

        monkeypatch.setattr("app.sysproxy.takeover", fail_takeover)
        monkeypatch.setattr(
            "app.ui.main_window.QMessageBox.question",
            lambda *a, **k: __import__("PySide6").QtWidgets.QMessageBox.StandardButton.No,
        )
        window._sysproxy_elevate_asked = False
        window._on_sysproxy_done(False, "设置 Wi-Fi 代理失败: no rights")
        assert "接管失败" in window.status_bar.currentMessage()


# ====================================================================== 端口即时生效（v1.14）

class TestPortChange:
    def test_change_yes_restarts_app(self, window, monkeypatch):
        """运行中改端口并确认：拉起新实例 + 标记重启 + 走 close 退出。"""
        import sys as _sys

        monkeypatch.setattr(
            "app.ui.main_window.QMessageBox.question",
            staticmethod(lambda *a, **k: _sys.modules[
                "PySide6.QtWidgets"].QMessageBox.StandardButton.Yes),
        )
        pops = []
        monkeypatch.setattr(
            "app.ui.main_window.subprocess.Popen",
            staticmethod(lambda cmd, **k: (pops.append(list(cmd)), object())[1]),
        )
        # sysproxy 层一并 stub 掉：main_window 里的 subprocess 是全局模块，
        # patch Popen 会影响 sysproxy._run 的 subprocess.run
        monkeypatch.setattr(
            "app.sysproxy.takeover",
            lambda port, run=None, elevate=False: (True, "ok"),
        )
        monkeypatch.setattr(
            "app.sysproxy.restore",
            lambda run=None, port=None: (True, "已还原"),
        )
        monkeypatch.setattr(
            "app.sysproxy.recover_if_needed", lambda run=None, port=None: False
        )
        monkeypatch.setattr(
            window, "_app_restart_command", lambda: ["/fake/MiteProxy.app"]
        )
        closes = []
        monkeypatch.setattr(window, "close", lambda: closes.append(1))

        window.start_proxy()
        old_port = window.settings.proxy_port
        new_port = old_port + 73
        window.port_spin.setValue(new_port)
        window._on_port_changed()

        assert window.settings.proxy_port == new_port
        assert window._restarting is True
        assert pops == [["/fake/MiteProxy.app"]]
        assert closes == [1]
        # 窗口 fixture teardown 会调 win.proxy.stop()——重启路径下未真停，
        # 手动清掉避免 FakeThread 状态残留
        window._restarting = False

    def test_restart_command_unavailable_falls_back_to_proxy_restart(
        self, window, monkeypatch
    ):
        """构造不出重启命令时退回「仅重启代理」：换端口重监听+先还原再接管。"""
        import sys as _sys

        monkeypatch.setattr(
            "app.ui.main_window.QMessageBox.question",
            staticmethod(lambda *a, **k: _sys.modules[
                "PySide6.QtWidgets"].QMessageBox.StandardButton.Yes),
        )
        monkeypatch.setattr(window, "_app_restart_command", lambda: None)
        calls = []
        monkeypatch.setattr(
            "app.sysproxy.takeover",
            lambda port, run=None, elevate=False:
                calls.append(("takeover", port)) or (True, "ok"),
        )
        monkeypatch.setattr(
            "app.sysproxy.restore",
            lambda run=None, port=None: calls.append(("restore",)) or (True, "已还原"),
        )
        monkeypatch.setattr(
            "app.sysproxy.recover_if_needed",
            lambda run=None, port=None: False,
        )
        window.start_proxy()
        old_port = window.settings.proxy_port
        assert ("takeover", old_port) in calls

        calls.clear()
        new_port = old_port + 73          # 换一个没绑过的端口
        window.port_spin.setValue(new_port)
        window._on_port_changed()          # editingFinished 处理器

        assert window.settings.proxy_port == new_port
        assert window.proxy.port == new_port
        # FakeThread 同步执行：返回时还原+重接管已完成，且顺序正确
        assert calls == [("restore",), ("takeover", new_port)]
        # 新线程真的监听起来（最多等 3s）
        import time as _time
        deadline = _time.monotonic() + 3.0
        while not window.proxy.running and _time.monotonic() < deadline:
            _time.sleep(0.05)
        assert window.proxy.running
        window.stop_proxy()

    def test_change_decline_keeps_old_proxy(self, window, monkeypatch):
        """运行中改端口但选「否」：只保存设置，旧代理继续在原端口跑。"""
        import sys as _sys

        monkeypatch.setattr(
            "app.ui.main_window.QMessageBox.question",
            staticmethod(lambda *a, **k: _sys.modules[
                "PySide6.QtWidgets"].QMessageBox.StandardButton.No),
        )
        calls = []
        monkeypatch.setattr(
            "app.sysproxy.takeover",
            lambda port, run=None, elevate=False:
                calls.append(("takeover", port)) or (True, "ok"),
        )
        monkeypatch.setattr(
            "app.sysproxy.restore",
            lambda run=None, port=None: calls.append(("restore",)) or (True, "已还原"),
        )
        monkeypatch.setattr(
            "app.sysproxy.recover_if_needed", lambda run=None, port=None: False
        )
        window.start_proxy()
        old_port = window.settings.proxy_port
        calls.clear()

        new_port = old_port + 91
        window.port_spin.setValue(new_port)
        window._on_port_changed()

        assert window.settings.proxy_port == new_port   # 设置已保存
        assert window.proxy.port == old_port            # 代理还在旧端口
        assert window.proxy.running
        assert calls == []                              # 没碰系统代理
        window.stop_proxy()

    def test_change_while_stopped_only_saves(self, window, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "app.sysproxy.takeover",
            lambda port, run=None, elevate=False: calls.append("takeover") or (True, "ok"),
        )
        monkeypatch.setattr(
            "app.sysproxy.restore",
            lambda run=None, port=None: calls.append("restore") or (True, "ok"),
        )
        new_port = window.settings.proxy_port + 11
        window.port_spin.setValue(new_port)
        window._on_port_changed()
        assert window.settings.proxy_port == new_port
        assert calls == []                 # 没运行就不碰系统代理
        assert not window.proxy.running

    def test_same_port_noop(self, window, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "app.sysproxy.takeover",
            lambda port, run=None, elevate=False: calls.append("takeover") or (True, "ok"),
        )
        window.port_spin.setValue(window.settings.proxy_port)  # 同值
        window._on_port_changed()
        assert calls == []


# ====================================================================== Windows 无窗口执行（v1.14b）

class TestNoWindowCreation:
    def test_windows_run_passes_create_no_window(self, monkeypatch):
        """Windows 下 _run 必须带 CREATE_NO_WINDOW——GUI 进程起 reg 子进程
        否则每个命令闪一个控制台窗口（启动接管连闪 4~5 个）。"""
        import subprocess as sp

        captured = {}

        def fake_run(cmd, **kwargs):
            captured.update(kwargs)
            captured["cmd"] = cmd
            return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr("app.sysproxy.platform.system", lambda: "Windows")
        monkeypatch.setattr("app.sysproxy.subprocess.run", fake_run)
        sysproxy._run(["reg", "query", "HKCU\\x"])
        # Windows 上该常量 = CREATE_NO_WINDOW；非 Windows 平台常量本身是 0，
        # 这里验证「Windows 分支确实把常量传进了 creationflags」这条接线
        assert captured.get("creationflags") == sysproxy._CREATE_NO_WINDOW

    def test_posix_run_has_no_creationflags(self, monkeypatch):
        import subprocess as sp

        captured = {}

        def fake_run(cmd, **kwargs):
            captured.update(kwargs)
            return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr("app.sysproxy.platform.system", lambda: "Darwin")
        monkeypatch.setattr("app.sysproxy.subprocess.run", fake_run)
        sysproxy._run(["networksetup", "-getwebproxy", "Wi-Fi"])
        assert "creationflags" not in captured


class TestCaptureStatusIndicator:
    """左下角 Fiddler 式抓包状态：随状态刷新，点击切换系统代理接管。"""

    def test_label_states(self, window):
        """运行+接管=绿「抓包中」；运行+未接管=黄「抓包暂停」；停止=灰「未抓包」。"""
        # 未运行
        window._update_status()
        assert "未抓包" in window.capture_label.text()
        # 运行 + 接管
        calls = []
        import app.sysproxy as sp_mod

        orig_takeover, orig_restore = sp_mod.takeover, sp_mod.restore
        sp_mod.takeover = lambda port, run=None, elevate=False: (
            calls.append(("takeover", port)) or (True, "ok")
        )
        sp_mod.restore = lambda run=None, port=None: (
            calls.append(("restore",)) or (True, "已还原")
        )
        try:
            window.sysproxy_cb.setChecked(True)
            window.start_proxy()
            window._update_status()
            assert "抓包中" in window.capture_label.text()
            assert "127.0.0.1" in window.capture_label.text()
            # 运行 + 未接管
            window.sysproxy_cb.setChecked(False)
            assert "抓包暂停" in window.capture_label.text()
        finally:
            window.stop_proxy()
            sp_mod.takeover, sp_mod.restore = orig_takeover, orig_restore
        # 停止后
        assert "未抓包" in window.capture_label.text()

    def test_click_toggles_sysproxy(self, window):
        """运行中点击状态标签 = 切换 sysproxy_cb（接管→还原）。"""
        import app.sysproxy as sp_mod

        calls = []
        orig_takeover, orig_restore = sp_mod.takeover, sp_mod.restore
        sp_mod.takeover = lambda port, run=None, elevate=False: (
            calls.append(("takeover", port)) or (True, "ok")
        )
        sp_mod.restore = lambda run=None, port=None: (
            calls.append(("restore",)) or (True, "已还原")
        )
        try:
            window.start_proxy()
            window.sysproxy_cb.setChecked(True)
            calls.clear()
            window._on_capture_clicked()          # 接管中点击 → 还原
            assert not window.sysproxy_cb.isChecked()
            assert calls == [("restore",)]
            window._on_capture_clicked()          # 未接管点击 → 重新接管
            assert window.sysproxy_cb.isChecked()
            assert calls == [("restore",), ("takeover", window.proxy.port)]
        finally:
            window.stop_proxy()
            sp_mod.takeover, sp_mod.restore = orig_takeover, orig_restore

    def test_click_when_stopped_starts_proxy(self, window):
        """未运行时点击 = 启动代理。"""
        import app.sysproxy as sp_mod

        orig_takeover = sp_mod.takeover
        sp_mod.takeover = lambda port, run=None, elevate=False: (True, "ok")
        try:
            assert not window.proxy.running
            window._on_capture_clicked()
            assert window.proxy.running
        finally:
            window.stop_proxy()
            sp_mod.takeover = orig_takeover


class TestRestoreFallbackByPort:
    """快照丢失时的端口兜底：只关闭指向 127.0.0.1:<我们的端口> 的代理。"""

    def _runner_with(self, server, port):
        r = FakeRunner()
        for secure in (False, True):
            r.state["Wi-Fi"][secure] = {
                "enabled": True, "server": server, "port": port,
            }
        return r

    def test_no_snapshot_clears_our_proxy(self, state_path):
        """无快照 + 系统代理指向 127.0.0.1:8888（我们的端口）→ 兜底关闭。"""
        r = self._runner_with("127.0.0.1", 8888)
        assert not state_path.exists()
        ok, msg = sysproxy.restore(run=r, port=8888)
        assert ok and "兜底" in msg
        state_offs = [c for c in r.calls if c[1] == "-setwebproxystate"
                      or c[1] == "-setsecurewebproxystate"]
        # Wi-Fi 的 HTTP/HTTPS 被关；Ethernet（10.0.0.1:7890，非我们的）不动
        assert len(state_offs) == 2
        assert all(c[2] == "Wi-Fi" and c[3] == "off" for c in state_offs)

    def test_no_snapshot_keeps_foreign_proxy(self, state_path):
        """无快照 + 代理端口不是我们的 → 不动用户配置。"""
        r = self._runner_with("127.0.0.1", 9999)
        ok, msg = sysproxy.restore(run=r, port=8888)
        assert ok and msg == "无接管记录"
        assert not [c for c in r.calls if "proxystate" in c[1]]

    def test_no_snapshot_keeps_non_loopback(self, state_path):
        """无快照 + 代理是其他服务器（哪怕端口相同）→ 不动。"""
        r = self._runner_with("192.168.1.1", 8888)
        ok, msg = sysproxy.restore(run=r, port=8888)
        assert msg == "无接管记录"

    def test_recover_sweeps_when_snapshot_missing(self, state_path):
        """启动崩溃恢复：无快照也按端口兜底扫一遍。"""
        r = self._runner_with("localhost", 8888)   # localhost 同样算我们的
        assert sysproxy.recover_if_needed(run=r, port=8888) is True
        assert [c for c in r.calls if "proxystate" in c[1]]

    def test_recover_noop_when_clean(self, state_path):
        r = FakeRunner()   # 默认没有指向我们的代理
        assert sysproxy.recover_if_needed(run=r, port=8888) is False

    def test_snapshot_still_wins_over_fallback(self, state_path):
        """有快照时走原还原逻辑（按记录恢复原值），兜底不参与。"""
        r = self._runner_with("127.0.0.1", 8888)
        state_path.write_text(json.dumps({
            "platform": "macos",
            "services": {"Wi-Fi": {
                "web": {"enabled": True, "server": "10.0.0.1", "port": 7890},
                "secure": {"enabled": True, "server": "10.0.0.1", "port": 7890},
            }},
        }), encoding="utf-8")
        ok, msg = sysproxy.restore(run=r, port=8888)
        assert ok and "兜底" not in msg
        # 恢复成快照里的原值而不是直接关
        assert r.state["Wi-Fi"][True]["server"] == "10.0.0.1"
