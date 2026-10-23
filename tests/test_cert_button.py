"""证书服务按钮交互：点击即弹二维码（修复「要点两次才弹窗」）。

背景：老逻辑是「启/停切换」——对话框点「好」关闭后服务仍在运行，
此时再点按钮会**静默停止**（无任何反馈），用户感知为「点了没反应」，
要再点一次才重新启动弹二维码。现语义：
- 点击：未运行 → 启动 + 弹二维码；已运行 → 直接重开二维码（不停止）；
- 停止：弹窗里的显式「停止服务」按钮；
- 按钮勾态 / tooltip 只表示「服务运行中」。

测试用假 CertServer（monkeypatch 掉 main_window.CertServer），不绑真端口。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QPushButton


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class FakeCertServer:
    """记录 start/stop 的假证书服务（接口对齐真 CertServer 的用法）。"""

    def __init__(self, port: int = 0, proxy_port: int = 0):
        self.port = port
        self.proxy_port = proxy_port
        self.url = f"http://127.0.0.1:{port}"
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    from app.ui import theme
    from app.ui import main_window as mw

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    theme.apply("light")
    # 假证书服务：不绑真端口；构造参数与真 CertServer 一致
    monkeypatch.setattr(mw, "CertServer", FakeCertServer)
    w = mw.MainWindow(restore_prompt=False)
    yield w
    w.close()


@pytest.fixture
def dialogs(monkeypatch):
    """拦截 QDialog.exec：记录被弹出的对话框而不是真跑模态循环。

    返回 list，每弹一次追加一个对话框实例。
    """
    shown: list[QDialog] = []

    def fake_exec(self):
        shown.append(self)
        return 0

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    return shown


def _stop_button(dlg: QDialog) -> QPushButton:
    return dlg.findChild(QPushButton, "cert_stop_btn")


# ---------------------------------------------------------------- 点击即弹

def test_click_starts_and_shows_dialog(win, dialogs):
    """未运行：点击 → 启动 + 弹二维码，按钮进入勾态。"""
    assert win.cert_server is None
    assert win.cert_btn.isChecked() is False

    win.cert_btn.click()

    assert len(dialogs) == 1
    assert dialogs[0].windowTitle() != ""
    assert win.cert_server is not None and win.cert_server.running
    assert win.cert_btn.isChecked() is True


def test_click_when_running_reshows_dialog_without_stopping(win, dialogs):
    """已运行：点击 → 重开二维码，服务**不停**（本测试锁定的核心回归）。

    老行为：第二次点击是静默停止，用户感知「没弹窗 / 要点两次」。
    """
    win._on_toggle_cert_server()          # 第一次：启动 + 弹
    first = win.cert_server
    assert len(dialogs) == 1

    win.cert_btn.click()                  # 第二次：应重弹而非停止

    assert len(dialogs) == 2, "运行中再点必须重弹二维码"
    assert win.cert_server is first and first.running, "不得被静默停止"
    assert win.cert_btn.isChecked() is True


def test_dialog_ok_keeps_service_running(win, dialogs):
    """弹窗「好」只关窗，服务保持运行（手机还要下载证书）。"""
    win._on_toggle_cert_server()
    dlg = dialogs[0]
    ok = dlg.findChild(QPushButton, "cert_ok_btn")
    assert ok is not None
    ok.click()
    assert win.cert_server is not None and win.cert_server.running
    assert win.cert_btn.isChecked() is True


def test_dialog_stop_button_stops_service(win, dialogs):
    """弹窗「停止服务」：显式停止，按钮复位，状态栏有反馈。"""
    win._on_toggle_cert_server()
    dlg = dialogs[0]

    _stop_button(dlg).click()

    assert win.cert_server is None
    assert win.cert_btn.isChecked() is False
    assert "证书服务" in win.status_bar.currentMessage()


def test_stop_path_resets_button(win, dialogs):
    """任意停止路径（_stop_cert_server 收敛点）都复位按钮勾态与 tooltip。"""
    win._on_toggle_cert_server()
    assert win.cert_btn.isChecked() is True

    win._stop_cert_server()

    assert win.cert_btn.isChecked() is False
    assert "启动局域网证书下载服务" in win.cert_btn.toolTip()


def test_running_tooltip_shows_url(win, dialogs):
    """运行中 tooltip 带实际地址，方便用户复制。"""
    win._on_toggle_cert_server()
    assert win.cert_server.url in win.cert_btn.toolTip()


def test_apply_cert_port_restart_syncs_button(win, dialogs):
    """运行中改证书端口：重启后按钮保持勾态并重弹二维码。"""
    win._on_toggle_cert_server()
    old = win.cert_server

    win._apply_cert_port(old.port + 1)

    assert win.cert_server is not None and win.cert_server.running
    assert win.cert_server.port == old.port + 1
    assert win.cert_btn.isChecked() is True
    assert len(dialogs) == 2  # 启动一次 + 端口重启一次


# ---------------------------------------------------------------- 命令面板

def test_palette_cert_command_opens_dialog(win, dialogs):
    """命令面板的「证书服务」条目：执行即弹二维码（标题不含启停歧义）。"""
    cmds = {c["id"]: c for c in win._build_commands()}
    assert "cert" in cmds
    assert cmds["cert"]["title"] == "证书服务"
    assert "启动" not in cmds["cert"]["title"] and "停止" not in cmds["cert"]["title"]

    cmds["cert"]["run"]()

    assert len(dialogs) == 1
    assert win.cert_server is not None and win.cert_server.running
