"""双击流量列表某条请求弹出的详情对话框（Fiddler 风格：上下结构同时看请求/响应）。

设计要点：
- 竖向分两半——上半部分请求、下半部分响应，二者**同时**可见（不像主面板用页签切换）。
- 请求 / 响应区域直接复用 ``app.ui.detail_panel.MessagePane``，保证与主页详情面板
  观感、能力完全一致（header 表 + body 六视图、搜索高亮、主题切换都白嫖）。
- 取值逻辑与 ``DetailPanel.show_flow`` 同一套（method/pretty_url、status_code/reason、
  get_content / raw_content），避免两处各写一份导致偏差。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QSplitter,
    QVBoxLayout,
)

from app.ui.detail_panel import MessagePane, truncation_flags


class FlowDetailDialog(QDialog):
    """单条请求的完整请求 + 响应，上下分栏同时展示。"""

    def __init__(self, flow, parent=None, wrap_default: bool = True) -> None:
        super().__init__(parent)
        # 窗口级模态：QDialog 的 exec() 默认是**应用模态**，会把整个应用程序
        # ——包括主窗口和拖出去的浮窗——一起冻住，用户感知就是「打开详情后整个
        # 界面卡死、点哪都没反应」。这里只锁父窗口，与项目其余对话框一致
        # （v3.0.1 已把 dialogs / api_panel / fix_panel / collection_dialog 全部
        # 改成 WindowModal，本对话框是最后漏网的一处）。
        self.setWindowModality(Qt.WindowModality.WindowModal)

        # 关闭即销毁。本对话框是「每次双击新建一次」，而 Qt 默认只在 parent 析构
        # 时才清理子对象——不设这个标记，每关一次就留下一整套隐藏的 QDialog，
        # 连带两个 MessagePane 里已经写满文本的 QTextDocument（大响应可达几百 MB）。
        # 反复双击几轮内存就只涨不降，Windows 上最终往往是进程被无声杀掉：连
        # traceback 都没有，外部看就是「卡一下，然后自动退出」——正是本次要查的现象。
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        req = getattr(flow, "request", None)
        res = getattr(flow, "response", None)

        if req is not None:
            self.setWindowTitle(f"{req.method} {req.pretty_url}")
        elif res is not None:
            self.setWindowTitle(f"HTTP {res.status_code}")
        else:
            self.setWindowTitle(self.tr("请求详情"))
        self.resize(960, 760)

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(6)

        self.request_pane = MessagePane(wrap_default=wrap_default)
        self.response_pane = MessagePane(wrap_default=wrap_default)
        splitter.addWidget(self.request_pane)
        splitter.addWidget(self.response_pane)
        splitter.setSizes([360, 360])
        layout.addWidget(splitter, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton(self.tr("关闭"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # 填充内容：与 DetailPanel.show_flow 同一套取值（含 Raw 页首行）
        truncated_sides, truncated_sizes = truncation_flags(flow)
        if req is not None:
            req_first = f"{req.method} {req.pretty_url}".rstrip()
            ver = getattr(req, "http_version", "") or ""
            if ver:
                req_first = f"{req_first} {ver}"
            self.request_pane.show_message(
                f"{req.method} {req.pretty_url}",
                req.headers,
                req.get_content(strict=False),
                len(req.raw_content or b""),
                "request" in truncated_sides,
                truncated_sizes.get("request"),
                req_first,
            )
        else:
            self.request_pane.clear()

        if res is not None:
            res_first = f"HTTP {res.status_code} {res.reason or ''}".strip()
            ver = getattr(res, "http_version", "") or ""
            if ver:
                res_first = f"{ver} {res.status_code} {res.reason or ''}".strip()
            self.response_pane.show_message(
                f"HTTP {res.status_code} {res.reason or ''}".strip(),
                res.headers,
                res.get_content(strict=False),
                len(res.raw_content or b""),
                "response" in truncated_sides,
                truncated_sizes.get("response"),
                res_first,
            )
        else:
            # pending：请求已发出但响应未到，响应半边给明确占位而非「未选择会话」
            self.response_pane.show_message(self.tr("尚未收到响应…"), {}, None, 0)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 的驼峰命名
        """关闭时立刻掐掉所有流式 QTimer。

        超过 RENDER_TEXT_LIMIT 的文本走 QTimer 分块追加，且 interval=0——每个事件
        循环 tick 都喂一块。对话框关了而 timer 还在跑的话，它会继续往一个已经
        看不见的编辑器里把剩下几 MB 全部写完：白烧 CPU，还把整份文档继续扣在
        内存里。定时器虽随 WA_DeleteOnClose 最终会被回收，但「写一个看不见的窗
        口」这段时间完全没必要存在。
        """
        self._stop_streaming()
        super().closeEvent(event)

    def _stop_streaming(self) -> None:
        """停掉请求/响应两侧的流式加载（body + raw 共四处，幂等）。"""
        for pane in (self.request_pane, self.response_pane):
            for stop in (
                getattr(getattr(pane, "body_pane", None), "_stream_stop", None),
                getattr(getattr(pane, "raw_pane", None), "_stop", None),
            ):
                if not callable(stop):
                    continue
                try:
                    stop()
                except RuntimeError:
                    pass          # C++ 侧已析构则无需再停，别让收尾反过来崩一次
