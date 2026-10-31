"""内存守护（:mod:`app.memguard`）测试。

重点锁三件事：
1. ``collect_now()`` 真的会回收循环垃圾，并把基线拉回回收后的读数；
2. ``_scan_once()`` 按「增长阈值 / 硬顶」而非固定时间触发，且常规回收受冷却约束；
3. ``start()`` / ``stop()`` 幂等，不会叠出多个守护线程。

阈值与内存读数全部用替身，不依赖真实堆大小——否则用例会在不同机器上飘。
"""

from __future__ import annotations

import gc
import weakref

import pytest

from app import memguard


class _Node:
    """可弱引用的循环对象节点（dict 不支持 weakref，所以用类）。"""

    __slots__ = ("payload", "self_ref", "lst", "__weakref__")


@pytest.fixture(autouse=True)
def _isolate():
    """每个用例前后都复位：停线程 + 清基线，避免用例之间互相污染。"""
    memguard.stop()
    memguard._baseline_mb = 0.0
    memguard._last_collect_at = 0.0
    yield
    memguard.stop()
    memguard._baseline_mb = 0.0
    memguard._last_collect_at = 0.0


class TestCollectNow:
    def test_reclaims_cycle_garbage(self):
        """自引用循环在 del 之后必须被这次 collect 收掉。

        这是整个模块存在的理由：CPython 3.14.0 的增量 GC 不自动回收它们，
        只有显式 collect 才行。用 weakref 精确判定存活——不数 GC 对象总数，
        那个数字会被模块导入等无关开销带偏。
        """
        # 预热：首次 collect 会把 crashreport 一并导入，避免干扰后续观测
        memguard.collect_now("warmup")

        refs = []
        for _ in range(300):
            node = _Node()
            node.payload = b"x" * 4096
            node.self_ref = node          # 自引用
            node.lst = [node]             # 与 list 互相引用
            refs.append(weakref.ref(node))
        del node

        alive_before = sum(1 for r in refs if r() is not None)
        if alive_before == 0:
            pytest.skip("该解释器的自动 GC 已能回收循环垃圾，本用例无意义")

        info = memguard.collect_now("test")

        alive_after = sum(1 for r in refs if r() is not None)
        assert set(info) == {"before", "after", "collected", "elapsed", "reason"}
        assert info["reason"] == "test"
        assert info["collected"] > 0
        assert info["elapsed"] >= 0.0
        # 一次 collect 应当收干净（实测 3.14.0 与正常版本均如此），
        # 而不是只收一部分——「收不干净」正是需要多次触发的信号
        assert alive_after == 0

    def test_updates_baseline_after_collect(self, monkeypatch):
        """回收后基线取回收后的读数，而不是回收前的。"""
        monkeypatch.setattr(memguard, "_rss", lambda: 500.0)
        memguard._baseline_mb = 900.0

        memguard.collect_now("test")

        assert memguard._baseline_mb == 500.0

    def test_counts_accumulate(self, monkeypatch):
        monkeypatch.setattr(memguard, "_rss", lambda: 100.0)
        start = memguard.stats()["collect_count"]
        memguard.collect_now("a")
        memguard.collect_now("b")
        assert memguard.stats()["collect_count"] == start + 2


class TestScan:
    def _no_collect(self, monkeypatch):
        """把 collect_now 换成只记录调用的替身。"""
        calls: list[str] = []

        def fake(reason: str = "manual") -> dict:
            calls.append(reason)
            return {"before": 0.0, "after": 0.0, "collected": 0,
                    "elapsed": 0.0, "reason": reason}

        monkeypatch.setattr(memguard, "collect_now", fake)
        return calls

    def test_first_scan_only_sets_baseline(self, monkeypatch):
        monkeypatch.setattr(memguard, "_rss", lambda: 300.0)
        calls = self._no_collect(monkeypatch)

        memguard._scan_once()

        assert memguard._baseline_mb == 300.0
        assert calls == []

    def test_below_threshold_does_nothing(self, monkeypatch):
        monkeypatch.setattr(memguard, "_rss", lambda: 350.0)
        memguard._baseline_mb = 300.0
        monkeypatch.setattr(memguard, "GROWTH_MB", 128.0)
        calls = self._no_collect(monkeypatch)

        memguard._scan_once()

        assert calls == []

    def test_growth_triggers_collect(self, monkeypatch):
        monkeypatch.setattr(memguard, "_rss", lambda: 500.0)
        memguard._baseline_mb = 300.0
        monkeypatch.setattr(memguard, "GROWTH_MB", 128.0)
        monkeypatch.setattr(memguard, "COOLDOWN", 0.0)
        memguard._last_collect_at = 0.0
        calls = self._no_collect(monkeypatch)

        memguard._scan_once()

        assert len(calls) == 1
        assert "增长" in calls[0]

    def test_cooldown_suppresses_repeat(self, monkeypatch):
        monkeypatch.setattr(memguard, "_rss", lambda: 500.0)
        memguard._baseline_mb = 300.0
        monkeypatch.setattr(memguard, "GROWTH_MB", 128.0)
        monkeypatch.setattr(memguard, "COOLDOWN", 3600.0)
        # 刚回收过：冷却期内同样的增长不再触发
        memguard._last_collect_at = __import__("time").monotonic()
        calls = self._no_collect(monkeypatch)

        memguard._scan_once()

        assert calls == []

    def test_hard_limit_bypasses_cooldown(self, monkeypatch):
        """硬顶是安全阀：冷却期内也要收，而且连收到降下来为止。"""
        monkeypatch.setattr(memguard, "_rss", lambda: 1200.0)
        memguard._baseline_mb = 400.0
        monkeypatch.setattr(memguard, "HARD_LIMIT_MB", 900.0)
        monkeypatch.setattr(memguard, "COOLDOWN", 3600.0)
        memguard._last_collect_at = __import__("time").monotonic()

        calls: list[str] = []

        def fake(reason: str = "manual") -> dict:
            calls.append(reason)
            # 第一次收回落到 500MB（低于硬顶 70%），应当立刻停手
            return {"before": 1200.0, "after": 500.0, "collected": 1,
                    "elapsed": 0.1, "reason": reason}

        monkeypatch.setattr(memguard, "collect_now", fake)

        memguard._scan_once()

        assert len(calls) == 1
        assert "硬顶" in calls[0]

    def test_baseline_follows_drop(self, monkeypatch):
        """内存回落到基线以下时把基线拉下来，后续不会误判为「没增长」。"""
        monkeypatch.setattr(memguard, "_rss", lambda: 200.0)
        memguard._baseline_mb = 600.0
        calls = self._no_collect(monkeypatch)

        memguard._scan_once()

        assert memguard._baseline_mb == 200.0
        assert calls == []


class TestLifecycle:
    def test_start_is_idempotent(self):
        assert memguard.start(delay=3600.0) is True
        first = memguard._thread
        assert memguard.start(delay=3600.0) is True
        assert memguard._thread is first          # 没建第二个线程
        assert memguard.is_running() is True

    def test_stop_terminates_thread(self):
        memguard.start(delay=3600.0)
        thread = memguard._thread
        assert thread is not None and thread.is_alive()

        memguard.stop()

        assert memguard.is_running() is False
        assert not thread.is_alive()              # join 成功，不是僵尸线程
        assert memguard._thread is None

    def test_stop_without_start_is_safe(self):
        memguard.stop()                           # 不该抛
        assert memguard.is_running() is False

    def test_thread_is_daemon(self):
        """必须 daemon：否则退出时守护线程会把进程吊住。"""
        memguard.start(delay=3600.0)
        thread = memguard._thread
        assert thread is not None
        assert thread.daemon is True
        assert thread.name == "mite-mem-guard"

    def test_start_resets_baseline(self, monkeypatch):
        monkeypatch.setattr(memguard, "_rss", lambda: 420.0)
        memguard._baseline_mb = 999.0

        memguard.start(delay=3600.0)

        assert memguard._baseline_mb == 420.0

    def test_stats_shape(self):
        stats = memguard.stats()
        for key in ("running", "baseline_mb", "collect_count",
                    "collected_total", "growth_mb", "hard_limit_mb",
                    "scan_interval"):
            assert key in stats
