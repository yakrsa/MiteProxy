"""Mock 规则管理面板（DESIGN.md 3.3 / 3.4.3）。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from addons.importers import farx, jsscript
from app.rules import Rule, RuleStore
from app.ui.import_dialog import (
    SOURCE_LABELS,
    _action_summary,
    _match_summary,
)
from app.ui.rule_editor import RuleEditorDialog


class RulesPanel(QWidget):
    """规则列表 + CRUD + Fiddler 导入入口。"""

    import_requested = Signal()

    def __init__(self, store: RuleStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        toolbar = QHBoxLayout()
        self.add_btn = QPushButton("新增")
        self.edit_btn = QPushButton("编辑")
        self.delete_btn = QPushButton("删除")
        self.import_btn = QPushButton("导入 Fiddler 规则")
        self.up_btn = QPushButton("上移")
        self.down_btn = QPushButton("下移")
        for b in (
            self.add_btn,
            self.edit_btn,
            self.delete_btn,
            self.import_btn,
            self.up_btn,
            self.down_btn,
        ):
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["启用", "名称", "匹配", "动作", "来源", "命中"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.add_btn.clicked.connect(self._on_add)
        self.edit_btn.clicked.connect(self._on_edit)
        self.delete_btn.clicked.connect(self._on_delete)
        self.import_btn.clicked.connect(self._on_import)
        self.up_btn.clicked.connect(lambda: self._on_move(-1))
        self.down_btn.clicked.connect(lambda: self._on_move(1))
        self.table.cellDoubleClicked.connect(lambda r, c: self._on_edit())

    # ------------------------------------------------------------ 刷新

    def refresh(self) -> None:
        rules = self.store.all()
        self.table.setRowCount(len(rules))
        for i, rule in enumerate(rules):
            enabled_item = QTableWidgetItem("✔" if rule.enabled else "—")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            name = rule.name + (" ⚠" if rule.error else "")
            self.table.setItem(i, 0, enabled_item)
            self.table.setItem(i, 1, QTableWidgetItem(name))
            self.table.setItem(i, 2, QTableWidgetItem(_match_summary(rule)))
            self.table.setItem(i, 3, QTableWidgetItem(_action_summary(rule)))
            self.table.setItem(
                i, 4, QTableWidgetItem(SOURCE_LABELS.get(rule.source, rule.source))
            )
            self._fill_hits(i, rule)
            if rule.error:
                self.table.item(i, 1).setToolTip(rule.error)

    def _fill_hits(self, row: int, rule) -> None:
        """命中列：0 次显示「—」（没干活过），有次数显示数字 + 最近命中时间提示。"""
        item = QTableWidgetItem("—" if not rule.hits else str(rule.hits))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if rule.hits:
            when = datetime.fromtimestamp(rule.last_hit).strftime("%H:%M:%S")
            item.setToolTip(f"最近命中 {when}")
        self.table.setItem(row, 5, item)

    def update_hit(self, rule_id: str) -> None:
        """代理线程命中后的实时刷新（经信号桥到主线程）。

        只改一格、不动选中与滚动——命中可能每秒几十次，整表重建会把人逼疯。
        """
        for i, rule in enumerate(self.store.all()):
            if rule.id == rule_id:
                self._fill_hits(i, rule)
                return

    def update_rule_error(self, rule_id: str, message) -> None:
        """代理线程报规则运行时错误后的实时刷新（mock 失败/文件缺失/重定向非法）。

        错误标记在名称列（⚠ + tooltip），不整表重建。
        """
        for i, rule in enumerate(self.store.all()):
            if rule.id != rule_id:
                continue
            item = self.table.item(i, 1)
            if item is None:
                return
            if message:
                item.setText(f"{rule.name} ⚠")
                item.setToolTip(message)
            else:
                item.setText(rule.name)
                item.setToolTip("")
            return

    def _current_rule(self) -> Rule | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        rules = self.store.all()
        if row < len(rules):
            return rules[row]
        return None

    # ------------------------------------------------------------ 事件

    def _on_add(self) -> None:
        dialog = RuleEditorDialog(self.store, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_edit(self) -> None:
        rule = self._current_rule()
        if rule is None:
            QMessageBox.information(self, "提示", "请先选择一条规则")
            return
        dialog = RuleEditorDialog(self.store, rule, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_delete(self) -> None:
        rule = self._current_rule()
        if rule is None:
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定删除规则「{rule.name}」？"
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.delete(rule.id)
            self.refresh()

    def _on_move(self, delta: int) -> None:
        row = self.table.currentRow()
        rules = self.store.all()
        target = row + delta
        if row < 0 or not (0 <= target < len(rules)):
            return
        ids = [r.id for r in rules]
        ids[row], ids[target] = ids[target], ids[row]
        self.store.reorder(ids)
        self.refresh()
        self.table.selectRow(target)

    # ------------------------------------------------------------ Fiddler 导入

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Fiddler 规则文件",
            "",
            "Fiddler 规则 (*.farx *.js);;FARX 规则包 (*.farx);;CustomRules.js (*.js);;所有文件 (*)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".farx"):
                result = farx.parse_file(path)
            else:
                result = jsscript.parse_file(path)
        except (ValueError, OSError) as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return

        if result.ok_count == 0:
            reasons = "\n".join(f"• {n}：{r}" for n, r in result.skipped[:10])
            QMessageBox.information(
                self,
                "无可导入规则",
                f"没有解析出可导入的规则。\n\n{reasons or '文件为空或格式不符'}",
            )
            return

        from app.ui.import_dialog import ImportPreviewDialog

        dialog = ImportPreviewDialog(
            result.rules, result.skipped, path.rsplit("/", 1)[-1], parent=self
        )
        if dialog.exec():
            selected = dialog.selected_rules()
            if selected:
                count, _ = self.store.merge(selected)
                self.refresh()
                QMessageBox.information(
                    self, "导入完成", f"成功导入 {count} 条规则"
                )
            self.import_requested.emit()  # 只在真正走完导入流程后通知
