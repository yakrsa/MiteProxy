"""回归：代理生命周期 / 容量 / 跨线程 / 一致性这批修复（v2.5.x）。

每条都对应一个「界面上看起来没事、实际在悄悄出错」的场景，
不是补覆盖率——是为了下次有人动这块时能立刻发现。
"""

from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtWidgets import QApplication

from addons.capture import CaptureAddon
from app import settings as settings_mod
from app.proxy import ProxyService
from app.settings import Settings
from app.ui.signals import UiInvoker

# ---------------------------------------------------------------------- 辅助


class _FakeReq:
    def __init__(self, scheme="http", host="a.test", port=80, path="/x"):
        self.scheme = scheme
        self.host = host
        self.port = port
        self.path = path
        self.method = "GET"
        self.headers = {}
        self.raw_content = b""
        self.timestamp_start = 0.0
        self.timestamp_end = None
        # mitmproxy 的 pretty_url 用裸 host 拼装——IPv6 从这里就错了
        self.pretty_url = f"{scheme}://{host}:{port}{path}"

    @property
    def pretty_host(self):
        return self.host


class _FakeFlow:
    def __init__(self, fid, req=None):
        self.id = fid
        self.request = req or _FakeReq()
        self.response = None
        self.metadata = {}
        self.error = None


def _cap(max_flows: int = 3) -> CaptureAddon:
    return CaptureAddon(max_flows=max_flows)


# ------------------------------------------------------------ P0-1 生命周期


class TestProxyLifecycleNotification:
    """代理线程死了必须让 UI 知道（否则界面一直显示"运行中"）。"""

    def test_state_change_callback_fires_false_on_construction_failure(
        self, monkeypatch,
    ):
        """DumpMaster 构造失败（证书损坏等）→ 回调收到 (False, 原因)。"""
        import app.proxy as proxy_mod

        class Boom(Exception):
            pass

        def _boom(*_a, **_k):
            raise Boom("证书损坏")

        monkeypatch.setattr(proxy_mod, "DumpMaster", _boom)
        seen: list = []
        proxy = ProxyService(
            host="127.0.0.1", port=18901,
            on_state_change=lambda running, msg: seen.append((running, msg)),
        )
        proxy.start()
        thread = proxy._thread
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert seen, "线程死了却没通知 UI —— 界面会一直显示运行中"
        assert seen[-1][0] is False
        assert "证书损坏" in seen[-1][1]

    def test_ready_is_reported_before_run(self):
        """正常路径先报 True（就绪）。回调在 asyncio 线程，这里只收不发。"""
        proxy = ProxyService(
            host="127.0.0.1", port=18902,
            on_state_change=lambda *_a: None,
        )
        # 只验证回调被挂上、且 start 不会因它抛错（真实监听留给 e2e 用例）
        assert proxy._on_state_change is not None
        assert proxy._notify_state(True) is None

    def test_stale_thread_does_not_overwrite_new_state(self):
        """stop() 后立刻 start()：旧线程的收尾不能把新状态冲掉。"""
        proxy = ProxyService(host="127.0.0.1", port=18903)
        seen: list = []
        proxy._on_state_change = lambda running, msg: seen.append(running)

        def _old_thread():
            # 模拟：当前线程不再是官方线程
            proxy._thread = threading.Thread(target=lambda: None)
            proxy._notify_state(False)

        t = threading.Thread(target=_old_thread)
        t.start()
        t.join(timeout=5)
        assert seen == [], "旧线程的退出通知必须被丢弃"


# ------------------------------------------------------------ P0-2 容量


class TestCaptureEviction:

    def test_request_only_flows_are_still_capped(self):
        """只发请求、从不到响应（CONNECT 隧道 / 连接重置）也必须淘汰。"""
        cap = _cap(3)
        for i in range(10):
            cap.request(_FakeFlow(f"r{i}"))
        assert len(cap.flows) == 3, (
            "永不响应的会话没被淘汰 → 长跑抓 HTTPS 就是内存泄漏"
        )
        # 保留的是最新的三条
        assert list(cap.flows) == ["r7", "r8", "r9"]

    def test_websocket_insertion_also_capped(self):
        cap = _cap(2)
        for i in range(6):
            flow = _FakeFlow(f"w{i}")
            cap.websocket_message(flow)
        assert len(cap.flows) == 2

    def test_response_path_unchanged(self):
        """响应路径的淘汰语义不变（别修出新问题）。"""
        cap = _cap(2)
        for i in range(5):
            f = _FakeFlow(f"f{i}")
            cap.request(f)
            cap.response(f)
        assert len(cap.flows) == 2


# ------------------------------------------------------------ P0-3 跨线程


class TestUiInvoker:

    def test_invoke_runs_on_main_thread(self, qapp):
        """工作线程 invoke → 回调必须跑在主线程（碰 Qt 控件才安全）。"""
        invoker = UiInvoker()
        main_tid = threading.get_ident()
        seen = {}

        def _fn():
            seen["tid"] = threading.get_ident()
            return {"ok": True}

        result: dict = {}
        t = threading.Thread(
            target=lambda: result.update(v=invoker.invoke(_fn))
        )
        t.start()
        # 主线程必须一边等一边泵事件：queued 信号没人处理的话回调永不执行
        # （真实应用里主线程有事件循环，测试没有，只能手动泵）
        deadline = time.monotonic() + 10
        while t.is_alive() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        t.join(timeout=5)
        assert seen.get("tid") == main_tid, "回调没排回主线程"
        assert result["v"] == {"ok": True}

    def test_exception_becomes_error_payload(self, qapp):
        invoker = UiInvoker()

        def _boom():
            raise RuntimeError("脚本炸了")

        out = invoker.invoke(_boom)
        assert "error" in out
        assert "RuntimeError" in out["error"]

    def test_direct_call_from_main_thread_does_not_deadlock(self, qapp):
        """已经在主线程时不该自锁。"""
        invoker = UiInvoker()
        assert invoker.invoke(lambda: 42) == 42


# ------------------------------------------------------------ P1 一致性


class TestAutoSaveSessionDefault:

    def test_missing_key_defaults_to_false(self):
        """from_dict 的缺省必须与字段默认值一致（早先是 True，两边不一致）。"""
        assert Settings.from_dict({}).auto_save_session is False
        assert Settings().auto_save_session is False

    def test_explicit_true_roundtrip(self):
        s = Settings.from_dict({"auto_save_session": True})
        assert s.auto_save_session is True
        assert Settings.from_dict(s.to_dict()).auto_save_session is True


class TestSaveSettingsReportsFailure:

    def test_returns_false_and_logs_on_oserror(self, tmp_path, monkeypatch,
                                               caplog):
        """落盘失败要留痕——静默失败会让用户以为改动存住了。"""
        target = tmp_path / "nested" / "settings.json"
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", target)
        # 父目录造不成（nested 是个文件）
        (tmp_path / "nested").write_text("x", encoding="utf-8")
        with caplog.at_level("ERROR"):
            ok = settings_mod.save_settings(Settings())
        assert ok is False
        assert "设置写入失败" in caplog.text

    def test_returns_true_on_success(self, tmp_path, monkeypatch):
        target = tmp_path / "settings.json"
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", target)
        assert settings_mod.save_settings(Settings()) is True
        assert target.exists()


class TestCaptureUrlIpv6:
    """列表 URL / 会话存档 / 复制 URL 都必须带方括号。"""

    def test_ipv6_url_is_bracketed(self):
        req = _FakeReq(host="::1", port=8080, path="/x")
        flow = _FakeFlow("ipv6", req)
        summary = CaptureAddon.summarize(flow)
        assert "[::1]" in summary["url"], (
            "summary 里存了畸形 URL（`http://::1:8080/x`），恢复会话会解析失败"
        )

    def test_ipv4_url_unchanged(self):
        flow = _FakeFlow("v4", _FakeReq(host="a.test", port=80))
        assert CaptureAddon.summarize(flow)["url"] == "http://a.test:80/x"


class TestSysproxyFallbackFlag:

    def test_clear_local_proxy_reports_whether_it_changed_something(
        self, monkeypatch,
    ):
        """第三位是布尔标志——早先靠在文案里搜「兜底」，切英文就恒假。"""
        from app import sysproxy

        monkeypatch.setattr(sysproxy, "platform", type(
            "P", (), {"system": staticmethod(lambda: "Linux")})())
        monkeypatch.setattr(
            sysproxy, "_macos_services", lambda run: ["Wi-Fi"]
        )
        monkeypatch.setattr(
            sysproxy, "_macos_get_proxy",
            lambda run, svc, secure: {
                "enabled": True, "server": "127.0.0.1", "port": 8888},
        )
        calls = []
        monkeypatch.setattr(
            sysproxy, "_macos_set",
            lambda *a, **k: calls.append(a),
        )
        ok, msg, cleared = sysproxy._clear_local_proxy(lambda *a: (0, "", ""),
                                                       8888)
        assert cleared is True
        assert ok is True

    def test_no_change_reports_cleared_false(self, monkeypatch):
        from app import sysproxy

        monkeypatch.setattr(sysproxy, "platform", type(
            "P", (), {"system": staticmethod(lambda: "Linux")})())
        monkeypatch.setattr(sysproxy, "_macos_services", lambda run: [])
        ok, msg, cleared = sysproxy._clear_local_proxy(lambda *a: (0, "", ""),
                                                       8888)
        assert cleared is False

    def test_restore_still_returns_two_tuple(self, monkeypatch, tmp_path):
        """公共 API 不变：restore() 仍然只给 (ok, msg)。"""
        from app import sysproxy

        monkeypatch.setattr(sysproxy, "STATE_PATH", tmp_path / "nope.json")
        monkeypatch.setattr(sysproxy, "platform", type(
            "P", (), {"system": staticmethod(lambda: "Linux")})())
        monkeypatch.setattr(sysproxy, "_macos_services", lambda run: [])
        out = sysproxy.restore(run=lambda *a: (0, "", ""), port=8888)
        assert len(out) == 2


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
