"""MiteProxy 入口。

用法：
    python -m app.main
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app import single_instance
from app.ui import dialogs
from app.ui.main_window import MainWindow


def _app_icon() -> QIcon:
    """窗口/任务栏图标（Windows 任务栏取自 QApplication.windowIcon）。

    打包后图标由 spec datas 塞进包内（Windows onedir 在 _internal，
    macOS bundle 在 Contents/Frameworks 与 Resources 各一份），
    源码运行取仓库 packaging/ 下。优先 icon.ico（含 16-256 全尺寸帧，
    各 DPI 清晰），回落 icon_256.png。
    """
    bases: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        bases.append(Path(meipass))
    exe_dir = Path(sys.executable).resolve().parent  # …/Contents/MacOS
    bases += [exe_dir, exe_dir.parent / "Resources", exe_dir.parent / "Frameworks"]
    bases.append(Path(__file__).resolve().parent.parent / "packaging")  # 源码运行
    for name in ("icon.ico", "icon_256.png"):
        for base in bases:
            candidate = base / name
            if candidate.is_file():
                return QIcon(str(candidate))
    return QIcon()


def _setup_file_logging() -> None:
    """把日志同时落盘到 ~/.miteproxy/logs/miteproxy.log。

    用 RotatingFileHandler：单文件上限 2MB，保留 4 份备份，总占用封顶 ~10MB，
    不会无限增长；旧文件自动按 .1/.2/.3 滚动覆盖。日志级别 INFO 及以上。
    """
    from logging.handlers import RotatingFileHandler

    from app.ui.log_panel import get_log_path

    path = get_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(
        str(path),
        maxBytes=2 * 1024 * 1024,
        backupCount=4,
        encoding="utf-8",
        delay=True,
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(fh)


def _setup_crash_handlers() -> None:
    """崩溃取证：段错误栈 / 未捕获异常 / Qt 致命消息统一写进 crash.log。

    打包成 GUI exe（Windows ``console=False``）后 stderr 无处可去，进程一崩就
    彻底失声——既没有 traceback，也没留下任何线索，事后只能靠猜。这里兜三条路：

    1. ``faulthandler``：段错误（SIGSEGV）等「进程直接消失」时，由解释器把当前
       各线程的 Python 栈吐出来。``all_threads=True`` 是必需的——崩溃未必发生在
       主线程，mitmproxy 的抓取线程同样值得看。
    2. ``sys.excepthook``：槽函数里抛出的异常默认只往 stderr 打一行（有时被
       PySide6 直接吞掉），写盘才留得住；写完后交回原 hook，控制台行为不变。
    3. Qt 消息处理器：Qt 自身的 WARNING/CRITICAL/FATAL（非法 QModelIndex、跨线程
       碰 GUI 等）往往是崩溃前兆，一并留证。Debug/Info 量太大，会淹没证据，跳过。

    追加写、不做滚动：历史崩溃栈是唯一证据，被新日志覆盖就得再崩一次才能重来。
    只有真崩溃才写，量很小（一次几十 KB），不像普通日志会膨胀。
    """
    import faulthandler
    import traceback
    from datetime import datetime

    from app.ui.log_panel import get_log_path

    path = get_log_path().parent / "crash.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open("a", encoding="utf-8", errors="replace")
    except OSError:
        return                       # 连日志目录都开不了，取证无门但不该拖垮启动

    stream.write(f"\n===== MiteProxy 启动 {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    stream.flush()
    faulthandler.enable(file=stream, all_threads=True)

    original_hook = sys.excepthook

    def _on_uncaught(exc_type, exc, tb) -> None:
        stream.write(f"\n----- 未捕获异常 {datetime.now():%H:%M:%S} -----\n")
        traceback.print_exception(exc_type, exc, tb, file=stream)
        stream.flush()
        original_hook(exc_type, exc, tb)

    sys.excepthook = _on_uncaught

    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        levels = {
            QtMsgType.QtCriticalMsg: "CRITICAL",
            QtMsgType.QtFatalMsg: "FATAL",
            QtMsgType.QtWarningMsg: "WARNING",
        }

        def _on_qt_message(mode, context, message) -> None:
            level = levels.get(mode)
            if level is None:        # Debug/Info 不写，避免淹没真正的证据
                return
            where = f" ({context.file}:{context.line})" if context.file else ""
            stream.write(f"[Qt {level}]{where} {message}\n")
            stream.flush()

        qInstallMessageHandler(_on_qt_message)
    except Exception:                # pragma: no cover - 不影响取证主路径
        pass


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # 落盘滚动日志（有大小上限，不会无限增长）
    _setup_file_logging()
    # 崩溃取证（段错误 / 未捕获异常 / Qt 致命消息写 crash.log）
    _setup_crash_handlers()

    app = QApplication(sys.argv)
    app.setApplicationName("MiteProxy")
    app.setWindowIcon(_app_icon())

    # 国际化：按设置的语言装好翻译器。中文是源语言（源码文案即中文），
    # 不装翻译器即显示中文；英文等需 MiteProxy_<lang>.qm 覆盖。
    # 必须在创建 MainWindow 之前完成——控件构造时即读取翻译。
    from app.i18n import load_language
    from app.settings import load_settings

    load_language(app, load_settings().language)

    # 单实例：第二个实例不启动主界面，唤醒已运行实例的主窗口后退出。
    # 多开没有任何收益——只会抢代理/证书端口、互相覆盖系统代理设置。
    if not single_instance.acquire():
        if not single_instance.notify_running():
            # 极端情况（锁在但唤醒服务没监听）：至少提示用户别干等
            dialogs.information(
                None,
                QApplication.translate("main", "MiteProxy 已在运行"),
                QApplication.translate(
                    "main",
                    "检测到 MiteProxy 已有一个实例在运行，请切换到已打开的窗口。",
                ),
            )
        return 0

    # 代理由 MainWindow 统一持有（含 MockAddon / CaptureAddon），
    # 入口不再单独创建 ProxyService，否则会出现两个代理实例：
    # 一个不带 addon（无法 mock、无法推送流量到界面）抢占了端口，用户却以为在跑带规则的代理。
    window = MainWindow()
    window.show()
    window.start_proxy(verify=True)      # 启动即开代理（对齐 Fiddler 打开即抓包）
    # 「恢复上次会话」弹窗排在端口变更弹窗之后：start_proxy 里的端口弹窗是
    # 同步模态（在 app.exec() 之前就弹并等用户关掉），这里再排程会话弹窗，
    # 事件循环启动后才会处理，保证端口弹窗第一个弹出、会话弹窗在其后。
    if window.restore_prompt:
        QTimer.singleShot(0, window._maybe_restore_autosave)
    app.aboutToQuit.connect(window.stop_proxy)

    # 主窗口就绪后再接收后续实例的唤醒请求（把它带到前台）
    def _raise_window() -> None:
        window.showNormal()
        window.raise_()
        window.activateWindow()

    single_instance.start_wake_listener(_raise_window)

    rc = app.exec()
    single_instance.release()    # 正常退出释放锁（崩溃场景由探活逻辑兜底）
    return rc


if __name__ == "__main__":
    sys.exit(main())
