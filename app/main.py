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
    """崩溃取证：段错误栈 / 未捕获异常 / Qt 致命消息 / 操作轨迹。

    具体实现见 :mod:`app.crashreport`（含后台线程钩子、启动环境快照与
    非正常退出检测）。这里只做入口，保持启动流程可读。
    """
    try:
        from app import crashreport

        crashreport.install()
    except Exception:                # pragma: no cover - 取证失败不该阻止启动
        logging.getLogger(__name__).exception("崩溃取证初始化失败")


def _start_hang_watch(app: QApplication) -> None:
    """启动界面卡死检测：主线程每 250ms 打心跳，看门狗线程负责判超时。

    心跳必须由**主线程的定时器**来打：主线程一旦卡住，定时器就停跳，
    看门狗据此判定。这条链路的意义在于——卡死时进程还活着，``faulthandler``
    不会触发，常规异常钩子也不会触发，只有第三方线程才可能察觉。
    """
    try:
        from app import crashreport

        beat = QTimer(app)            # 挂在 app 上，避免被回收导致心跳停跳
        beat.setInterval(250)
        beat.timeout.connect(crashreport.beat)
        beat.start()
        crashreport.beat()
        crashreport.start_watchdog()
    except Exception:                # pragma: no cover - 看门狗失败不影响抓包
        logging.getLogger(__name__).exception("卡死看门狗启动失败")


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
    # 界面卡死看门狗（主线程心跳 + 后台超时判栈）。越早装越好：启动阶段的
    # 卡死同样要能留下证据。宽限期由 crashreport 内部给，不会误报。
    _start_hang_watch(app)

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

    def _after_startup_prompts() -> None:
        """启动弹窗排队：先「恢复上次会话」，再「上次异常退出，是否上报」。

        两者都是模态框，必须串行——并行排队会让第二个叠在第一个上面。
        端口变更弹窗由 start_proxy 同步弹出，天然排在最前。
        """
        window._maybe_restore_autosave()
        window._maybe_report_crash()

    if window.restore_prompt:
        QTimer.singleShot(0, _after_startup_prompts)
    app.aboutToQuit.connect(window.stop_proxy)

    # 主窗口就绪后再接收后续实例的唤醒请求（把它带到前台）
    def _raise_window() -> None:
        window.showNormal()
        window.raise_()
        window.activateWindow()

    single_instance.start_wake_listener(_raise_window)

    rc = app.exec()
    # 正常退出：删掉运行标记。下次启动若发现标记还在，说明这次没走完退出
    # 流程（崩溃/被杀），crash.log 会据此记一笔，不必等用户回想「哪次崩的」。
    try:
        from app import crashreport

        # 先停看门狗：关窗期间主线程要收尾，心跳会短暂停跳，
        # 不停的话每次正常退出都会在 hang.log 里留一条假卡死。
        crashreport.stop_watchdog()
        crashreport.note("app_exit", f"rc={rc}")
        crashreport.mark_clean_exit()
    except Exception:                # pragma: no cover
        pass
    single_instance.release()    # 正常退出释放锁（崩溃场景由探活逻辑兜底）
    return rc


if __name__ == "__main__":
    sys.exit(main())
