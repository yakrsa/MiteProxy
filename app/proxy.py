"""代理服务：在独立线程中内嵌运行 mitmproxy DumpMaster。

线程模型（见 DESIGN.md 2.4）：
- DumpMaster 跑在自己的 asyncio 事件循环里，由本类放入 daemon 线程；
- 外部（Qt 主线程）只通过 start()/stop() 控制生命周期，不直接触碰 master 内部；
- 关闭时用 loop.call_soon_threadsafe 把 shutdown 投递到事件循环线程执行，
  避免跨线程操作 asyncio 原语。
"""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from typing import Optional

from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster

log = logging.getLogger(__name__)

#: 端口被占用时向后顺延的最大尝试数（从请求端口起连续试 100 个）
PORT_SCAN_TRIES = 100


def _port_bindable(host: str, port: int) -> bool:
    """探测端口能否绑定（bind 后立即关，不监听，只用来查占用）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


class ProxyService:
    """mitmproxy 代理的线程化封装。

    addons: 在 master 启动前注册的 addon 实例列表（MockAddon / CaptureAddon 等）。
    options: 启动时应用的 mitmproxy 选项（如域名映射用 `map_remote`）；
             之后可用 update_options() 热更新，未运行时会被记下待下次启动生效。
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        addons: list | None = None,
        options: dict | None = None,
    ):
        self.host = host
        self.port = port
        self._addons = list(addons or [])
        self._options: dict = dict(options or {})
        self._thread: Optional[threading.Thread] = None
        self._master: Optional[DumpMaster] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------ API

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """启动代理线程（幂等；已在运行则直接返回）。

        启动前先探测端口：被占用就自动顺延到下一个可用端口（实际端口
        回写 self.port）。mitmproxy 是异步绑定、失败只能靠事后 verify
        兜底，这里把绝大多数端口冲突在启动前就消化掉。
        找不到任何可用端口时抛 OSError，由调用方统一收尾。
        """
        if self.running:
            return
        requested = self.port
        chosen = self._pick_port()
        if chosen is None:
            raise OSError(
                f"从端口 {requested} 起连续 {PORT_SCAN_TRIES} 个端口均不可用"
            )
        self.port = chosen
        if chosen != requested:
            log.warning("端口 %s 被占用，代理自动改用 %s", requested, chosen)
        self._thread = threading.Thread(
            target=self._thread_main, name="mitmproxy-proxy", daemon=True
        )
        self._thread.start()
        log.info("代理线程已启动: %s:%s", self.host, self.port)

    def _pick_port(self) -> Optional[int]:
        """从 self.port 起找一个可绑定端口；找不到返回 None。"""
        for offset in range(PORT_SCAN_TRIES):
            candidate = self.port + offset
            if candidate > 65535:
                return None
            if _port_bindable(self.host, candidate):
                return candidate
        return None

    def stop(self, timeout: float = 5.0) -> None:
        """优雅停止代理；超时未退出也不阻塞主流程（daemon 线程会随进程退出）。"""
        master, loop, thread = self._master, self._loop, self._thread
        if thread is None:
            return
        # 线程刚 start 还没跑到 `self._master = master` 时，master/loop 都是
        # None——直接 join 的话 shutdown 没人投递，线程会永久滞留（DumpMaster
        # 一直 run）。先短等 master 就绪再投递（正常路径 master 已就绪，零等待）
        deadline = time.monotonic() + 2.0
        while master is None and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
            master, loop = self._master, self._loop
        if master is not None and loop is not None:
            try:
                loop.call_soon_threadsafe(master.shutdown)
            except RuntimeError:
                # 事件循环已关闭
                pass
        thread.join(timeout)
        if thread.is_alive():
            log.warning("代理线程未在 %ss 内退出", timeout)
        else:
            log.info("代理线程已停止")
        self._thread = None
        self._master = None
        self._loop = None

    def update_options(self, **opts) -> bool:
        """热更新 mitmproxy 选项（如 map_remote / connection_strategy）。

        运行中经 call_soon_threadsafe 投到事件循环线程执行——options 的变更会
        触发 addon 的 configure 钩子，不能从 UI 线程直接改。
        `_options` 始终记录最新值，代理重启（换端口等）后自动带过去。

        返回 True 表示已提交给运行中的代理，False 表示只是记下来待下次启动。
        """
        self._options.update(opts)
        master, loop = self._master, self._loop
        if master is None or loop is None:
            return False
        try:
            loop.call_soon_threadsafe(self._apply_options, dict(opts))
            return True
        except RuntimeError:
            log.warning("事件循环已关闭，选项未应用: %s", list(opts))
            return False

    def _apply_options(self, opts: dict) -> None:
        master = self._master
        if master is None:
            return
        try:
            master.options.update(**opts)
        except Exception:
            log.exception("应用 mitmproxy 选项失败: %s", opts)

    def replay_flow(self, flow) -> bool:
        """把（副本）flow 投入 mitmproxy ClientPlayback 重放队列。

        ClientPlayback.start_replay 不是线程安全的，必须经
        call_soon_threadsafe 投递到事件循环线程执行。
        """
        master, loop = self._master, self._loop
        if master is None or loop is None:
            log.warning("代理未运行，无法重放")
            return False

        def _do_replay() -> None:
            playback = master.addons.get("clientplayback")
            if playback is None:
                log.error("未找到 ClientPlayback addon")
                return
            playback.start_replay([flow])

        try:
            loop.call_soon_threadsafe(_do_replay)
            return True
        except RuntimeError:
            log.warning("事件循环已关闭，无法重放")
            return False

    # -------------------------------------------------------------- internal

    def _thread_main(self) -> None:
        asyncio.run(self._amain())

    async def _amain(self) -> None:
        loop = asyncio.get_running_loop()
        self._loop = loop
        opts = options.Options(listen_host=self.host, listen_port=self.port)
        master = DumpMaster(opts, with_termlog=False, with_dumper=False)
        for addon in self._addons:
            master.addons.add(addon)
        if self._options:
            # 在 run() 之前设置：MapRemote 等 addon 靠 configure 钩子读选项，
            # 此时赋值能保证第一请求就带上映射
            try:
                master.options.update(**self._options)
            except Exception:
                log.exception("应用启动选项失败: %s", self._options)
        self._master = master
        try:
            await master.run()
        except Exception:
            log.exception("代理线程异常退出")
        finally:
            # mitmproxy 的 ProxyServer addon 没有 done() 钩子：master.run()
            # 返回时监听 socket 不会关闭（CLI 场景进程直接退出看不出来）。
            # 嵌入场景必须自己关，否则端口一直被占——「停止代理」后再启动
            # 同端口会 EADDRINUSE，改端口回绑旧端口同样失败。
            try:
                proxyserver = master.addons.get("proxyserver")
                if proxyserver is not None:
                    for inst in list(proxyserver.servers):
                        await inst.stop()
            except Exception:
                log.warning("关闭 mitmproxy 监听 socket 失败", exc_info=True)
            # 只清自己创建的：start() 后立刻 stop() 时，本线程可能还没跑到
            # `self._master = master` 就退出，无条件清 None 会把**后来新启动**的
            # master 一并清掉，UI 状态错乱、replay/stop 全部失灵
            if self._master is master:
                self._master = None
            if self._loop is loop:
                self._loop = None
