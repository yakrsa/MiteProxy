"""API 调试页：构建请求 → 直发 → 就地看响应（对齐 Postman 的最小核心）。

线程模型与 proxy.py 同款：http.client 阻塞调用放 daemon 线程，
结果经 Qt 信号回主线程——UI 线程永不碰 socket。
响应显示复用 BodyPane（JSON 着色 / 表单 / 图片 / 十六进制全套免费拿到）。
"""

from __future__ import annotations

import json
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import httpclient
from app.httpclient import ApiResponse
from app.ui.detail_panel import BodyPane
from app.ui import theme
from app.textutil import decode_body

METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]

#: 请求 body 输入上限（超出直接拦，别等线程里炸）
MAX_BODY_INPUT = 50 * 1024 * 1024


class ApiPanel(QWidget):
    """工具页第 4 子页：API 调试。"""

    #: 请求完成（后台线程 → 主线程）；payload 是 ApiResponse
    finished = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sending = False
        self._seq = 0  # 防竞态：请求序号，回来的结果序号旧于当前则丢弃
        self._build_ui()
        self.finished.connect(self._on_finished)
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._on_send)

    # ------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 请求行：方法 + URL + 校验 + 发送
        row = QHBoxLayout()
        self.method_combo = QComboBox()
        for m in METHODS:
            self.method_combo.addItem(m, m)
        self.method_combo.setCurrentText("GET")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://api.example.com/v1/user?id=1")
        self.verify_cb = QCheckBox(self.tr("校验证书"))
        self.verify_cb.setToolTip(
            self.tr("调试对象常是自签 / 内网证书，默认跳过校验；\n"
            "要验证正式证书链再勾上。")
        )
        self.send_btn = QPushButton(self.tr("发送"))
        self.send_btn.clicked.connect(self._on_send)
        row.addWidget(self.method_combo)
        row.addWidget(self.url_edit, stretch=1)
        row.addWidget(self.verify_cb)
        row.addWidget(self.send_btn)
        layout.addLayout(row)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # 上半：headers 表 + 请求 body
        req_widget = QWidget()
        req_layout = QVBoxLayout(req_widget)
        req_layout.setContentsMargins(0, 0, 0, 0)
        req_layout.setSpacing(3)

        self.headers_table = QTableWidget(0, 2)
        self.headers_table.setHorizontalHeaderLabels([self.tr("请求 Header"), "Value"])
        self.headers_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.headers_table.verticalHeader().setVisible(False)
        self.headers_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.headers_table.setMaximumHeight(110)
        req_layout.addWidget(self.headers_table)

        hbtn_row = QHBoxLayout()
        add_h = QPushButton(self.tr("添加 Header"))
        add_h.clicked.connect(
            lambda: self.headers_table.insertRow(self.headers_table.rowCount())
        )
        del_h = QPushButton(self.tr("删除选中行"))
        del_h.clicked.connect(self._delete_header_row)
        hbtn_row.addWidget(add_h)
        hbtn_row.addWidget(del_h)
        hbtn_row.addStretch(1)
        req_layout.addLayout(hbtn_row)

        req_layout.addWidget(QLabel(self.tr("请求 Body（GET / HEAD 时忽略）：")))
        self.body_edit = QPlainTextEdit()
        self.body_edit.setMaximumHeight(110)
        font = QFont("ui-monospace, SF Mono, Menlo, Consolas, monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.body_edit.setFont(font)
        self.body_edit.setPlaceholderText(self.tr('如 {"name": "张三"}，或表单 a=1&b=2'))
        req_layout.addWidget(self.body_edit)
        splitter.addWidget(req_widget)

        # 下半：响应（状态行 + BodyPane 复用详情面板的六模式渲染）
        resp_widget = QWidget()
        resp_layout = QVBoxLayout(resp_widget)
        resp_layout.setContentsMargins(0, 0, 0, 0)
        resp_layout.setSpacing(3)

        self.resp_label = QLabel(self.tr("尚未发送"))
        self.resp_label.setStyleSheet(f"color: {theme.css('hint')};")
        self._resp_kind = "hint"        # 主题切换时按最近一次结果重染
        theme.add_listener(self._retheme)
        resp_layout.addWidget(self.resp_label)

        # 响应 Header 表：API 调试页原本只把响应头「数了一下」，从不渲染，
        # 这里补上与详情面板一致的响应头列表（见 _fill_resp_headers）。
        self.resp_headers_table = QTableWidget(0, 2)
        self.resp_headers_table.setHorizontalHeaderLabels(
            [self.tr("响应 Header"), "Value"]
        )
        self.resp_headers_table.horizontalHeader().setStretchLastSection(True)
        self.resp_headers_table.verticalHeader().setVisible(False)
        self.resp_headers_table.setAlternatingRowColors(True)
        self.resp_headers_table.setShowGrid(False)
        self.resp_headers_table.verticalHeader().setDefaultSectionSize(22)
        self.resp_headers_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.resp_headers_table.setMaximumHeight(140)
        resp_layout.addWidget(self.resp_headers_table)

        self.resp_pane = BodyPane(wrap_default=True)
        resp_layout.addWidget(self.resp_pane, stretch=1)
        splitter.addWidget(resp_widget)

        splitter.setSizes([340, 460])
        layout.addWidget(splitter, stretch=1)

    # ------------------------------------------------------------ 对外

    def load_request(
        self,
        method: str = "GET",
        url: str = "",
        headers: dict | None = None,
        body: str = "",
    ) -> None:
        """从流量列表带入一个请求（见 main_window._send_request_to_api）。"""
        idx = self.method_combo.findData((method or "GET").upper())
        self.method_combo.setCurrentIndex(max(idx, 0))
        self.url_edit.setText(url or "")
        self.headers_table.setRowCount(0)
        for k, v in (headers or {}).items():
            if not k:
                continue
            row = self.headers_table.rowCount()
            self.headers_table.insertRow(row)
            self.headers_table.setItem(row, 0, QTableWidgetItem(str(k)))
            self.headers_table.setItem(row, 1, QTableWidgetItem(str(v)))
        self.body_edit.setPlainText(body or "")
        self.resp_label.setText(self.tr("已带入请求，点击「发送」（或 Ctrl+Return）"))
        self.resp_pane.clear()
        self._fill_resp_headers([])

    def set_body_text(self, text: str) -> None:
        """「在工具页中打开 body」路径：只灌请求 body。"""
        self.body_edit.setPlainText(text)

    def is_sending(self) -> bool:
        return self._sending

    # ------------------------------------------------------------ 发送

    def _collect_headers(self) -> dict:
        headers = {}
        for row in range(self.headers_table.rowCount()):
            k_item = self.headers_table.item(row, 0)
            v_item = self.headers_table.item(row, 1)
            if k_item is None or not k_item.text().strip():
                continue
            headers[k_item.text().strip()] = v_item.text() if v_item else ""
        return headers

    def _on_send(self) -> None:
        if self._sending:
            return
        url = self.url_edit.text().strip()
        if not url:
            self.resp_label.setText(self.tr("请先填 URL"))
            return
        method = self.method_combo.currentData() or "GET"
        body_text = self.body_edit.toPlainText()
        if len(body_text.encode("utf-8")) > MAX_BODY_INPUT:
            self.resp_label.setText(self.tr("请求 body 超过 50MB 上限"))
            return
        headers = self._collect_headers()
        body = body_text.encode("utf-8") if body_text else b""
        verify = self.verify_cb.isChecked()

        self._sending = True
        self._seq += 1
        seq = self._seq
        self.send_btn.setEnabled(False)
        self.send_btn.setText(self.tr("发送中…"))
        self.resp_label.setText(self.tr("请求中…"))

        thread = threading.Thread(
            target=self._worker,
            args=(seq, method, url, headers, body, verify),
            daemon=True,
            name="api-debug-send",
        )
        thread.start()

    def _worker(self, seq: int, method: str, url: str,
                headers: dict, body: bytes, verify: bool) -> None:
        result = httpclient.send_request(
            method, url, headers=headers, body=body, verify=verify
        )
        self.finished.emit((seq, result))

    def _on_finished(self, payload) -> None:
        seq, result = payload
        if seq != self._seq:
            return  # 旧请求的结果，丢弃（用户连点时按最后一把算）
        self._sending = False
        self.send_btn.setEnabled(True)
        self.send_btn.setText(self.tr("发送"))
        self._show_response(result)

    def _show_response(self, result: ApiResponse) -> None:
        if not result.ok:
            self._resp_kind = "error"
            self.resp_label.setText(f"✗ {result.error}（{result.elapsed_ms}ms）")
            self.resp_label.setStyleSheet(f"color: {theme.css('error')};")
            self.resp_pane.clear()
            self._fill_resp_headers([])
            return
        headers = dict(result.headers)  # dict 即可满足 BodyPane 的 .get 需求
        size = len(result.body)
        self._resp_kind = "ok" if 200 <= result.status < 400 else "error"
        self.resp_label.setStyleSheet(f"color: {theme.css(self._resp_kind)};")
        self.resp_label.setText(
            self.tr('HTTP {0} {1} · {2}ms · {3} 字节 · {4} 个响应头').format(result.status, result.reason, result.elapsed_ms, size, len(result.headers))
        )
        # body 已由 httpclient 解压；raw_len 传线上原始（压缩后）长度，BodyPane 据此显示「已解压」提示
        self.resp_pane.show_body(headers, result.body, raw_len=result.raw_len or size)
        # 响应 Header 表（见 self.resp_headers_table）
        self._fill_resp_headers(result.headers)

    def _retheme(self) -> None:
        """主题切换：响应状态行按最近一次结果重染。"""
        self.resp_label.setStyleSheet(f"color: {theme.css(self._resp_kind)};")

    def _fill_resp_headers(self, headers) -> None:
        """把响应头渲染成 [(name, value)] 列表；空列表 → 清空。"""
        self.resp_headers_table.setRowCount(0)
        if not headers:
            return
        self.resp_headers_table.setRowCount(len(headers))
        for i, (name, value) in enumerate(headers):
            self.resp_headers_table.setItem(i, 0, QTableWidgetItem(str(name)))
            self.resp_headers_table.setItem(i, 1, QTableWidgetItem(str(value)))

    def _delete_header_row(self) -> None:
        for idx in sorted(
            {i.row() for i in self.headers_table.selectedIndexes()}, reverse=True
        ):
            self.headers_table.removeRow(idx)


def preview_text(body: bytes, content_type: str = "", limit: int = 2000) -> str:
    """响应 body 的纯文本预览（供测试与状态栏提示用，非 UI 主路径）。"""
    text = decode_body(body, content_type)
    if text is None:
        return body[:limit].hex()
    return text[:limit]
