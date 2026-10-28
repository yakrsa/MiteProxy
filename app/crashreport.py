"""崩溃取证：崩溃栈 + 未捕获异常 + Qt 致命消息 + 操作轨迹。

## 为什么需要这个模块

打包成 GUI 程序（Windows ``console=False``）后，stderr 无处可去。进程一旦在
原生层崩溃（Windows 的 ``0xc0000005`` 访问违规、段错误等），Python 的
``try/except`` 与 ``logging`` 全都抓不到——用户看到的现象是「界面卡一下，然后
窗口自己没了」，事后既没有 traceback 也没有日志，只能靠猜。

本模块把三层证据统一落在 ``<CONFIG_DIR>/logs/`` 下：

===============  ============================================================
``crash.log``    真正的崩溃现场：启动环境快照、``faulthandler`` 的段错误栈、
                 未捕获异常的 traceback（主线程与后台线程各一路）、Qt 的
                 WARNING/CRITICAL/FATAL 消息。追加写、不滚动。
``actions.log``  最近若干步界面操作（双击了哪条请求、body 多大、渲染耗时、
                 当时的内存占用），环形覆盖。与 ``crash.log`` 的时间戳对照，
                 就能把「崩在哪个栈」和「当时在点哪条流量」对上。
``.running``     运行标记。启动时写入、正常退出时删除；下次启动若发现它还在，
                 说明上次进程没有走完退出流程（崩溃或被杀），立刻在
                 ``crash.log`` 里记一笔，并向 ``crash-pending.json`` 写一份摘要，
                 供启动后的弹窗询问用户是否上报。
``hang.log``     界面卡死（无响应但进程还活着）的证据。由独立看门狗线程在
                 主线程心跳超时后抓取各次主线程栈，卡死恢复时再记一笔时长。
                 这类问题 ``faulthandler`` 抓不到——进程并没有死。
``crash-pending.json``  上次异常退出的摘要（时间、栈片段、卡死记录、操作轨迹），
                 给「是否发送诊断报告」弹窗用。
===============  ============================================================

## 设计约束

- **取证代码自身绝不能抛异常**。它跑在崩溃路径上，这里再抛就等于断掉唯一的
  证据来源，所以对外函数一律 ``try/except`` 包死，失败就静默降级。
- 写盘开销要小。``note()`` 只在低频的界面动作上调用（双击、切换视图），
  不做逐帧或逐条流量记录。
"""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

#: 操作轨迹保留的条数（环形覆盖）。300 条足以还原崩溃前几分钟的点击序列，
#: 文件约 30KB，可以放心常开。
ACTION_KEEP = 300

#: 每写多少条做一次环形裁剪。每条都去数行数太贵，攒够一批再一次做完。
_ACTION_TRIM_EVERY = 60

#: 内存采样的最小间隔（秒）。取样要走一次系统调用，没必要每条轨迹都取。
_RSS_MIN_INTERVAL = 1.0

#: 单条轨迹的明细长度上限，防止把整段 body 塞进日志。
_DETAIL_MAX = 400

#: 主线程心跳超时（秒）。超过它没收到心跳，就认为界面已经卡住。
#: 取 5 秒：正常一次大 body 排版也在百毫秒级，5 秒不响应用户已经在骂了。
HEARTBEAT_TIMEOUT = 5.0

#: 卡死期间抓栈的采样间隔（秒）与次数上限。多次采样是有意为之——
#: 死循环每次栈顶不同、死锁每次都停在同一帧、慢渲染则都卡在同一个调用里，
#: 三种情况靠对比几次栈就能区分，单次栈看不出区别。
HANG_SAMPLE_EVERY = 5.0
HANG_SAMPLE_MAX = 6

#: 看门狗轮询间隔（秒）。要比 HEARTBEAT_TIMEOUT 小得多，否则判定时刻本身
#: 就会漂移出好几秒，卡死时长得凭空多算一截。
_WATCH_TICK = 0.5

#: 启动宽限期（秒）。事件循环还没转起来时主线程本来就不会打心跳，
#: 这段窗口内不判卡死，否则每次启动都会误报一次。
_STARTUP_GRACE = 15.0

#: 卡死日志单次保留上限（字符）。反复卡死也不能把文件写到几十 MB。
_HANG_CHARS_MAX = 60000

_lock = threading.Lock()
_installed = False
_action_count = 0
_rss_cache: tuple[float, float] = (0.0, 0.0)      # (取样时刻, MB)
_heartbeat = 0.0                                  # 最后一次心跳的 monotonic 时刻
_watchdog: threading.Thread | None = None
_watchdog_stop = threading.Event()
_grace_until = 0.0


# ---------------------------------------------------------------- 路径

def _log_dir() -> Path:
    """日志目录。延迟导入 CONFIG_DIR，避免本模块在 QApplication 之前被导入时
    把 app.rules 的重依赖链一并拉起来。"""
    from app.rules import CONFIG_DIR

    return CONFIG_DIR / "logs"


def crash_path() -> Path:
    """崩溃现场日志路径。"""
    return _log_dir() / "crash.log"


def actions_path() -> Path:
    """操作轨迹日志路径。"""
    return _log_dir() / "actions.log"


def _running_marker() -> Path:
    return _log_dir() / "crash-watch.running"


def hang_path() -> Path:
    """界面卡死日志路径（与 crash.log 分开：卡死不是崩溃，混在一起会误导排查）。"""
    return _log_dir() / "hang.log"


def _pending_file() -> Path:
    return _log_dir() / "crash-pending.json"


# ---------------------------------------------------------------- 内存

def _read_rss_mb() -> float:
    """当前进程常驻内存（MB）。取不到返回 0.0。"""
    try:
        if sys.platform == "win32":
            import ctypes
            import ctypes.wintypes as wt

            class _Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", wt.DWORD),
                    ("PageFaultCount", wt.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            k32.GetCurrentProcess.restype = wt.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [
                wt.HANDLE, ctypes.POINTER(_Counters), wt.DWORD
            ]
            psapi.GetProcessMemoryInfo.restype = wt.BOOL

            counters = _Counters()
            counters.cb = ctypes.sizeof(_Counters)
            if psapi.GetProcessMemoryInfo(
                k32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
            ):
                return counters.WorkingSetSize / 1024 / 1024
            return 0.0

        import resource
        import resource as _r

        peak = _r.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS 返回字节，Linux 返回 KB
        return peak / 1024 / 1024 if sys.platform == "darwin" else peak / 1024
    except Exception:                 # noqa: BLE001 - 取证辅助信息，取不到就算了
        return 0.0


def memory_mb() -> float:
    """带节流的常驻内存读数（MB）。"""
    global _rss_cache
    now = time.monotonic()
    stamp, value = _rss_cache
    if value > 0 and now - stamp < _RSS_MIN_INTERVAL:
        return value
    value = _read_rss_mb()
    _rss_cache = (now, value)
    return value


# ---------------------------------------------------------------- 环境快照

def _wer_dump_configured() -> bool | None:
    """Windows 上是否已开启 WER LocalDumps（本地保留 minidump）。

    没开的话，崩溃后系统把 dump 上报完就删，我们只剩一份没有调用栈的
    ``Report.wer``。返回 None 表示无法判断（非 Windows 或读取失败）。
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg

        key = (
            r"SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps"
            r"\MiteProxy.exe"
        )
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as handle:
            winreg.QueryValueEx(handle, "DumpFolder")
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
    except Exception:                 # noqa: BLE001
        return None


def environment() -> str:
    """一行一项的环境快照（多行文本）。"""
    lines = []
    try:
        from app.version import __version__

        lines.append(f"版本: {__version__}")
    except Exception:                 # noqa: BLE001
        lines.append("版本: 未知")

    lines.append(f"系统: {platform.platform()}")
    lines.append(f"Python: {platform.python_version()} ({sys.executable})")
    lines.append(f"打包运行: {'是' if getattr(sys, 'frozen', False) else '否'}")
    try:
        from PySide6 import QtCore

        lines.append(f"Qt: {QtCore.qVersion()}")
    except Exception:                 # noqa: BLE001
        pass

    mem = memory_mb()
    if mem > 0:
        lines.append(f"内存: {mem:.1f} MB")
    lines.append(f"进程: pid={os.getpid()}")

    dumps = _wer_dump_configured()
    if dumps is False:
        lines.append(
            "WER dump: 未开启（崩溃只会留下无调用栈的 Report.wer；"
            "开启方法见 TUTORIAL.md「崩溃排查」）"
        )
    elif dumps:
        lines.append("WER dump: 已开启")
    return "\n".join(lines)


# ---------------------------------------------------------------- 操作轨迹

def _trim_actions(path: Path) -> None:
    """把轨迹文件裁到最近 ACTION_KEEP 行。"""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) <= ACTION_KEEP:
            return
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines[-ACTION_KEEP:]) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass                          # 文件被占用/权限不足：下个周期再试


def note(action: str, detail: str = "") -> None:
    """记一条操作轨迹（供崩溃后与栈对照）。

    ``action`` 用短标签（``open_detail`` / ``detach_page``），``detail`` 写当时
    的关键参数（URL、body 字节数、耗时）。**这个函数绝不抛异常**——它跑在
    崩溃取证路径上，自己出错就等于把证据弄丢了。
    """
    global _action_count
    try:
        with _lock:
            _action_count += 1
            path = actions_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            mem = memory_mb()
            head = f"{stamp} [{mem:7.1f}MB] {action}"
            if detail:
                clean = str(detail).replace("\n", " ").replace("\r", " ")
                head = f"{head} | {clean[:_DETAIL_MAX]}"
            with path.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(head + "\n")
            if _action_count % _ACTION_TRIM_EVERY == 0:
                _trim_actions(path)
    except Exception:                 # noqa: BLE001 - 见函数说明
        pass


def recent_actions(limit: int = 40) -> list[str]:
    """读回最近若干条轨迹（排查时用，也供崩溃报告引用）。"""
    try:
        lines = actions_path().read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        return lines[-limit:]
    except OSError:
        return []


# ---------------------------------------------------------------- 卡死看门狗

def beat() -> None:
    """主线程心跳。UI 定时器每 250ms 调一次，卡死就自然停跳。

    只写一个浮点数，不加锁——它是 ``time.monotonic()`` 的赋值，在 CPython
    里原子；为它上锁反而会在主线程里制造无谓的竞争点。
    """
    global _heartbeat
    _heartbeat = time.monotonic()


def _main_stack(limit: int = 10) -> str:
    """当前主线程的 Python 栈（卡死时由看门狗线程抓取）。

    ``sys._current_frames()`` 可以在任意线程读别的线程栈，正是卡死时唯一
    还能用的观测手段——主线程已经跑不动了，让它自己抓栈是不可能的。
    """
    ident = threading.main_thread().ident
    frame = sys._current_frames().get(ident) if ident else None
    if frame is None:
        return "  (取不到主线程栈)"
    return "".join("  " + line for line in traceback.format_stack(frame, limit=limit))


def _write_hang(text: str) -> None:
    """追加写 hang.log，并把文件总长兜在上限内。"""
    try:
        path = hang_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(text)
        try:
            if path.stat().st_size > _HANG_CHARS_MAX * 2:
                raw = path.read_text(encoding="utf-8", errors="replace")
                path.write_text(raw[-_HANG_CHARS_MAX:], encoding="utf-8")
        except OSError:
            pass
    except Exception:                 # noqa: BLE001 - 取证路径不允许抛
        pass


def _hang_begin(silent: float) -> None:
    """卡死开始：写证据头 + 首次主线程栈 + 卡死前最后几步操作。"""
    lines = [
        f"\n=== 界面卡死 {datetime.now():%Y-%m-%d %H:%M:%S} "
        f"（已 {silent:.1f}s 无响应）===\n",
        "卡死前最后操作:\n",
    ]
    for item in recent_actions(12):
        lines.append(f"  {item}\n")
    lines.append("主线程栈（第 1 次采样）:\n")
    lines.append(_main_stack() + "\n")
    _write_hang("".join(lines))


def _hang_sample(index: int, silent: float) -> None:
    """卡死持续中：再抓一次栈，供前后对比判定成因。"""
    _write_hang(
        f"-- 第 {index} 次采样（已 {silent:.1f}s 无响应）--\n" + _main_stack(8) + "\n"
    )


def _hang_recovered(elapsed: float) -> None:
    """卡死自行恢复：记下时长，下次看同一处就知道是不是慢渲染。"""
    _write_hang(
        f"--- 已恢复，卡死时长 {elapsed:.1f}s "
        f"（{datetime.now():%H:%M:%S}）---\n"
    )


def _watchdog_loop() -> None:
    """看门狗主循环（跑在独立线程里）。

    为什么必须是独立线程：主线程一旦卡死，``QTimer`` 全部停摆，任何"自己
    检查自己"的方案都会跟着一起卡住。只有另一个线程才知道主线程不动了。
    """
    hang_start = 0.0
    samples = 0
    last_sample = 0.0

    while not _watchdog_stop.wait(_WATCH_TICK):
        try:
            now = time.monotonic()
            if now < _grace_until:
                continue
            silent = now - _heartbeat
            if silent < HEARTBEAT_TIMEOUT:
                if hang_start:
                    _hang_recovered(now - hang_start)
                    hang_start = 0.0
                    samples = 0
                continue

            if not hang_start:
                hang_start = now
                samples = 1
                last_sample = now
                _hang_begin(silent)
                continue

            # 采样有上限：长期挂着不该把日志刷爆，前几次已经足够看出成因
            if samples >= HANG_SAMPLE_MAX:
                continue
            if now - last_sample >= HANG_SAMPLE_EVERY:
                samples += 1
                last_sample = now
                _hang_sample(samples, silent)
        except Exception:             # noqa: BLE001 - 看门狗自己不能死
            time.sleep(_WATCH_TICK)


def start_watchdog(grace: float = _STARTUP_GRACE) -> bool:
    """启动卡死看门狗。幂等；重复调用只重置宽限期。

    ``grace``：启动宽限秒数。刚启动时事件循环还没转起来，主线程本来就不打
    心跳，这段窗口内不判卡死。
    """
    global _watchdog, _heartbeat, _grace_until

    _heartbeat = time.monotonic()
    _grace_until = _heartbeat + max(0.0, grace)

    if _watchdog is not None and _watchdog.is_alive():
        return True

    _watchdog_stop.clear()
    thread = threading.Thread(
        target=_watchdog_loop, name="mite-hang-watch", daemon=True
    )
    _watchdog = thread
    thread.start()
    return True


def stop_watchdog() -> None:
    """停掉看门狗（退出路径用：正常退出不该在关窗瞬间报一次卡死）。"""
    global _watchdog
    _watchdog_stop.set()
    thread = _watchdog
    _watchdog = None
    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)


def is_watchdog_running() -> bool:
    return _watchdog is not None and _watchdog.is_alive()


# ---------------------------------------------------------------- 安装

def _install_faulthandler(stream) -> None:
    """段错误等「进程直接消失」的场景，由解释器吐出各线程的 Python 栈。

    ``all_threads=True`` 是必需的：崩溃未必发生在主线程，mitmproxy 的抓取
    线程同样值得看。
    """
    import faulthandler

    faulthandler.enable(file=stream, all_threads=True)


def _install_thread_hook(stream) -> None:
    """后台线程里未被捕获的异常。

    ``sys.excepthook`` 只管主线程；mitmproxy 的抓取线程、单实例监听线程里抛出的
    异常**不会**经过它，默认只往 stderr 打一行——GUI 打包后等于静默丢弃。
    """
    import traceback

    original = threading.excepthook

    def _on_thread_error(args) -> None:
        try:
            stream.write(
                f"\n----- 线程未捕获异常 {datetime.now():%H:%M:%S} "
                f"thread={getattr(args.thread, 'name', '?')} -----\n"
            )
            traceback.print_exception(
                args.exc_type, args.exc_value, args.exc_traceback, file=stream
            )
            stream.flush()
        except Exception:             # noqa: BLE001
            pass
        try:
            original(args)
        except Exception:             # noqa: BLE001
            pass

    threading.excepthook = _on_thread_error


def _install_excepthook(stream) -> None:
    """主线程未捕获异常：写盘后交回原 hook，控制台行为保持不变。"""
    import traceback

    original = sys.excepthook

    def _on_uncaught(exc_type, exc, tb) -> None:
        try:
            stream.write(f"\n----- 未捕获异常 {datetime.now():%H:%M:%S} -----\n")
            traceback.print_exception(exc_type, exc, tb, file=stream)
            stream.flush()
        except Exception:             # noqa: BLE001
            pass
        try:
            original(exc_type, exc, tb)
        except Exception:             # noqa: BLE001
            pass

    sys.excepthook = _on_uncaught


def _install_qt_handler(stream) -> None:
    """Qt 自身的 WARNING/CRITICAL/FATAL 往往是崩溃前兆。

    Debug/Info 量太大，会把真正的证据淹没，只留 WARNING 及以上。
    """
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        levels = {
            QtMsgType.QtWarningMsg: "WARNING",
            QtMsgType.QtCriticalMsg: "CRITICAL",
            QtMsgType.QtFatalMsg: "FATAL",
        }

        def _on_qt_message(mode, context, message) -> None:
            level = levels.get(mode)
            if level is None:
                return
            try:
                where = f" ({context.file}:{context.line})" if context.file else ""
                stream.write(f"[Qt {level}]{where} {message}\n")
                stream.flush()
            except Exception:         # noqa: BLE001
                pass

        qInstallMessageHandler(_on_qt_message)
    except Exception:                 # noqa: BLE001 - 不影响其余取证路径
        pass


def _check_previous_run(stream, marker: Path, excerpt: str = "") -> None:
    """上次是否非正常退出（崩溃/被杀）；是就记进 crash.log 并留一份待上报摘要。"""
    try:
        if marker.exists():
            raw = marker.read_text(encoding="utf-8", errors="replace").strip()
            stream.write(
                "!! 上次进程未走完退出流程（崩溃、被结束或断电）："
                f"{raw or '无记录'}\n"
            )
            stream.flush()
            _write_pending(raw, excerpt)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            f"启动于 {datetime.now():%Y-%m-%d %H:%M:%S} pid={os.getpid()}",
            encoding="utf-8",
        )
    except OSError:
        pass


# ---------------------------------------------------------------- 待上报摘要

def _version() -> str:
    try:
        from app.version import __version__

        return __version__
    except Exception:                 # noqa: BLE001
        return "未知"


def _last_run_excerpt(max_chars: int = 12000) -> str:
    """上一次运行留在 crash.log 里的证据段。

    必须在本次启动的表头写入**之前**调用：``crash.log`` 以
    ``===== MiteProxy 启动`` 分段，最后一段就是刚结束（崩掉）的那次运行。
    """
    try:
        text = crash_path().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    parts = text.split("===== MiteProxy 启动")
    if len(parts) < 2:
        return ""
    # split 把分隔符本身吃掉了，拼回去让日志片段读起来仍是一段完整记录
    return ("===== MiteProxy 启动" + parts[-1])[-max_chars:].strip()


def _hang_tail(max_chars: int = 8000) -> str:
    try:
        return hang_path().read_text(encoding="utf-8", errors="replace")[-max_chars:].strip()
    except OSError:
        return ""


def _write_pending(marker_raw: str, excerpt: str) -> None:
    """把「上次异常退出」的摘要落盘，供下次启动弹窗提示用户是否上报。

    单独存 JSON 而不是让 UI 每次去解析日志：日志格式随时会调整，
    而这份摘要只需要稳定的几个字段。
    """
    data = {
        "detected_at": datetime.now().isoformat(timespec="seconds"),
        "started_at": marker_raw,
        "excerpt": excerpt,
        "hang": _hang_tail(),
        "actions": recent_actions(40),
        "version": _version(),
        # 只在首次发现时提示一次。用户看过没发，下次启动就不再骚扰——
        # 但摘要留着，随时可以在「帮助 → 发送崩溃报告」里补发。
        "prompted": False,
    }
    try:
        path = _pending_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except OSError:
        pass


def pending_crash() -> dict | None:
    """上次异常退出的摘要；没有就返回 None。"""
    try:
        data = json.loads(_pending_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def mark_pending_prompted() -> None:
    """标记「已提示过」，避免每次启动都弹窗骚扰。"""
    data = pending_crash()
    if not data:
        return
    data["prompted"] = True
    try:
        _pending_file().write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except OSError:
        pass


def clear_pending_crash() -> None:
    """上报完成或用户明确不再需要（删除摘要）。"""
    try:
        _pending_file().unlink(missing_ok=True)
    except OSError:
        pass


def build_summary() -> dict:
    """就地组装一份诊断摘要。

    用于「帮助 → 发送崩溃诊断报告」的手动入口：进程没崩（比如刚卡了一阵、
    或者用户就是想顺手反馈）时没有待上报摘要，此时直接采集当前运行至今的
    证据，字段与 :func:`pending_crash` 保持一致，对话框无需区分来源。
    """
    return {
        "detected_at": datetime.now().isoformat(timespec="seconds"),
        "started_at": "",
        "version": _version(),
        "excerpt": _last_run_excerpt(),
        "hang": _hang_tail(),
        "actions": recent_actions(40),
        "prompted": False,
    }


def install() -> bool:
    """装好全部取证钩子。幂等；返回是否成功接管。"""
    global _installed
    if _installed:
        return True

    try:
        path = crash_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open("a", encoding="utf-8", errors="replace")
    except OSError:
        return False                  # 连日志目录都开不了：取证无门但不该拖垮启动

    try:
        # 必须在写本次表头之前读：crash.log 按「启动」分节，最后一段才是
        # 刚崩掉的那次运行；表头一写进去，段就切走了。
        previous = _last_run_excerpt()
        stream.write(
            f"\n===== MiteProxy 启动 {datetime.now():%Y-%m-%d %H:%M:%S} =====\n"
        )
        stream.write(environment() + "\n")
        stream.flush()

        _check_previous_run(stream, _running_marker(), previous)
        _install_faulthandler(stream)
        _install_excepthook(stream)
        _install_thread_hook(stream)
        _install_qt_handler(stream)
    except Exception:                 # noqa: BLE001
        return False

    _installed = True
    note("app_start", f"pid={os.getpid()}")
    return True


def mark_clean_exit() -> None:
    """正常退出：删掉运行标记，下次启动就不会误报「上次异常退出」。"""
    try:
        _running_marker().unlink(missing_ok=True)
    except OSError:
        pass
