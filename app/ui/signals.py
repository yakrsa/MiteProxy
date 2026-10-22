"""跨线程信号桥：mitmproxy 线程 → Qt 主线程的唯一数据通道（DESIGN.md 2.4）。

CaptureAddon 的回调运行在 asyncio 线程，直接碰 Qt 对象会崩溃；
所有数据先过这里的 pyqtSignal（跨线程自动队列投递）。
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QT_TRANSLATE_NOOP, QCoreApplication, Signal

log = logging.getLogger(__name__)

#: 主线程排队的失败文案（静态方法/无 self.tr 时用 NOOP + 运行时 translate）
UI_ERR_TIMEOUT = QT_TRANSLATE_NOOP("UiInvoker", "UI 线程无响应（等待超时）")
UI_ERR_NO_RESULT = QT_TRANSLATE_NOOP("UiInvoker", "回调未返回结果")


class FlowBridge(QObject):
    flow_arrived = Signal(dict)
    #: 已存在会话的增量更新（WebSocket 消息到达时行内数据会变）
    flow_updated = Signal(dict)
    #: Mock 规则命中（rule_id）——代理线程 → 规则页计数器
    rule_hit = Signal(str)
    #: Mock 规则运行时错误（rule_id, message）——代理线程 → 规则页 ⚠ 标记
    rule_error = Signal(str, object)
    #: 代理真实生命周期（True=已就绪开始监听 / False=线程退出）。
    #: 由 ProxyService 在 asyncio 线程里 emit（跨线程 emit 是安全的），
    #: UI 靠它把"界面显示运行中、实际线程已死"的假象纠正过来——
    #: 否则 DumpMaster 构造失败（证书损坏等）时按钮会永远停在"停止代理"，
    #: 用户以为在抓包，其实一条都没记。message 是可读的失败原因（可能为空）
    proxy_state_changed = Signal(bool, str)
    #: 系统代理接管/还原结果（后台线程 → 主线程状态栏提示）
    sysproxy_done = Signal(bool, str)
    #: 断点命中：(flow, phase) —— 代理线程挂住了这条会话，等 UI 改完放行
    flow_intercepted = Signal(object, str)

    def emit_flow(self, summary: dict) -> None:
        self.flow_arrived.emit(summary)

    def emit_flow_update(self, summary: dict) -> None:
        self.flow_updated.emit(summary)

    def emit_rule_hit(self, rule_id: str) -> None:
        self.rule_hit.emit(rule_id)

    def emit_rule_error(self, rule_id: str, message) -> None:
        self.rule_error.emit(rule_id, message)

    def emit_intercepted(self, flow, phase: str) -> None:
        self.flow_intercepted.emit(flow, phase)


class UiInvoker(QObject):
    """把可调用对象排到 Qt 主线程执行，并同步等它返回结果。

    用途：MCP 写操作。MCP 服务跑在 ``ThreadingHTTPServer`` 的工作线程里，
    而写回调要碰 Qt 控件和模型（工具栏按钮、规则表）——从非 GUI 线程
    直接碰是未定义行为，macOS 上表现为渲染错乱甚至随机崩溃。

    信号跨线程 emit 由 Qt 排到主线程；再用 ``threading.Event`` 等结果，
    让调用方（JSON-RPC 处理）保持同步语义。已经就在主线程时是
    DirectConnection，立即执行、不会自锁。

    超时是为了兜底：主线程若正卡在模态对话框里，宁可让 RPC 报错返回，
    也不能把工作线程永久挂住。
    """

    #: 载荷是一个无参可调用对象（结果写回闭包里的 dict）
    _requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 刻意用默认 AutoConnection：跨线程自动排到主线程，同线程则直接
        # 执行。写死 QueuedConnection 的话，主线程自己调用也得等一轮事件
        # 循环——在没有泵事件的地方（测试、启动早期）会白白卡到超时
        self._requested.connect(self._execute)

    def _execute(self, fn) -> None:
        try:
            fn()
        except Exception:
            log.exception("主线程执行回调失败")

    def invoke(self, fn, timeout: float = 10.0):
        """在主线程执行 ``fn``，返回它的返回值；失败返回 ``{"error": ...}``。"""
        box: dict = {}
        done = threading.Event()

        def wrapped() -> None:
            try:
                box["result"] = fn()
            except Exception as e:      # noqa: BLE001 - 兜住后转成 RPC 错误
                log.exception("MCP 写操作执行失败")
                box["result"] = {"error": f"{type(e).__name__}: {e}"}
            finally:
                done.set()

        self._requested.emit(wrapped)
        if not done.wait(timeout):
            return {"error": QCoreApplication.translate(
                "UiInvoker", UI_ERR_TIMEOUT)}
        return box.get("result") or {"error": QCoreApplication.translate(
            "UiInvoker", UI_ERR_NO_RESULT)}
