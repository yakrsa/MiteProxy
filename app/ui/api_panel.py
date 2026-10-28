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
    QInputDialog,
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

from app import api_collections as store
from app import httpclient
from app.httpclient import ApiResponse
from app.ui import icons, theme
from app.ui.collection_dialog import CollectionDialog
from app.ui.detail_panel import BodyPane
from app.textutil import decode_body

METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]

#: body 模式：普通 JSON/文本；GraphQL（组装 {"query","variables"} 发 POST）
BODY_KINDS = ("json", "graphql")

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
        # 集合入口：保存当前请求 / 管理已存请求（图标按钮省地方）
        self.save_btn = QPushButton()
        self.save_btn.setIcon(icons.icon("save"))
        self.save_btn.setToolTip(self.tr("保存当前请求到集合"))
        self.save_btn.clicked.connect(self._save_to_collection)
        self.collection_btn = QPushButton()
        self.collection_btn.setIcon(icons.icon("collection"))
        self.collection_btn.setToolTip(self.tr("请求集合（加载 / 重命名 / 删除）"))
        self.collection_btn.clicked.connect(self._open_collections)
        row.addWidget(self.method_combo)
        row.addWidget(self.url_edit, stretch=1)
        row.addWidget(self.verify_cb)
        row.addWidget(self.save_btn)
        row.addWidget(self.collection_btn)
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

        # body 模式：JSON / GraphQL（GraphQL 时多一个 variables 编辑框）
        body_title_row = QHBoxLayout()
        body_title_row.addWidget(QLabel(self.tr("请求 Body（GET / HEAD 时忽略）：")))
        self.body_kind_combo = QComboBox()
        self.body_kind_combo.addItem(self.tr("普通 JSON"), "json")
        self.body_kind_combo.addItem("GraphQL", "graphql")
        self.body_kind_combo.setToolTip(
            self.tr("GraphQL 模式：上方编辑 query，下方编辑 variables(JSON)，\n"
            "发送时自动组装为 {\"query\", \"variables\"} 并以 POST 发出。")
        )
        self.body_kind_combo.currentIndexChanged.connect(
            self._on_body_kind_changed
        )
        body_title_row.addStretch(1)
        body_title_row.addWidget(self.body_kind_combo)
        req_layout.addLayout(body_title_row)
        self.body_edit = QPlainTextEdit()
        self.body_edit.setMaximumHeight(110)
        font = QFont("ui-monospace, SF Mono, Menlo, Consolas, monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.body_edit.setFont(font)
        self.body_edit.setPlaceholderText(self.tr('如 {"name": "张三"}，或表单 a=1&b=2'))
        req_layout.addWidget(self.body_edit)

        # GraphQL variables 编辑框（仅 GraphQL 模式可见）
        self.variables_label = QLabel(self.tr("GraphQL Variables（JSON）："))
        self.variables_edit = QPlainTextEdit()
        self.variables_edit.setMaximumHeight(80)
        self.variables_edit.setFont(font)
        self.variables_edit.setPlaceholderText(self.tr('如 {"id": 1}，可留空'))
        self.variables_label.setVisible(False)
        self.variables_edit.setVisible(False)
        req_layout.addWidget(self.variables_label)
        req_layout.addWidget(self.variables_edit)
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
        graphql: bool = False,
        variables: str = "",
    ) -> None:
        """从流量列表带入一个请求（见 main_window._send_request_to_api），
        或从请求集合加载（graphql/variables 一并恢复）。"""
        # GraphQL 固定 POST；普通模式方法可自选
        kind_idx = self.body_kind_combo.findData("graphql" if graphql else "json")
        self.body_kind_combo.setCurrentIndex(max(kind_idx, 0))
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
        self.variables_edit.setPlainText(variables or "")
        self.resp_label.setText(self.tr("已带入请求，点击「发送」（或 Ctrl+Return）"))
        self.resp_pane.clear()
        self._fill_resp_headers([])

    def set_body_text(self, text: str) -> None:
        """「在工具页中打开 body」路径：只灌请求 body。"""
        self.body_edit.setPlainText(text)

    def is_sending(self) -> bool:
        return self._sending

    # ------------------------------------------------------------ 集合

    def _save_to_collection(self) -> None:
        """把当前请求存进集合（先取名；URL 为空时用 URL 兜底命名）。"""
        url = self.url_edit.text().strip()
        graphql = self._current_body_kind() == "graphql"
        name, ok = QInputDialog.getText(
            self,
            self.tr("保存到请求集合"),
            self.tr("名称："),
            text=url or self.tr("未命名请求"),
        )
        if not ok:
            return
        headers = self._collect_headers()
        # headers 表是有序 dict 语义，存成 [[k, v], ...] 保序
        store.add_collection(
            name=name or url or self.tr("未命名请求"),
            method="POST" if graphql else (self.method_combo.currentData() or "GET"),
            url=url,
            headers=[[k, v] for k, v in headers.items()],
            body=self.body_edit.toPlainText(),
            graphql=graphql,
            variables=self.variables_edit.toPlainText() if graphql else "",
        )
        self.resp_label.setText(self.tr("已保存到请求集合"))

    def _collection_dialog(self) -> CollectionDialog:
        """取（必要时创建）请求集合对话框。

        真非模态 + 对象复用：① 页面可能被拖成独立浮窗，模态框会把整个应用
        锁死；② 每次重建会重新加载列表、丢掉滚动位置。
        """
        dlg = getattr(self, "_collection_dlg", None)
        if dlg is None:
            dlg = CollectionDialog(self, on_load=self._load_from_collection)
            dlg.setWindowModality(Qt.WindowModality.NonModal)
            dlg.setModal(False)
            self._collection_dlg = dlg
        return dlg

    def _open_collections(self) -> None:
        dlg = self._collection_dialog()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _load_from_collection(self, item: dict) -> None:
        headers = {}
        for pair in item.get("headers") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2 and pair[0]:
                headers[str(pair[0])] = str(pair[1])
        self.load_request(
            method=item.get("method", "GET"),
            url=item.get("url", ""),
            headers=headers,
            body=item.get("body", ""),
            graphql=bool(item.get("graphql")),
            variables=item.get("variables", ""),
        )

    # ------------------------------------------------------------ 发送

    def _current_body_kind(self) -> str:
        return self.body_kind_combo.currentData() or "json"

    def _on_body_kind_changed(self) -> None:
        is_gql = self._current_body_kind() == "graphql"
        self.variables_label.setVisible(is_gql)
        self.variables_edit.setVisible(is_gql)
        if is_gql:
            # GraphQL 只能是 POST；切走时不动方法（用户可能自选）
            idx = self.method_combo.findData("POST")
            if idx >= 0:
                self.method_combo.setCurrentIndex(idx)
            self.body_edit.setPlaceholderText(
                self.tr("GraphQL Query，如：query { user(id: 1) { name } }")
            )
        else:
            self.body_edit.setPlaceholderText(
                self.tr('如 {"name": "张三"}，或表单 a=1&b=2')
            )

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
        graphql = self._current_body_kind() == "graphql"
        method = "POST" if graphql else (self.method_combo.currentData() or "GET")
        headers = self._collect_headers()
        if graphql:
            body_text, err = self._build_graphql_body()
            if err:
                self.resp_label.setText(err)
                return
            # GraphQL 走 application/json（用户显式设了 Content-Type 则尊重）
            if not any(k.lower() == "content-type" for k in headers):
                headers["Content-Type"] = "application/json"
        else:
            body_text = self.body_edit.toPlainText()
        if len(body_text.encode("utf-8")) > MAX_BODY_INPUT:
            self.resp_label.setText(self.tr("请求 body 超过 50MB 上限"))
            return
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

    def _build_graphql_body(self) -> tuple[str, str]:
        """组装 GraphQL 请求体；返回 (body, 错误文案)——出错时 body 为空。"""
        query = self.body_edit.toPlainText().strip()
        if not query:
            return "", self.tr("请先填写 GraphQL Query")
        variables_text = self.variables_edit.toPlainText().strip()
        variables = {}
        if variables_text:
            try:
                variables = json.loads(variables_text)
            except ValueError as e:
                return "", self.tr("Variables 不是合法 JSON：{0}").format(e)
            if not isinstance(variables, dict):
                return "", self.tr("Variables 必须是 JSON 对象（{\"key\": value}）")
        return json.dumps({"query": query, "variables": variables},
                          ensure_ascii=False), ""

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
