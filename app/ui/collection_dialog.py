"""API 集合管理对话框：列出已保存请求，支持加载 / 重命名 / 删除。

数据全权走 app/api_collections.py（纯函数存储），本类只做 UI。
加载动作经 ``on_load(item)`` 回调抛给 api_panel——对话框不认识面板，
面板也不认识对话框内部控件，双向解耦。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app import api_collections as store
from app.ui import theme


class CollectionDialog(QDialog):
    """集合管理：加载到 API 调试页 / 重命名 / 删除。"""

    def __init__(self, parent=None, on_load=None):
        super().__init__(parent)
        self._on_load = on_load
        self.setWindowTitle(self.tr("请求集合"))
        self.setMinimumWidth(560)
        self.setMinimumHeight(380)
        self._build_ui()
        self.reload()

    # ---------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        hint = QLabel(
            self.tr("双击或点「加载」把请求带回 API 调试页；删除不可恢复。")
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list_widget = QListWidget(self)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.list_widget.itemDoubleClicked.connect(self._load_selected)
        layout.addWidget(self.list_widget, stretch=1)

        self.empty_label = QLabel(self.tr("还没有保存任何请求。\n在 API 调试页填好请求后点「保存到集合」即可。"))
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {theme.css('hint')};")
        layout.addWidget(self.empty_label)

        btn_row = QHBoxLayout()
        self.load_btn = QPushButton(self.tr("加载"))
        self.load_btn.setDefault(True)
        self.load_btn.clicked.connect(self._load_selected)
        self.rename_btn = QPushButton(self.tr("重命名"))
        self.rename_btn.clicked.connect(self._rename_selected)
        self.delete_btn = QPushButton(self.tr("删除"))
        self.delete_btn.clicked.connect(self._delete_selected)
        close_btn = QPushButton(self.tr("关闭"))
        close_btn.clicked.connect(self.reject)
        for b in (self.load_btn, self.rename_btn, self.delete_btn, close_btn):
            btn_row.addWidget(b)
        layout.addLayout(btn_row)
        self._sync_buttons()

    # ---------------------------------------------------------------- 数据

    def reload(self) -> None:
        """重新读盘并刷新列表（保存/删除/重命名后都走这里）。"""
        self.list_widget.clear()
        self._items = store.load_collections()
        for it in self._items:
            label = "{0}  {1}".format(it.get("method", ""),
                                      it.get("name") or self.tr("未命名请求"))
            url = it.get("url") or ""
            item = QListWidgetItem(label)
            item.setToolTip(url)
            item.setData(Qt.ItemDataRole.UserRole, it.get("id"))
            self.list_widget.addItem(item)
        has_any = bool(self._items)
        self.list_widget.setVisible(has_any)
        self.empty_label.setVisible(not has_any)
        self._sync_buttons()

    def _selected_item(self) -> dict | None:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def _sync_buttons(self) -> None:
        has_sel = self.list_widget.currentRow() >= 0 and bool(self._items)
        self.load_btn.setEnabled(has_sel)
        self.rename_btn.setEnabled(has_sel)
        self.delete_btn.setEnabled(has_sel)

    # ---------------------------------------------------------------- 动作

    def _load_selected(self) -> None:
        it = self._selected_item()
        if it is None:
            return
        if callable(self._on_load):
            self._on_load(it)
        self.accept()

    def _rename_selected(self) -> None:
        it = self._selected_item()
        if it is None:
            return
        text, ok = QInputDialog.getText(
            self,
            self.tr("重命名请求"),
            self.tr("新名称："),
            text=it.get("name", ""),
        )
        if ok and text.strip():
            store.rename_collection(it["id"], text.strip())
            self.reload()

    def _delete_selected(self) -> None:
        it = self._selected_item()
        if it is None:
            return
        ret = QMessageBox.question(
            self,
            self.tr("删除请求"),
            self.tr("确定删除「{0}」吗？此操作不可恢复。").format(it.get("name", "")),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            store.delete_collection(it["id"])
            self.reload()
