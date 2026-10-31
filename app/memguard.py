"""内存回收守护：绕开 CPython 3.14.0~3.14.4 增量 GC 不回收循环垃圾的缺陷。

## 背景

Python 3.14 把垃圾回收改成了增量式（incremental GC），3.14.0~3.14.4 的实现
存在缺陷：循环引用不再被定时回收，进程内存只涨不降。官方已在 3.14.5 回滚为
3.13 的分代 GC。

抓包主路径恰好是重灾区：每个 TLS 会话在 mitmproxy 里会形成循环引用的对象
图（flow ↔ connection ↔ stream），正常的分代 GC 会定期把它们清掉，有缺陷的
版本则全部堆积。实测（3.14.0，8000 个自引用循环对象）删除引用后 GC 对象数
一个不降、gen0 自动回收次数为 0，只有手动 ``gc.collect()`` 才能回收。

堆到 1.8GB 之后，GC 在遍历时遇到已被写坏的对象（``ob_type`` 无效），触发
``0xC0000005`` 空指针解引用，进程直接消失——没有 Python 栈，因为它崩在
解释器自身的 GC 代码里（``python314.dll`` 偏移 ``0xB2A37``，正是
``test dword [rax+0xA8], 0x4000`` 这条 ``Py_TPFLAGS_HAVE_GC`` 检查）。

## 本模块做什么

独立守护线程按「内存增长」而不是「固定时间」触发 ``gc.collect()``：

- 只按时间回收，空闲时也在白白 stop-the-world；
- 只按阈值回收，涨得慢就永远不触发。

两者结合：每 :data:`SCAN_INTERVAL` 秒读一次常驻内存，相对上次回收后的基线
增长超过 :data:`GROWTH_MB` 就回收一次；另有 :data:`HARD_LIMIT_MB` 硬顶，
超过就连续回收，确保不会再回到 1.8GB。

## 代价

``gc.collect()`` 是 stop-the-world，回收期间所有线程（含 Qt 主线程）暂停。
所以频率受增长阈值约束、两次回收之间强制 :data:`COOLDOWN` 冷却，单次耗时
超过 :data:`SLOW_WARN` 记一条 WARNING，便于事后核对是否影响了手感。

## 与升级解释器的关系

升级到 3.14.5+ 之后本模块仍然可以安全常开：GC 恢复正常后堆增长变慢，阈值
基本不触发，实际开销趋近于零。因此这里不按版本号做条件开关——按版本判断
一旦判断错（比如发行版自编译），反而会漏掉保护。
"""

from __future__ import annotations

import gc
import logging
import threading
import time

log = logging.getLogger(__name__)

#: 巡检间隔（秒）。20 秒足够追上持续抓包的增长速度，又不至于频繁读内存。
SCAN_INTERVAL = 20.0

#: 启动后首次巡检的延迟（秒）。启动阶段本来就在装配界面、加载规则，
#: 此时回收只会白白拖慢冷启动，而且那点内存是必要开销。
START_DELAY = 30.0

#: 相对基线增长多少 MB 触发一次回收。128MB 大致是十几分钟持续抓包的净增量，
#: 低于它没必要付 stop-the-world 的代价。
GROWTH_MB = 128.0

#: 硬顶（MB）。到这个量级就连续回收，不再等增长阈值和冷却。
#: 崩溃现场是 1878MB——取一半以下留足缓冲。
HARD_LIMIT_MB = 900.0

#: 两次常规回收之间的最小间隔（秒），避免高流量下反复全量回收造成抖动。
COOLDOWN = 30.0

#: 硬顶模式下最多连续回收几轮（每轮都会重新读一次内存）。
EMERGENCY_ROUNDS = 3

#: 单次回收耗时超过该秒数就记 WARNING（说明已经开始影响界面响应）。
SLOW_WARN = 0.5

#: 回收后内存降到硬顶的多少比例以下就认为解除告警。
_RELIEF_RATIO = 0.7

_lock = threading.Lock()          # 保证同一时刻只有一次 gc.collect()
_stop = threading.Event()
_thread: threading.Thread | None = None
_baseline_mb = 0.0                # 上次回收后的内存基线
_last_collect_at = 0.0            # 上次回收的 monotonic 时刻
_collect_count = 0
_collected_total = 0


def _rss() -> float:
    """当前常驻内存（MB）。复用 crashreport 的实现，取不到返回 0.0。"""
    try:
        from app.crashreport import memory_mb

        return memory_mb()
    except Exception:             # noqa: BLE001 - 监控辅助，取不到不致命
        return 0.0


def collect_now(reason: str = "manual") -> dict:
    """立即执行一次全量回收，返回本次结果。

    返回 ``{"before", "after", "collected", "elapsed", "reason"}``（内存单位
    MB，耗时单位秒）。本函数不抛异常——它跑在守护线程里，抛出去只会静默
    杀死线程。
    """
    global _baseline_mb, _last_collect_at, _collect_count, _collected_total

    if not _lock.acquire(timeout=10.0):
        return {"before": 0.0, "after": 0.0, "collected": 0,
                "elapsed": 0.0, "reason": reason}

    try:
        before = _rss()
        started = time.monotonic()
        try:
            collected = gc.collect()
        except Exception:         # noqa: BLE001
            log.exception("内存回收执行失败")
            return {"before": before, "after": before, "collected": 0,
                    "elapsed": 0.0, "reason": reason}
        elapsed = time.monotonic() - started
        after = _rss()

        _collect_count += 1
        _collected_total += collected
        _last_collect_at = time.monotonic()
        # 基线取回收后的读数；取不到就退回 before，避免下次拿 0 当基线
        _baseline_mb = after if after > 0 else before

        freed = (before - after) if (before > 0 and after > 0) else 0.0
        message = (
            "内存回收：%.1fMB → %.1fMB（释放 %.1fMB，回收 %d 个循环，耗时 %.2fs，%s）"
            % (before, after, freed, collected, elapsed, reason)
        )
        if elapsed >= SLOW_WARN:
            log.warning("%s —— 回收耗时偏长，界面在此期间会短暂卡顿", message)
        else:
            log.info("%s", message)

        # 记进操作轨迹：崩溃后与 crash.log 对照时，能看出内存是被谁压下来的
        try:
            from app import crashreport

            crashreport.note(
                "gc_collect",
                "%.0fMB→%.0fMB 回收%d个 用时%.2fs (%s)"
                % (before, after, collected, elapsed, reason),
            )
        except Exception:         # noqa: BLE001
            pass

        return {"before": before, "after": after, "collected": collected,
                "elapsed": elapsed, "reason": reason}
    finally:
        _lock.release()


def _scan_once() -> None:
    """一次巡检：读内存，按硬顶 / 增长阈值决定是否回收。"""
    global _baseline_mb

    rss = _rss()
    if rss <= 0:                  # 读不到（非 Windows 或系统调用失败）就跳过
        return

    # 首次运行，或内存已回落到基线以下（主动释放 / 系统回收）：把基线拉下来
    if _baseline_mb <= 0 or rss < _baseline_mb:
        _baseline_mb = rss
        return

    if rss >= HARD_LIMIT_MB:
        # 硬顶不看冷却：安全优先，宁可卡一下也别再堆到 1.8GB 崩掉
        for _ in range(EMERGENCY_ROUNDS):
            info = collect_now("超过硬顶 %.0fMB（当前 %.0fMB）" % (HARD_LIMIT_MB, rss))
            if info["after"] <= 0 or info["after"] < HARD_LIMIT_MB * _RELIEF_RATIO:
                return
        log.error("内存回收后仍高于硬顶的 %.0f%%，可能需要检查是否真泄漏",
                  _RELIEF_RATIO * 100)
        return

    grown = rss - _baseline_mb
    if grown < GROWTH_MB:
        return
    if time.monotonic() - _last_collect_at < COOLDOWN:
        return
    collect_now("增长 %.0fMB（当前 %.0fMB）" % (grown, rss))


def _loop(delay: float) -> None:
    """守护线程主循环。"""
    if _stop.wait(delay):
        return
    while not _stop.is_set():
        try:
            _scan_once()
        except Exception:         # noqa: BLE001 - 守护线程不能死
            log.exception("内存守护巡检异常")
        if _stop.wait(SCAN_INTERVAL):
            return


def start(delay: float = START_DELAY) -> bool:
    """启动内存守护。幂等：已启动时只返回 True，不重复建线程。"""
    global _thread, _baseline_mb

    if _thread is not None and _thread.is_alive():
        return True

    _stop.clear()
    _baseline_mb = _rss()          # 以启动时内存为基线，避免一启动就回收
    thread = threading.Thread(
        target=_loop, args=(max(0.0, delay),), name="mite-mem-guard", daemon=True
    )
    _thread = thread
    thread.start()

    log.info(
        "内存守护已启动（间隔 %.0fs，增长阈值 %.0fMB，硬顶 %.0fMB，Python %s）",
        SCAN_INTERVAL, GROWTH_MB, HARD_LIMIT_MB, _python_version(),
    )
    return True


def _python_version() -> str:
    import platform

    return platform.python_version()


def stop() -> None:
    """停止守护线程（退出路径用：没必要在关窗时再跑一次全量回收）。"""
    global _thread

    _stop.set()
    thread = _thread
    _thread = None
    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def stats() -> dict:
    """运行统计（测试与「关于」页展示用）。"""
    return {
        "running": is_running(),
        "baseline_mb": round(_baseline_mb, 1),
        "collect_count": _collect_count,
        "collected_total": _collected_total,
        "growth_mb": GROWTH_MB,
        "hard_limit_mb": HARD_LIMIT_MB,
        "scan_interval": SCAN_INTERVAL,
    }
