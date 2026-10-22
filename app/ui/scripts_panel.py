"""用户脚本（插件）管理页（路线图 #10）：脚本的增删改 / 启停 / 状态。

布局：上面一张表（名称 / 启用 / 大小 / 修改时间 / 状态），下面一排按钮，
再往下是安全说明与钩子文档。刻意不做语法高亮编辑器——代码编辑用用户
顺手的编辑器（「打开目录」一键过去），这里只管管理与启停。

线程与生命周期：加载在代理启动 / 热替换时发生（app/scripts.py），
本页只做文件管理与启用态；任何变更发 ``scripts_changed``，由主窗口
决定是热替换还是等下次启动。
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, Qt, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.scripts import SCRIPT_TEMPLATE, ScriptsManager, valid_name
from app.ui import dialogs
from app.ui import theme

log = logging.getLogger(__name__)

#: 页面级说明文案（NOOP 打标，运行时 translate）
PANEL_WARNING = QT_TRANSLATE_NOOP(
    "ScriptsPanel",
    "脚本在本进程内运行，与 MiteProxy 同等权限：能读写抓包内容、改动流量、"
    "访问文件。只添加可信来源的脚本。单个脚本报错不会影响其他脚本与代理"
    "（错误记入「日志」页）。",
)
PANEL_HOOKS = QT_TRANSLATE_NOOP(
    "ScriptsPanel",
    "钩子：request / response / requestheaders / responseheaders / error / "
    "websocket_message / websocket_end。写成模块级函数，或一个 Addon 类；"
    "第一参数叫 ctx 的钩子会收到 {{\"script\": 脚本名}}。",
)

COL_NAME, COL_ENABLED, COL_SIZE, COL_MODIFIED, COL_STATUS = 0, 1, 2, 3, 4


def _format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    return f"{n / 1024:.1f} KB"


class ScriptEditDialog(QDialog):
    """新建 / 编辑脚本：名称 + 代码。保存前做语法检查（见 manager）。"""

    def __init__(self, manager: ScriptsManager, name: str = "",
                 content: str = "", parent=None):
        super().__init__(parent)
        self.manager = manager
        self._original_name = name
        self.setWindowTitle(self.tr("编辑脚本") if name else self.tr("新建脚本"))
        self.resize(760, 560)
        self._saved_name = ""
        self._build_ui(name, content)

    def _build_ui(self, name: str, content: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("文件名:")))
        self.name_edit = QLineEdit()
        self.name_edit.setText(name)
        self.name_edit.setPlaceholderText(self.tr("my_script.py"))
        row.addWidget(self.name_edit, stretch=1)
        layout.addLayout(row)

        layout.addWidget(QLabel(self.tr("代码:")))
        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlainText(content)
        font = self.code_edit.font()
        font.setStyleHint(font.StyleHint.Monospace)
        font.setFamily("ui-monospace, SF Mono, Menlo, Consolas, monospace")
        self.code_edit.setFont(font)
        self.code_edit.setTabStopDistance(28)
        layout.addWidget(self.code_edit, stretch=1)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {theme.css('error')};")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        save_btn = QPushButton(self.tr("保存"))
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton(self.tr("取消"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self._fail(self.tr("文件名不能为空"))
            return
        if not name.endswith(".py"):
            name += ".py"
        if not valid_name(name):
            self._fail(self.tr(
                "文件名只能包含字母、数字、点、下划线、连字符，且必须以 .py 结尾"))
            return
        err = self.manager.write_script(name, self.code_edit.toPlainText())
        if err:
            # 语法错误在保存前就被拦下：错误直接显示在对话框里，不落盘
            self._fail(self.tr("无法保存：{0}").format(err))
            return
        self._saved_name = name
        self.accept()

    def _fail(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()

    @property
    def saved_name(self) -> str:
        return self._saved_name


class ScriptsPanel(QWidget):
    """脚本管理页。启用态字典由主窗口落进 settings.scripts。"""

    scripts_changed = Signal()

    def __init__(self, manager: ScriptsManager, enabled: dict | None = None,
                 parent=None):
        super().__init__(parent)
        self.manager = manager
        #: {脚本名: 是否启用}。缺省视为启用（文件在目录里且没被显式关过）
        self._enabled: dict[str, bool] = dict(enabled or {})
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            self.tr("名称"), self.tr("启用"), self.tr("大小"),
            self.tr("修改时间"), self.tr("状态"),
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        for col in (COL_ENABLED, COL_SIZE, COL_MODIFIED, COL_STATUS):
            header.setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout()
        self.new_btn = QPushButton(self.tr("新建脚本"))
        self.new_btn.clicked.connect(self._on_new)
        self.edit_btn = QPushButton(self.tr("编辑"))
        self.edit_btn.clicked.connect(self._on_edit)
        self.delete_btn = QPushButton(self.tr("删除"))
        self.delete_btn.clicked.connect(self._on_delete)
        self.refresh_btn = QPushButton(self.tr("刷新"))
        self.refresh_btn.clicked.connect(self.refresh)
        self.open_dir_btn = QPushButton(self.tr("打开目录"))
        self.open_dir_btn.setToolTip(
            self.tr("在文件管理器里打开脚本目录（用顺手的编辑器改代码）")
        )
        self.open_dir_btn.clicked.connect(self._on_open_dir)
        for btn in (self.new_btn, self.edit_btn, self.delete_btn,
                    self.refresh_btn, self.open_dir_btn):
            btn_row.addWidget(btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        warn = QLabel(QCoreApplication.translate("ScriptsPanel", PANEL_WARNING))
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color: {theme.css('warn')};")
        layout.addWidget(warn)

        hooks = QLabel(QCoreApplication.translate("ScriptsPanel", PANEL_HOOKS))
        hooks.setWordWrap(True)
        hooks.setStyleSheet(f"color: {theme.css('hint')};")
        layout.addWidget(hooks)

        self._update_buttons()

    # ------------------------------------------------------------ 数据

    def enabled_map(self) -> dict:
        return dict(self._enabled)

    def refresh(self) -> None:
        """重新扫描目录并重绘（加载错误一并显示）。"""
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            infos = self.manager.list_scripts()
            self.table.setRowCount(len(infos))
            for row, info in enumerate(infos):
                enabled = self._enabled.get(info.name, True)

                name_item = QTableWidgetItem(info.name)
                self.table.setItem(row, COL_NAME, name_item)

                check = QTableWidgetItem()
                check.setFlags(
                    Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                )
                # PySide6 的 checkState 值是原始 int：一律用 .value 比较
                check.setCheckState(
                    Qt.CheckState.Checked if enabled
                    else Qt.CheckState.Unchecked
                )
                self.table.setItem(row, COL_ENABLED, check)

                self.table.setItem(row, COL_SIZE,
                                   QTableWidgetItem(_format_size(info.size)))
                self.table.setItem(row, COL_MODIFIED,
                                   QTableWidgetItem(info.modified))
                if info.error:
                    status = self.tr("加载失败：{0}").format(info.error)
                elif enabled:
                    status = self.tr("已启用")
                else:
                    status = self.tr("已停用（不加载）")
                status_item = QTableWidgetItem(status)
                if info.error:
                    status_item.setForeground(QBrush(QColor(theme.color("error"))))
                self.table.setItem(row, COL_STATUS, status_item)
        finally:
            self.table.blockSignals(False)
        self._update_buttons()

    def _selected_name(self) -> str:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return ""
        item = self.table.item(rows[0].row(), COL_NAME)
        return item.text() if item else ""

    def _update_buttons(self) -> None:
        has_selection = bool(self._selected_name())
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    # ------------------------------------------------------------ 交互

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """勾选/取消「启用」列：更新启用态并通知主窗口。"""
        if item.column() != COL_ENABLED:
            return
        row = item.row()
        name_item = self.table.item(row, COL_NAME)
        if name_item is None:
            return
        name = name_item.text()
        # checkState 是原始 int：Qt.CheckState.Checked == 2，必须取 .value
        enabled = item.checkState().value == Qt.CheckState.Checked.value
        if self._enabled.get(name, True) == enabled:
            return
        self._enabled[name] = enabled
        # 状态列文案跟着变
        status_item = self.table.item(row, COL_STATUS)
        if status_item is not None:
            if enabled:
                status_item.setText(self.tr("已启用"))
                status_item.setForeground(QBrush())
            else:
                status_item.setText(self.tr("已停用（不加载）"))
        self.scripts_changed.emit()

    def _on_new(self) -> None:
        dialog = ScriptEditDialog(self.manager, content=SCRIPT_TEMPLATE,
                                  parent=self)
        if dialog.exec():
            name = dialog.saved_name
            self._enabled.setdefault(name, True)
            self.refresh()
            self.scripts_changed.emit()

    def _on_edit(self) -> None:
        name = self._selected_name()
        content = self.manager.read_script(name)
        if content is None:
            dialogs.information(self, self.tr("提示"),
                                self.tr("读不到脚本内容：{0}").format(name))
            return
        dialog = ScriptEditDialog(self.manager, name=name, content=content,
                                  parent=self)
        if dialog.exec():
            self.refresh()
            self.scripts_changed.emit()

    def _on_delete(self) -> None:
        name = self._selected_name()
        if not name:
            return
        # dialogs.question 返回的是 StandardButton，不是 bool
        clicked = dialogs.question(
            self,
            self.tr("删除脚本"),
            self.tr('确定删除脚本「{0}」？删除后不可恢复。').format(name),
        )
        if clicked != QMessageBox.StandardButton.Yes:
            return
        if self.manager.delete_script(name):
            self._enabled.pop(name, None)
            self.refresh()
            self.scripts_changed.emit()

    def _on_open_dir(self) -> None:
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.manager.scripts_dir))
        )
