"""断点命中时的编辑/放行对话框（Fiddler 的 Breakpoint 编辑器）。

代理把会话挂住后弹出来：改完点「继续」放行，点「中止」给客户端一个错误。
设计上刻意**非模态**——多个会话同时撞断点时要能一排摆着逐个处理，
同时保留引用避免被 GC（见 main_window 的 _breakpoint_dialogs）。

放行/中止通过构造参数注入回调（on_resume / on_kill），不直接依赖
ProxyService，方便单测里用假回调断言行为。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.ui import theme

#: 常用请求方法（断点里改方法用；保留自定义输入能力）
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


class BreakpointDialog(QDialog):
    """编辑被断点挂住的请求 / 响应，然后放行或中止。"""

    def __init__(self, flow, phase: str, on_resume=None, on_kill=None,
                 parent=None) -> None:
        super().__init__(parent)
        self.flow = flow
        self.phase = phase
        self._on_resume = on_resume
        self._on_kill = on_kill
        self._kill_done = False

        req = getattr(flow, "request", None)
        res = getattr(flow, "response", None)
        if phase == "request":
            title = self.tr("断点：请求发出前")
        else:
            title = self.tr("断点：响应返回前")
        url = getattr(req, "pretty_url", "") if req is not None else ""
        self.setWindowTitle(f"{title} — {url}")
        self.resize(760, 560)

        layout = QVBoxLayout(self)

        hint = QLabel(
            self.tr("会话已挂起：改完点「继续」放行，点「中止」让请求失败。"
                    "直接关闭窗口 = 原样放行。")
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.css('hint')};")
        layout.addWidget(hint)

        # ---- 首行：请求（方法 + URL）或响应（状态码 + reason）
        first = QHBoxLayout()
        if phase == "request":
            self.method_combo = QComboBox()
            self.method_combo.setEditable(True)
            for m in METHODS:
                self.method_combo.addItem(m)
            cur = (getattr(req, "method", "") or "GET").upper()
            self.method_combo.setCurrentText(cur)
            first.addWidget(self.method_combo)

            self.url_edit = QLineEdit(url)
            first.addWidget(self.url_edit, stretch=1)
            self.status_spin = None
        else:
            first.addWidget(QLabel(self.tr("状态码:")))
            self.status_spin = QSpinBox()
            self.status_spin.setRange(100, 599)
            self.status_spin.setValue(getattr(res, "status_code", 200) or 200)
            first.addWidget(self.status_spin)
            self.reason_edit = QLineEdit(getattr(res, "reason", "") or "")
            self.reason_edit.setPlaceholderText(self.tr("原因短语（可留空）"))
            first.addWidget(self.reason_edit, stretch=1)
            self.method_combo = None
            self.url_edit = None
        layout.addLayout(first)

        # ---- headers（可编辑）
        layout.addWidget(QLabel(self.tr("Header（可增删改）")))
        self.headers_table = QTableWidget(0, 2)
        self.headers_table.setHorizontalHeaderLabels(
            [self.tr("名称"), self.tr("值")]
        )
        self.headers_table.horizontalHeader().setStretchLastSection(True)
        self.headers_table.verticalHeader().setVisible(False)
        self.headers_table.setAlternatingRowColors(True)
        self.headers_table.setShowGrid(False)
        self._fill_headers(
            (req.headers if phase == "request" else getattr(res, "headers", {}))
            or {}
        )
        layout.addWidget(self.headers_table, stretch=1)

        hdr_row = QHBoxLayout()
        add_btn = QPushButton(self.tr("新增一行"))
        add_btn.clicked.connect(self._add_header_row)
        del_btn = QPushButton(self.tr("删除选中行"))
        del_btn.clicked.connect(self._delete_header_row)
        hdr_row.addWidget(add_btn)
        hdr_row.addWidget(del_btn)
        hdr_row.addStretch(1)
        layout.addLayout(hdr_row)

        # ---- body（可编辑）
        layout.addWidget(QLabel(self.tr("Body（可编辑）")))
        self.body_edit = QPlainTextEdit()
        self.body_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.body_edit.setPlainText(self._initial_body())
        layout.addWidget(self.body_edit, stretch=2)

        # ---- 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        kill_btn = QPushButton(self.tr("中止请求"))
        kill_btn.clicked.connect(self._do_kill)
        btn_row.addWidget(kill_btn)
        self.resume_btn = QPushButton(self.tr("继续放行"))
        self.resume_btn.setDefault(True)
        self.resume_btn.clicked.connect(self._do_resume)
        btn_row.addWidget(self.resume_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------ 初始化

    def _fill_headers(self, headers) -> None:
        try:
            items = list(headers.items())
        except AttributeError:
            items = []
        self.headers_table.setRowCount(len(items))
        for row, (k, v) in enumerate(items):
            self.headers_table.setItem(row, 0, QTableWidgetItem(str(k)))
            self.headers_table.setItem(row, 1, QTableWidgetItem(str(v)))

    def _initial_body(self) -> str:
        msg = (
            self.flow.request if self.phase == "request"
            else getattr(self.flow, "response", None)
        )
        if msg is None:
            return ""
        try:
            content = msg.get_content(strict=False)
        except Exception:
            content = None
        if not content:
            return ""
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            # 二进制就别让人手改了：展示十六进制前若干字节，编辑框留空
            return content[:512].hex(" ")

    # ------------------------------------------------------------ headers 增删

    def _add_header_row(self) -> None:
        row = self.headers_table.rowCount()
        self.headers_table.insertRow(row)
        self.headers_table.setItem(row, 0, QTableWidgetItem(""))
        self.headers_table.setItem(row, 1, QTableWidgetItem(""))

    def _delete_header_row(self) -> None:
        rows = {i.row() for i in self.headers_table.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            self.headers_table.removeRow(row)

    def _edited_headers(self) -> list[tuple[str, str]]:
        out = []
        for row in range(self.headers_table.rowCount()):
            name_item = self.headers_table.item(row, 0)
            value_item = self.headers_table.item(row, 1)
            name = (name_item.text() if name_item else "").strip()
            if not name:
                continue
            out.append((name, value_item.text() if value_item else ""))
        return out

    # ------------------------------------------------------------ 应用 / 放行

    def apply_edits(self) -> None:
        """把界面上的改动写回 flow（放行前调用）。"""
        msg = (
            self.flow.request if self.phase == "request"
            else getattr(self.flow, "response", None)
        )
        if msg is None:
            return

        if self.phase == "request" and self.url_edit is not None:
            url = self.url_edit.text().strip()
            if url:
                try:
                    msg.url = url
                except ValueError:
                    # URL 写坏了就保留原 URL（改动无效的代价远小于放行到错误地址）
                    pass
            if self.method_combo is not None:
                method = self.method_combo.currentText().strip().upper()
                if method:
                    msg.method = method
        elif self.status_spin is not None:
            msg.status_code = self.status_spin.value()
            reason = self.reason_edit.text().strip()
            msg.reason = reason

        headers = self._edited_headers()
        try:
            msg.headers.clear()
        except AttributeError:
            return
        for k, v in headers:
            msg.headers[k] = v

        body = self.body_edit.toPlainText()
        try:
            msg.text = body
        except Exception:
            # 二进制/编码异常时不改 body，至少 headers 的改动生效
            return
        # 改了 body 就得同步 Content-Length，否则对端会一直等（最常见的坑）
        if any(k.lower() == "content-length" for k, _ in headers):
            msg.headers["Content-Length"] = str(len(body.encode("utf-8")))

    def _do_resume(self) -> None:
        self.apply_edits()
        if self._on_resume is not None:
            self._on_resume(self.flow)
        self.accept()

    def _do_kill(self) -> None:
        # 先打标记：reject() 会触发 closeEvent，别让「关闭=放行」把它又放行一次
        self._kill_done = True
        if self._on_kill is not None:
            self._on_kill(self.flow)
        self.reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        """关闭 = 原样放行。

        断点挂着的会话必须有出路：用户随手关掉窗口不能把请求永久卡住，
        那比改错内容糟得多（客户端一直转圈，还查不出为什么）。
        """
        if self.result() == QDialog.DialogCode.Rejected and not self._killed():
            if self._on_resume is not None:
                self._on_resume(self.flow)
        super().closeEvent(event)

    def _killed(self) -> bool:
        return getattr(self, "_kill_done", False)
