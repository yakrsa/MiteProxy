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

from app.ui.detail_panel import MessagePane


class FlowDetailDialog(QDialog):
    """单条请求的完整请求 + 响应，上下分栏同时展示。"""

    def __init__(self, flow, parent=None, wrap_default: bool = True) -> None:
        super().__init__(parent)
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

        # 填充内容：与 DetailPanel.show_flow 同一套取值
        if req is not None:
            self.request_pane.show_message(
                f"{req.method} {req.pretty_url}",
                req.headers,
                req.get_content(strict=False),
                len(req.raw_content or b""),
            )
        else:
            self.request_pane.clear()

        if res is not None:
            self.response_pane.show_message(
                f"HTTP {res.status_code} {res.reason or ''}".strip(),
                res.headers,
                res.get_content(strict=False),
                len(res.raw_content or b""),
            )
        else:
            # pending：请求已发出但响应未到，响应半边给明确占位而非「未选择会话」
            self.response_pane.show_message(self.tr("尚未收到响应…"), {}, None, 0)
