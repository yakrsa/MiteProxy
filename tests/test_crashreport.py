"""崩溃取证模块（app.crashreport）的单元测试。

这里只验证「证据留得下来」这件事本身：轨迹写盘、环形裁剪、环境快照、
钩子安装、非正常退出检测。真正的段错误栈由子进程用例
（test_segfault_leaves_stack）验证，不放进本文件的主流程——它会真的把
子进程打死。
"""

from __future__ import annotations

import faulthandler
import sys
import threading
import time

import pytest

from app import crashreport


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """把日志目录指向临时目录，并重置模块级状态。

    退出时把全局钩子还原：``install()`` 会替换 ``sys.excepthook`` /
    ``threading.excepthook`` / Qt 消息处理器，还会让 faulthandler 抓住一个
    临时文件——不收尾会污染同进程里后续的测试。
    """
    monkeypatch.setattr(crashreport, "_log_dir", lambda: tmp_path)
    monkeypatch.setattr(crashreport, "_installed", False)
    monkeypatch.setattr(crashreport, "_action_count", 0)
    monkeypatch.setattr(crashreport, "_rss_cache", (0.0, 0.0))

    saved_excepthook = sys.excepthook
    saved_thread_hook = threading.excepthook
    saved_faulthandler = faulthandler.is_enabled()

    yield tmp_path

    crashreport.stop_watchdog()       # 别把看门狗线程/状态泄漏给后面的用例
    sys.excepthook = saved_excepthook
    threading.excepthook = saved_thread_hook
    faulthandler.disable()
    if saved_faulthandler:            # 本进程原本开着（pytest 有时会开）就恢复
        faulthandler.enable()
    try:
        from PySide6.QtCore import qInstallMessageHandler

        qInstallMessageHandler(None)
    except Exception:                 # noqa: BLE001
        pass


# ---------------------------------------------------------------- 操作轨迹

def test_note_writes_line_with_action_and_detail(isolated):
    crashreport.note("open_detail", "GET https://example.com/a | resp=2048B")

    text = crashreport.actions_path().read_text(encoding="utf-8")
    assert "open_detail" in text
    assert "https://example.com/a" in text
    assert "resp=2048B" in text


def test_note_flattens_newlines_into_one_line(isolated):
    crashreport.note("weird", "line1\nline2\r\nline3")

    lines = [
        ln for ln in crashreport.actions_path().read_text(
            encoding="utf-8").splitlines() if ln.strip()
    ]
    assert len(lines) == 1
    assert "line1 line2  line3" in lines[0]


def test_note_truncates_overlong_detail(isolated):
    crashreport.note("huge", "x" * (crashreport._DETAIL_MAX * 3))

    line = crashreport.actions_path().read_text(encoding="utf-8").strip()
    assert len(line) < crashreport._DETAIL_MAX + 120


def test_note_never_raises_on_odd_input(isolated, monkeypatch):
    """取证代码跑在崩溃路径上，绝不能因为自己的输入把调用方带崩。"""
    crashreport.note("", "")
    crashreport.note("obj", object())          # detail 不是字符串

    # 让写盘目标变成一个目录：open(..., "a") 必然失败，note 必须自己吞掉
    monkeypatch.setattr(crashreport, "actions_path", lambda: isolated)
    crashreport.note("should_not_raise", "x")


def test_recent_actions_returns_tail(isolated):
    for i in range(5):
        crashreport.note(f"step{i}")
    tail = crashreport.recent_actions(limit=2)
    assert len(tail) == 2
    assert "step3" in tail[0]
    assert "step4" in tail[1]


def test_trim_keeps_only_last_lines(isolated):
    path = crashreport.actions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"line{i}" for i in range(crashreport.ACTION_KEEP + 50)) + "\n",
        encoding="utf-8",
    )

    crashreport._trim_actions(path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == crashreport.ACTION_KEEP
    assert lines[-1].startswith(f"line{crashreport.ACTION_KEEP + 49}")


def test_note_trims_automatically_every_batch(isolated, monkeypatch):
    """累计到一批就裁剪，不用等调用方手动处理。"""
    monkeypatch.setattr(crashreport, "ACTION_KEEP", 10)
    monkeypatch.setattr(crashreport, "_ACTION_TRIM_EVERY", 5)

    for i in range(40):
        crashreport.note(f"n{i}")

    lines = crashreport.actions_path().read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 10


# ---------------------------------------------------------------- 环境快照

def test_environment_reports_version_and_platform(isolated):
    text = crashreport.environment()

    assert "版本:" in text
    assert "系统:" in text
    assert "Python:" in text
    from app.version import __version__

    assert __version__ in text


# ---------------------------------------------------------------- 安装与守卫

def test_install_writes_snapshot_and_is_idempotent(isolated):
    assert crashreport.install() is True
    before = crashreport.crash_path().read_text(encoding="utf-8")
    assert "MiteProxy 启动" in before

    # 第二次调用不应重开一个 stream、也不再写一遍启动分隔行
    assert crashreport.install() is True
    after = crashreport.crash_path().read_text(encoding="utf-8")
    assert after.count("MiteProxy 启动") == before.count("MiteProxy 启动")


@pytest.mark.filterwarnings(
    "ignore::pytest.PytestUnhandledThreadExceptionWarning"
)
def test_install_installs_thread_hook(isolated):
    """后台线程未捕获异常必须落盘。

    本用例故意在线程里抛异常，pytest 的线程异常插件会把它再报一遍警告，
    属于测试手段本身产生的噪音，忽略掉。
    """
    crashreport.install()
    # 有效性验证：起个线程抛异常，看有没有落盘（sys.excepthook 管不到线程）
    def _worker():
        raise ValueError("后台线程炸了")

    t = threading.Thread(target=_worker, name="probe-worker")
    t.start()
    t.join(timeout=5)

    text = crashreport.crash_path().read_text(encoding="utf-8")
    assert "线程未捕获异常" in text
    assert "后台线程炸了" in text
    assert "probe-worker" in text


def test_previous_run_marker_reports_abnormal_exit(isolated):
    marker = crashreport._running_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("启动于 2026-10-28 20:43:00 pid=31008", encoding="utf-8")

    crashreport.install()

    text = crashreport.crash_path().read_text(encoding="utf-8")
    assert "上次进程未走完退出流程" in text
    assert "pid=31008" in text
    # 新一次启动要把标记重写成当前进程，供下一次判断
    assert "pid=" in marker.read_text(encoding="utf-8")


def test_mark_clean_exit_removes_marker(isolated):
    crashreport.install()
    marker = crashreport._running_marker()
    assert marker.exists()

    crashreport.mark_clean_exit()
    assert not marker.exists()

    # 干净退出后再启动，不该报「上次异常退出」
    crashreport._installed = False
    crashreport.install()
    text = crashreport.crash_path().read_text(encoding="utf-8")
    assert "上次进程未走完退出流程" not in text


def test_memory_mb_returns_positive():
    """内存采样是轨迹的一部分，取不到会退化成 0 但不应抛。"""
    value = crashreport.memory_mb()
    assert value >= 0.0
    if sys.platform == "win32":
        assert value > 0.0


def test_memory_mb_is_throttled(isolated, monkeypatch):
    calls = {"n": 0}

    def _fake():
        calls["n"] += 1
        return 123.0

    monkeypatch.setattr(crashreport, "_read_rss_mb", _fake)
    monkeypatch.setattr(crashreport, "_rss_cache", (0.0, 0.0))

    first = crashreport.memory_mb()
    second = crashreport.memory_mb()
    assert first == second == 123.0
    assert calls["n"] == 1            # 1 秒内复用缓存，不重复走系统调用


# ---------------------------------------------------------------- 卡死看门狗
#
# 时间相关的用例都靠 monkeypatch 把阈值压到几十毫秒：真实 5s/5s 的配置在
# 测试里既慢又不稳，而判定逻辑本身与具体数值无关。

def _fast_watch(monkeypatch) -> None:
    monkeypatch.setattr(crashreport, "HEARTBEAT_TIMEOUT", 0.3)
    monkeypatch.setattr(crashreport, "_WATCH_TICK", 0.05)
    monkeypatch.setattr(crashreport, "HANG_SAMPLE_EVERY", 0.15)
    monkeypatch.setattr(crashreport, "HANG_SAMPLE_MAX", 3)


def test_watchdog_records_hang_and_recovery(isolated, monkeypatch):
    """主线程不再打心跳 = 界面卡住，必须留下栈与恢复时长。"""
    _fast_watch(monkeypatch)
    crashreport.install()
    crashreport.start_watchdog(grace=0.0)
    assert crashreport.is_watchdog_running()

    time.sleep(0.7)                   # 一直不 beat，模拟卡死
    text = crashreport.hang_path().read_text(encoding="utf-8")
    assert "界面卡死" in text
    assert "主线程栈" in text
    assert "卡死前最后操作" in text

    crashreport.beat()                # 恢复
    time.sleep(0.4)
    assert "已恢复" in crashreport.hang_path().read_text(encoding="utf-8")


def test_watchdog_stays_silent_while_beating(isolated, monkeypatch):
    _fast_watch(monkeypatch)
    crashreport.install()
    crashreport.start_watchdog(grace=0.0)

    end = time.monotonic() + 0.6
    while time.monotonic() < end:
        crashreport.beat()
        time.sleep(0.03)

    assert not crashreport.hang_path().exists()


def test_watchdog_never_exceeds_sample_limit(isolated, monkeypatch):
    """长时间卡死不能把日志刷爆。"""
    _fast_watch(monkeypatch)
    crashreport.install()
    crashreport.start_watchdog(grace=0.0)

    time.sleep(1.5)
    text = crashreport.hang_path().read_text(encoding="utf-8")
    assert text.count("次采样") <= crashreport.HANG_SAMPLE_MAX


def test_stop_watchdog_ends_thread(isolated):
    crashreport.start_watchdog(grace=0.0)
    assert crashreport.is_watchdog_running()
    crashreport.stop_watchdog()
    assert not crashreport.is_watchdog_running()


# ---------------------------------------------------------------- 待上报摘要

def _seed_lost_run(tmp_path) -> None:
    """铺一份「上次崩溃留下的现场」：栈 + 卡死记录 + 操作轨迹 + 运行标记。"""
    (tmp_path / "crash-watch.running").write_text(
        "启动于 2026-10-28 20:40:11 pid=4321", encoding="utf-8")
    (tmp_path / "crash.log").write_text(
        "\n===== MiteProxy 启动 2026-10-28 20:40:11 =====\n版本: 3.0.1\n"
        "\n----- 未捕获异常 20:43:29 -----\n"
        "Windows fatal exception: access violation\n",
        encoding="utf-8",
    )
    (tmp_path / "hang.log").write_text(
        "\n=== 界面卡死 2026-10-28 20:42:10 （已 5.3s 无响应）===\n", encoding="utf-8")
    (tmp_path / "actions.log").write_text(
        "20:42:58.101 [  118.9MB] open_detail | GET https://a.b/c 8.4MB\n",
        encoding="utf-8",
    )


def test_pending_crash_captures_evidence(isolated):
    _seed_lost_run(isolated)
    crashreport.install()

    summary = crashreport.pending_crash()
    assert summary is not None
    assert "pid=4321" in summary["started_at"]
    assert "access violation" in summary["excerpt"]
    assert "界面卡死" in summary["hang"]
    assert summary["actions"]
    assert summary["prompted"] is False


def test_pending_crash_absent_after_clean_exit(isolated):
    """正常退出后再启动不该有摘要——否则每次开机都弹窗。"""
    crashreport.install()
    crashreport.mark_clean_exit()

    crashreport._installed = False
    crashreport.install()

    assert crashreport.pending_crash() is None


def test_mark_pending_prompted_is_not_repeated(isolated):
    _seed_lost_run(isolated)
    crashreport.install()
    assert crashreport.pending_crash()["prompted"] is False

    crashreport.mark_pending_prompted()
    assert crashreport.pending_crash()["prompted"] is True

    crashreport.clear_pending_crash()
    assert crashreport.pending_crash() is None


def test_last_run_excerpt_keeps_marker_prefix(isolated):
    """截断后的片段仍带「启动」标记，排查时才看得出是哪一次运行。

    注意调用时机：``install()`` 之前读，最后一段才是刚崩掉的那次；install()
    内部也正是在写本次表头之前取这份内容的。
    """
    _seed_lost_run(isolated)

    excerpt = crashreport._last_run_excerpt()
    assert excerpt.startswith("===== MiteProxy 启动")
    assert "access violation" in excerpt


def test_build_summary_reports_current_run(isolated):
    """手动入口用的是「当前这次运行」，不是上一次。"""
    crashreport.install()
    crashreport.note("marker_in_current_run", "x")

    summary = crashreport.build_summary()
    assert summary["version"]
    assert "MiteProxy 启动" in summary["excerpt"]
    assert summary["prompted"] is False
