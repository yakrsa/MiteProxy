"""编辑并重放对话框（对齐 Fiddler Edit and Replay，DESIGN.md 3.6）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


class ReplayEditDialog(QDialog):
    """预填原始请求，用户改 method/url/headers/body 后重放。

    `compare=True` 时是「重放并对比」模式：标题与确认按钮换文案，
    其余编辑能力完全一致（先改请求，再重放，响应到达后弹对比框）。
    """

    def __init__(self, request, parent=None, compare: bool = False):
        super().__init__(parent)
        self.setWindowTitle("重放并对比" if compare else "编辑并重放")
        self.setMinimumSize(640, 560)
        self._compare = compare
        self._build_ui()
        self._load_request(request)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.method_combo = QComboBox()
        self.method_combo.addItems(METHODS)
        self.method_combo.setEditable(True)
        form.addRow("方法:", self.method_combo)

        self.url_edit = QPlainTextEdit()
        self.url_edit.setMaximumHeight(60)
        form.addRow("URL:", self.url_edit)

        # headers 表格
        headers_row = QWidget()
        headers_layout = QVBoxLayout(headers_row)
        headers_layout.setContentsMargins(0, 0, 0, 0)
        self.headers_table = QTableWidget(0, 2)
        self.headers_table.setHorizontalHeaderLabels(["Header", "Value"])
        self.headers_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.headers_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        headers_layout.addWidget(self.headers_table)
        hbtn = QHBoxLayout()
        add_h = QPushButton("添加")
        add_h.clicked.connect(
            lambda: self.headers_table.insertRow(self.headers_table.rowCount())
        )
        del_h = QPushButton("删除选中")
        del_h.clicked.connect(self._delete_row)
        hbtn.addWidget(add_h)
        hbtn.addWidget(del_h)
        hbtn.addStretch(1)
        headers_layout.addLayout(hbtn)
        form.addRow("Headers:", headers_row)

        self.body_edit = QPlainTextEdit()
        form.addRow("Body:", self.body_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "重放并对比" if self._compare else "重放"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_request(self, request) -> None:
        self.method_combo.setCurrentText(request.method or "GET")
        self.url_edit.setPlainText(request.pretty_url or "")
        self.headers_table.setRowCount(0)
        try:
            items = list(request.headers.items(multi=True))
        except TypeError:
            items = list(request.headers.items())
        for k, v in items:
            row = self.headers_table.rowCount()
            self.headers_table.insertRow(row)
            self.headers_table.setItem(row, 0, QTableWidgetItem(str(k)))
            self.headers_table.setItem(row, 1, QTableWidgetItem(str(v)))
        try:
            content = request.get_content(strict=False) or b""
        except Exception:
            content = b""
        from app.textutil import decode_body

        text = decode_body(content)
        self.body_edit.setPlainText(text if text is not None else "")

    def _delete_row(self) -> None:
        for idx in sorted(
            {i.row() for i in self.headers_table.selectedIndexes()}, reverse=True
        ):
            self.headers_table.removeRow(idx)

    # ------------------------------------------------------------ 结果

    def result(self) -> dict:
        headers = {}
        for row in range(self.headers_table.rowCount()):
            k_item = self.headers_table.item(row, 0)
            if k_item is None or not k_item.text().strip():
                continue
            v_item = self.headers_table.item(row, 1)
            headers[k_item.text().strip()] = v_item.text() if v_item else ""
        return {
            "method": self.method_combo.currentText().strip(),
            "url": self.url_edit.toPlainText().strip(),
            "headers": headers,
            "body": self.body_edit.toPlainText(),
        }
