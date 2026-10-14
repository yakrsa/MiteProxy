"""跨线程信号桥：mitmproxy 线程 → Qt 主线程的唯一数据通道（DESIGN.md 2.4）。

CaptureAddon 的回调运行在 asyncio 线程，直接碰 Qt 对象会崩溃；
所有数据先过这里的 pyqtSignal（跨线程自动队列投递）。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class FlowBridge(QObject):
    flow_arrived = Signal(dict)
    #: 已存在会话的增量更新（WebSocket 消息到达时行内数据会变）
    flow_updated = Signal(dict)
    #: Mock 规则命中（rule_id）——代理线程 → 规则页计数器
    rule_hit = Signal(str)
    #: Mock 规则运行时错误（rule_id, message）——代理线程 → 规则页 ⚠ 标记
    rule_error = Signal(str, object)
    proxy_state_changed = Signal(bool)  # True=运行中

    def emit_flow(self, summary: dict) -> None:
        self.flow_arrived.emit(summary)

    def emit_flow_update(self, summary: dict) -> None:
        self.flow_updated.emit(summary)

    def emit_rule_hit(self, rule_id: str) -> None:
        self.rule_hit.emit(rule_id)

    def emit_rule_error(self, rule_id: str, message) -> None:
        self.rule_error.emit(rule_id, message)
