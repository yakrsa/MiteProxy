"""JSON 比对页：左右两段 JSON → 键级差异表（复用 app/jsondiff.py）。

和「重放并对比」共用同一个 diff 引擎，但入口不同：那边比重放前后的
响应，这边比任意两段 JSON（线上返回 vs 本地期望、两个接口的字段…）。

设计沿用 JSON 工具页的规矩：
- **失败不吞内容**：某一侧非法时报出定位（行列 + `^` 指针），输入框内容不动；
- **实时比对带防抖**（220ms），大输入不卡；
- 差异表行数有上限，超了只显示前几百条并说明。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.jsondiff import diff_json, format_diff_report, render_value
from app.jsonutil import count_nodes, parse_json

#: 差异表最多显示多少行（diff 本身仍会算完，只是不全部渲染）
TABLE_ROW_LIMIT = 500

KIND_LABELS = {"added": "新增", "removed": "删除", "changed": "修改"}
KIND_COLORS = {"added": "#2f7d32", "removed": "#c0392b", "changed": "#bf8700"}

HINT_COLOR = "#6b6b6b"
ERROR_COLOR = "#e5534b"
OK_COLOR = "#2f7d32"
DIFF_COLOR = "#bf8700"


def _mono_font() -> QFont:
    font = QFont("ui-monospace, SF Mono, Menlo, Consolas, monospace")
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


class JsonComparePanel(QWidget):
    """左右两个 JSON 输入 + 键级差异表。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = _mono_font()
        self._report_text = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addLayout(self._build_toolbar())
        root.addWidget(self._build_inputs(), stretch=2)
        root.addWidget(self._build_result(), stretch=3)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self._compare)
        self.left_edit.textChanged.connect(self._schedule)
        self.right_edit.textChanged.connect(self._schedule)

    # ------------------------------------------------------------ 构建

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        swap_btn = QPushButton("交换左右")
        swap_btn.setToolTip("把两边内容对调（比对结果方向随之反转）")
        swap_btn.clicked.connect(self._swap)
        row.addWidget(swap_btn)

        row.addStretch(1)

        self.copy_btn = QPushButton("复制差异")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_report)
        row.addWidget(self.copy_btn)

        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._on_clear)
        row.addWidget(clear_btn)
        return row

    def _build_inputs(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        for name, attr in (("原 JSON", "left_edit"), ("新 JSON", "right_edit")):
            box = QGroupBox(name)
            layout = QVBoxLayout(box)
            layout.setContentsMargins(4, 4, 4, 4)
            edit = QPlainTextEdit()
            edit.setFont(self._font)
            edit.setPlaceholderText("把 JSON 贴进来…")
            layout.addWidget(edit)
            setattr(self, attr, edit)
            splitter.addWidget(box)
        splitter.setSizes([520, 520])
        return splitter

    def _build_result(self) -> QWidget:
        box = QGroupBox("差异")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(4, 4, 4, 4)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["路径", "类型", "旧值", "新值"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.status_label = QLabel("两边都贴上 JSON 后自动比对")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.status_label)
        return box

    # ------------------------------------------------------------ 状态栏

    def _set_status(self, text: str, color: str = HINT_COLOR) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

    # ------------------------------------------------------------ 动作

    def _schedule(self) -> None:
        self._timer.start()

    def _swap(self) -> None:
        left, right = self.left_edit.toPlainText(), self.right_edit.toPlainText()
        # 先断开再恢复：避免交换过程触发两次比对（内容没变，结果也不会变）
        self.left_edit.blockSignals(True)
        self.right_edit.blockSignals(True)
        self.left_edit.setPlainText(right)
        self.right_edit.setPlainText(left)
        self.left_edit.blockSignals(False)
        self.right_edit.blockSignals(False)
        self._compare()

    def _on_clear(self) -> None:
        self.left_edit.blockSignals(True)
        self.right_edit.blockSignals(True)
        self.left_edit.clear()
        self.right_edit.clear()
        self.left_edit.blockSignals(False)
        self.right_edit.blockSignals(False)
        self.table.setRowCount(0)
        self._report_text = ""
        self.copy_btn.setEnabled(False)
        self._set_status("两边都贴上 JSON 后自动比对")

    def _copy_report(self) -> None:
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._report_text)

    # ------------------------------------------------------------ 比对

    def _compare(self) -> None:
        left_text = self.left_edit.toPlainText()
        right_text = self.right_edit.toPlainText()
        self.table.setRowCount(0)
        self._report_text = ""
        self.copy_btn.setEnabled(False)

        if not left_text.strip() and not right_text.strip():
            self._set_status("两边都贴上 JSON 后自动比对")
            return

        # 逐侧解析：非法的那侧给出定位，内容不动（失败不吞内容）
        results = []
        for side, text in (("原 JSON", left_text), ("新 JSON", right_text)):
            if not text.strip():
                self._set_status(f"「{side}」还是空的", ERROR_COLOR)
                return
            result = parse_json(text)
            if not result.ok:
                self._set_status(
                    f"「{side}」不合法：{result.error.report()}", ERROR_COLOR
                )
                return
            results.append(result)
        left, right = results

        result = diff_json(left.value, right.value)
        nodes_text = (
            f"左 {count_nodes(left.value)} 节点 · 右 {count_nodes(right.value)} 节点"
        )

        if result.identical:
            self._report_text = "两个 JSON 完全一致"
            self._set_status(f"{nodes_text} · 完全一致", OK_COLOR)
            return

        shown = result.entries[:TABLE_ROW_LIMIT]
        self.table.setRowCount(len(shown))
        for row, entry in enumerate(shown):
            self.table.setItem(row, 0, QTableWidgetItem(entry.path))
            kind_item = QTableWidgetItem(KIND_LABELS.get(entry.kind, entry.kind))
            kind_item.setForeground(QColor(KIND_COLORS.get(entry.kind, "#000000")))
            self.table.setItem(row, 1, kind_item)
            self.table.setItem(row, 2, QTableWidgetItem(render_value(entry.old)))
            self.table.setItem(row, 3, QTableWidgetItem(render_value(entry.new)))

        self._report_text = format_diff_report(result)
        more = (
            f"（差异表仅显示前 {TABLE_ROW_LIMIT} 条）"
            if result.count > TABLE_ROW_LIMIT
            else ""
        )
        trunc = "（差异过多，结构化对比已提前停止）" if result.truncated else ""
        self._set_status(
            f"{nodes_text} · 共 {result.count} 处差异{more}{trunc}", DIFF_COLOR
        )
        self.copy_btn.setEnabled(True)

    # ------------------------------------------------------------ 对外

    def set_texts(self, left: str, right: str = "") -> None:
        """外部灌入（如「在工具页中打开 body」送到比对页）。"""
        self.left_edit.blockSignals(True)
        self.right_edit.blockSignals(True)
        self.left_edit.setPlainText(left)
        self.right_edit.setPlainText(right)
        self.left_edit.blockSignals(False)
        self.right_edit.blockSignals(False)
        self._compare()

    @property
    def report_text(self) -> str:
        return self._report_text
