"""关闭应用不误报"意外退出" + 端口被占用顺延时弹窗提示（v2.7）。

- closeEvent 停代理时，代理线程收尾会 emit proxy_state_changed(False)，
  那是正常退出，不应弹"抓包进程意外退出"（closeEvent 不像 stop_proxy
  那样先复位按钮，旧逻辑会误报）。
- 启动时端口被占用自动顺延到其他端口，必须弹窗明确告知用户。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from app import settings as settings_mod
from app import sysproxy


_app = QApplication.instance() or QApplication([])


class FakeRunner:
    def __init__(self, services=("Wi-Fi", "Ethernet"), fail_on=None):
        self.calls = []
        self.services = list(services)
        self.fail_on = fail_on
        self.state = {
            svc: {
                False: {"enabled": False, "server": "", "port": 0},
                True: {"enabled": True, "server": "10.0.0.1", "port": 7890},
            }
            for svc in self.services
        }

    def __call__(self, cmd, timeout=15):
        self.calls.append(cmd)
        if cmd[1] == "-listallnetworkservices":
            return 0, "\n".join(self.services) + "\n", ""
        if cmd[1] in ("-getwebproxy", "-getsecurewebproxy"):
            svc = cmd[2]
            st = self.state.get(svc, {})[cmd[1] == "-getsecurewebproxy"]
            return 0, f"Enabled: {'Yes' if st['enabled'] else 'No'}\n", ""
        if cmd[1] in ("-setwebproxy", "-setsecurewebproxy", "-setwebproxystate",
                      "-setsecurewebproxystate"):
            return 0, "", ""
        return 0, "", ""


class FakeThread:
    """同步执行的线程替身：start() 直接跑 target，便于断言。"""

    instances = []

    def __init__(self, target=None, daemon=False, name=None):
        self.target = target
        FakeThread.instances.append(self)

    def start(self):
        self.target()

    def join(self, timeout=None):
        pass


@pytest.fixture()
def window(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text(
        json.dumps({"proxy_port": 18888, "auto_system_proxy": True})
    )
    import threading as _real_threading

    monkeypatch.setattr(
        "app.ui.main_window.threading",
        SimpleNamespace(Thread=FakeThread, Lock=_real_threading.Lock),
    )
    FakeThread.instances.clear()
    from app.ui.main_window import MainWindow

    win = MainWindow(restore_prompt=False)
    # 让系统代理层在测试里无副作用
    monkeypatch.setattr("app.sysproxy.takeover",
                        lambda port, run=None, elevate=False: (True, "ok"))
    monkeypatch.setattr("app.sysproxy.restore",
                        lambda run=None, port=None: (True, "已还原"))
    monkeypatch.setattr("app.sysproxy.recover_if_needed",
                        lambda run=None, port=None: False)
    yield win
    win.proxy.stop()
    sysproxy.restore(run=FakeRunner())


class TestExitNoFalseDialog:
    def test_close_with_running_proxy_does_not_pop_crash_dialog(self, window, monkeypatch):
        pops = []
        monkeypatch.setattr("app.ui.main_window.dialogs.critical",
                            lambda *a, **k: pops.append(k))
        window.start_proxy()
        assert window.proxy.running
        assert window.proxy_btn.isChecked()

        evt = QCloseEvent()
        window.closeEvent(evt)
        QApplication.processEvents()  # 让代理线程收尾 emit 的 queued 信号送达

        assert window._exiting is True
        assert pops == []  # 没有"抓包进程意外退出"弹窗

    def test_exiting_flag_suppresses_state_change_dialog(self, window, monkeypatch):
        pops = []
        monkeypatch.setattr("app.ui.main_window.dialogs.critical",
                            lambda *a, **k: pops.append(k))
        window._exiting = True
        window.proxy_btn.setChecked(True)
        window._on_proxy_state_changed(False, "")
        assert pops == []

    def test_real_unexpected_exit_still_pops(self, window, monkeypatch):
        """非退出路径（如代理真的崩了）仍要弹窗告警——行为不能丢。"""
        pops = []
        monkeypatch.setattr("app.ui.main_window.dialogs.critical",
                            lambda *a, **k: pops.append(k))
        window._exiting = False
        window.proxy_btn.setChecked(True)
        window._on_proxy_state_changed(False, "DumpMaster boom")
        assert pops != []


class TestPortChangeDialog:
    def test_port_collision_pops_information(self, window, monkeypatch):
        infos = []
        monkeypatch.setattr("app.ui.main_window.dialogs.information",
                            lambda *a, **k: infos.append(a))

        # 强制端口顺延：请求端口被占，自动改到下一个
        requested = window.settings.proxy_port
        window.proxy._pick_port = lambda: requested + 1

        window.start_proxy()
        assert window.proxy.port == requested + 1

        assert infos != []
        # 文案里应同时出现旧端口和新端口（position args: parent, title, text）
        text = infos[0][2]
        assert str(requested) in text and str(requested + 1) in text

    def test_no_collision_no_dialog(self, window, monkeypatch):
        infos = []
        monkeypatch.setattr("app.ui.main_window.dialogs.information",
                            lambda *a, **k: infos.append(k))
        window.start_proxy()
        assert window.proxy.port == window.settings.proxy_port
        assert infos == []


@pytest.fixture()
def capturing_window(tmp_path, monkeypatch):
    """记录 MainWindow 构造期间排程的所有 QTimer.singleShot（restore_prompt=True）。"""
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text(
        json.dumps({"proxy_port": 18888, "auto_system_proxy": True,
                    "check_update_on_startup": False})
    )
    import threading as _real_threading

    monkeypatch.setattr(
        "app.ui.main_window.threading",
        SimpleNamespace(Thread=FakeThread, Lock=_real_threading.Lock),
    )
    FakeThread.instances.clear()
    calls = []
    import PySide6.QtCore as _qtcore

    _real_ss = _qtcore.QTimer.singleShot

    def _spy(*a, **k):
        calls.append((a, k))
        return _real_ss(*a, **k)      # 记录同时真正排程，避免拦截后续事件循环

    monkeypatch.setattr("app.ui.main_window.QTimer.singleShot", _spy)
    from app.ui.main_window import MainWindow

    win = MainWindow(restore_prompt=True)
    win._single_shot_calls = calls
    yield win
    win.proxy.stop()
    sysproxy.restore(run=FakeRunner())


class TestStartupDialogOrder:
    def test_init_does_not_schedule_session_restore(self, capturing_window):
        """根因回归：会话恢复弹窗不能再在构造里排程，否则会被端口弹窗的
        模态事件循环提前处理、叠在端口弹窗之上（看起来像会话先弹）。"""
        funcs = [a[0] for a, k in capturing_window._single_shot_calls if a]
        assert capturing_window._maybe_restore_autosave not in funcs

    def test_port_dialog_before_session_dialog(self, capturing_window, monkeypatch):
        """复刻 main.py 顺序：start_proxy（端口弹窗，同步）在前，
        singleShot(0) 排程会话恢复在后；事件循环里端口弹窗先出。"""
        order = []
        monkeypatch.setattr("app.ui.main_window.dialogs.information",
                            lambda *a, **k: order.append("port"))
        monkeypatch.setattr("app.ui.main_window.dialogs.question",
                            lambda *a, **k: order.append("session")
                            or __import__("PySide6.QtWidgets").QtWidgets.QMessageBox.StandardButton.No)
        # 事件循环里代理状态回调也可能走 critical（测试环境端口绑定不可靠）：
        # offscreen 下真弹模态会挂死，必须一并拦掉
        monkeypatch.setattr("app.ui.main_window.dialogs.critical",
                            lambda *a, **k: order.append("critical"))
        # 让 _maybe_restore_autosave 真的走到 question 分支（并消除落盘副作用）
        monkeypatch.setattr("app.ui.main_window.read_autosave_meta",
                            lambda: {"count": 5, "saved_at": "now"})
        monkeypatch.setattr("app.ui.main_window.archive_autosave", lambda: None)
        monkeypatch.setattr("app.ui.main_window.clear_autosave", lambda: None)
        # 强制端口顺延，触发端口弹窗
        requested = capturing_window.settings.proxy_port
        capturing_window.proxy._pick_port = lambda: requested + 1
        capturing_window.start_proxy()           # 端口弹窗（同步，先）
        # main.py 顺序：start_proxy 之后再排程会话恢复
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, capturing_window._maybe_restore_autosave)
        QApplication.processEvents()
        assert order == ["port", "session"], order
