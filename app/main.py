"""MiteProxy 入口。

用法：
    python -m app.main
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def _app_icon() -> QIcon:
    """窗口/任务栏图标（Windows 任务栏取自 QApplication.windowIcon）。

    打包后 icon_256.png 由 spec datas 塞进 _internal（sys._MEIPASS），
    源码运行取仓库 packaging/ 下。
    """
    base = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    for candidate in (base / "icon_256.png", base / "packaging" / "icon_256.png"):
        if candidate.is_file():
            return QIcon(str(candidate))
    return QIcon()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("MiteProxy")
    app.setWindowIcon(_app_icon())

    # 代理由 MainWindow 统一持有（含 MockAddon / CaptureAddon），
    # 入口不再单独创建 ProxyService，否则会出现两个代理实例：
    # 一个不带 addon（无法 mock、无法推送流量到界面）抢占了端口，用户却以为在跑带规则的代理。
    window = MainWindow()
    window.show()
    window.start_proxy(verify=True)      # 启动即开代理（对齐 Fiddler 打开即抓包）
    app.aboutToQuit.connect(window.stop_proxy)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
