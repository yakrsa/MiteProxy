"""入口装配的防回归测试。

背景（真实 bug，Gate 6 抓到）：
`app/main.py` 曾自行 `ProxyService(...)` 并 `start()`，而这个实例**不带任何 addon**。
MainWindow 内部另有一个带 MockAddon/CaptureAddon 的 ProxyService，但只在点
「启动代理」时才启动。结果打包后的应用实际跑的是那个裸代理——
能连上游、却既不 mock 也不往界面推流量。源码模式的冒烟恰好绕过 main.py，
所以没暴露。

这里用两条断言把这个坑焊死：
1. 入口模块不得自行构造 ProxyService；
2. MainWindow 持有的代理必须挂齐 mock + capture 两个 addon。
"""

from pathlib import Path

from PySide6.QtWidgets import QApplication

import app.main as main_mod

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _ensure_app():
    return QApplication.instance() or QApplication([])


def test_entrypoint_does_not_create_own_proxy():
    """main.py 里不应出现 ProxyService 的构造或导入（代理归 MainWindow 所有）。"""
    src = (PROJECT_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "from app.proxy import" not in src, "入口不应导入 ProxyService"
    assert "ProxyService(" not in src, (
        "入口不应再自建 ProxyService——代理由 MainWindow 统一持有，"
        "否则会出现无 addon 的裸代理抢占端口"
    )
    assert "start_proxy" in src, "入口应通过 window.start_proxy() 启动代理"


def test_main_window_proxy_has_all_addons():
    """MainWindow 的代理必须同时挂 MockAddon 与 CaptureAddon。"""
    from addons.capture import CaptureAddon
    from addons.mock import MockAddon
    from app.ui.main_window import MainWindow

    _ensure_app()
    win = MainWindow()
    try:
        addons = win.proxy._addons
        assert any(isinstance(a, MockAddon) for a in addons), "缺少 MockAddon"
        assert any(isinstance(a, CaptureAddon) for a in addons), "缺少 CaptureAddon"
    finally:
        win.proxy.stop()
        win.deleteLater()


def test_start_proxy_is_idempotent():
    """start_proxy 幂等：重复调用不产生第二个代理线程。"""
    from app.ui.main_window import MainWindow

    _ensure_app()
    win = MainWindow()
    try:
        # 未启动时不应崩溃
        win.stop_proxy()
        assert win.start_proxy(verify=False) is True
    finally:
        win.proxy.stop()
        win.deleteLater()
