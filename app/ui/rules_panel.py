"""Mock 规则管理面板（DESIGN.md 3.3 / 3.4.3）。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QMenu,
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
from app.ui import theme


class RuleTable(QTableWidget):
    """规则表：支持整行拖拽调整顺序（拖到目标行上半=插到其前，下半=插到其后）。

    QTableWidget 自带的 InternalMove 是按单元格移动，行会乱；这里覆盖
    dropEvent 自己算插入位置，只发信号，重排由 RulesPanel 走 store.reorder。
    """

    row_dropped = Signal(int, int)  # (源行, 目标插入位置-原始列表语义)

    def __init__(self, parent=None):
        super().__init__(0, 6, parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def dropEvent(self, event) -> None:
        if event.source() is not self:
            event.ignore()
            return
        src = self.currentRow()
        if src < 0:
            event.ignore()
            return
        pos = event.position().toPoint()
        idx = self.indexAt(pos)
        if not idx.isValid():
            dst = self.rowCount()  # 拖到表尾
        else:
            dst = idx.row()
            rect = self.visualItemRect(self.item(idx.row(), 0))
            if pos.y() > rect.center().y():
                dst += 1  # 落在下半行 → 插到目标行之后
        event.accept()
        self.row_dropped.emit(src, dst)


class RulesPanel(QWidget):
    """规则列表 + CRUD + Fiddler 导入入口。"""

    import_requested = Signal()

    def __init__(self, store: RuleStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._display_ids: list[str] = []   # 表格行 → 规则 id（过滤后的视图顺序）
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
        self.only_enabled_cb = QCheckBox("只显示启用")
        self.only_enabled_cb.setToolTip(
            "勾选后列表只显示启用中的规则；停用规则仍在存储中，取消勾选即可看到。"
        )
        for b in (
            self.add_btn,
            self.edit_btn,
            self.delete_btn,
            self.import_btn,
            self.up_btn,
            self.down_btn,
        ):
            toolbar.addWidget(b)
        toolbar.addSpacing(12)
        toolbar.addWidget(self.only_enabled_cb)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.table = RuleTable(self)
        self.table.setHorizontalHeaderLabels(
            ["名称", "启用", "匹配", "动作", "来源", "命中"]
        )
        # 质感：斑马纹 + 无网格线 + 紧凑行高（全局 QSS 管表头/边框）
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.table)

        self.add_btn.clicked.connect(self._on_add)
        self.edit_btn.clicked.connect(self._on_edit)
        self.delete_btn.clicked.connect(self._on_delete)
        self.import_btn.clicked.connect(self._on_import)
        self.up_btn.clicked.connect(lambda: self._on_move(-1))
        self.down_btn.clicked.connect(lambda: self._on_move(1))
        self.table.row_dropped.connect(self._on_row_dropped)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.only_enabled_cb.toggled.connect(self._on_filter_toggled)
        self.table.cellDoubleClicked.connect(lambda r, c: self._on_edit())

    # ------------------------------------------------------------ 刷新

    def _visible_rules(self) -> list[Rule]:
        """当前应显示的规则（「只显示启用」过滤后的视图顺序）。"""
        rules = self.store.all()
        if self.only_enabled_cb.isChecked():
            return [r for r in rules if r.enabled]
        return rules

    def refresh(self) -> None:
        visible = self._visible_rules()
        self._display_ids = [r.id for r in visible]
        self.table.setRowCount(len(visible))
        for i, rule in enumerate(visible):
            enabled_item = QTableWidgetItem("✔" if rule.enabled else "—")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            name = rule.name + (" ⚠" if rule.error else "")
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, enabled_item)
            self.table.setItem(i, 2, QTableWidgetItem(_match_summary(rule)))
            self.table.setItem(i, 3, QTableWidgetItem(_action_summary(rule)))
            self.table.setItem(
                i, 4, QTableWidgetItem(SOURCE_LABELS.get(rule.source, rule.source))
            )
            self._fill_hits(i, rule)
            if rule.error:
                self.table.item(i, 0).setToolTip(rule.error)

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
        try:
            row = self._display_ids.index(rule_id)
        except (ValueError, AttributeError):
            return
        rule = self.store.get(rule_id)
        if rule is not None:
            self._fill_hits(row, rule)

    def update_rule_error(self, rule_id: str, message) -> None:
        """代理线程报规则运行时错误后的实时刷新（mock 失败/文件缺失/重定向非法）。

        错误标记在名称列（⚠ + tooltip），不整表重建。
        """
        try:
            row = self._display_ids.index(rule_id)
        except (ValueError, AttributeError):
            return
        rule = self.store.get(rule_id)
        item = self.table.item(row, 0)
        if rule is None or item is None:
            return
        if message:
            item.setText(f"{rule.name} ⚠")
            item.setToolTip(message)
        else:
            item.setText(rule.name)
            item.setToolTip("")

    def _current_rule(self) -> Rule | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.store.get(self._display_ids[row])

    # ------------------------------------------------------------ 右键菜单

    def _show_context_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        menu = self._build_context_menu(row)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _build_context_menu(self, row: int) -> QMenu:
        """构建右键菜单：选中行 → 规则操作；空白处 → 新增/导入。"""
        menu = QMenu(self)
        visible = self._visible_rules()
        if 0 <= row < len(visible):
            self.table.selectRow(row)
            rule = visible[row]
            menu.addAction("编辑", self._on_edit)
            menu.addAction(
                "停用" if rule.enabled else "启用",
                lambda: self._toggle_enable(rule.id),
            )
            menu.addSeparator()
            act_up = menu.addAction("上移", lambda: self._on_move(-1))
            act_down = menu.addAction("下移", lambda: self._on_move(1))
            act_up.setEnabled(row > 0)
            act_down.setEnabled(row < len(visible) - 1)
            menu.addSeparator()
            menu.addAction("删除", self._on_delete)
        else:
            menu.addAction("新增", self._on_add)
            menu.addAction("导入 Fiddler 规则", self._on_import)
        return menu

    def _toggle_enable(self, rule_id: str) -> None:
        rule = self.store.get(rule_id)
        if rule is None:
            return
        if rule.enabled:
            self._warn_duplicate_matches(rule)
        self.store.update(rule_id, enabled=not rule.enabled)
        self.refresh()

    @staticmethod
    def _same_match(a, b) -> bool:
        """两条规则的匹配条件是否完全一样（类型 + 值 + 方法）。"""
        return (
            a.match.type == b.match.type
            and a.match.value == b.match.value
            and a.match.method == b.match.method
        )

    def _warn_duplicate_matches(self, rule) -> None:
        """停用规则时，若有相同匹配条件的启用规则仍会命中，明确告知。

        「先声明先匹配」下常见困惑：导入了重叠的 Fiddler 规则，停用
        其中一条后请求仍被另一条 mock——看起来像"停用不生效"。
        """
        dupes = [
            r for r in self.store.all()
            if r.enabled and r.id != rule.id and self._same_match(r, rule)
        ]
        if not dupes:
            return
        names = "、".join(d.name for d in dupes[:3])
        more = f" 等 {len(dupes)} 条" if len(dupes) > 3 else ""
        QMessageBox.information(
            self,
            "注意：仍有规则会命中",
            f"停用「{rule.name}」后，相同匹配的启用规则仍会命中同样请求：\n"
            f"{names}{more}\n\n如需完全放行，请一并停用这些规则。",
        )

    def _on_filter_toggled(self) -> None:
        """切换「只显示启用」：重建视图，尽量保住当前选中的规则。"""
        current = self._current_rule()
        self.refresh()
        if current is not None and current.id in self._display_ids:
            self.table.selectRow(self._display_ids.index(current.id))

    def _apply_display_order(self, new_display_ids: list[str]) -> None:
        """把显示子序列的新顺序映射回全量存储顺序并落盘。

        被过滤隐藏的规则保持原相对位置插回，不会因为只操作可见行
        就被挤到列表末尾。
        """
        display_set = set(new_display_ids)
        remaining = iter(new_display_ids)
        full = []
        for r in self.store.all():
            full.append(next(remaining) if r.id in display_set else r.id)
        self.store.reorder(full)

    def _on_move(self, delta: int) -> None:
        row = self.table.currentRow()
        ids = self._display_ids
        target = row + delta
        if row < 0 or not (0 <= target < len(ids)):
            return
        ids[row], ids[target] = ids[target], ids[row]
        self._apply_display_order(ids)
        self.refresh()
        self.table.selectRow(target)

    def _on_row_dropped(self, src: int, dst: int) -> None:
        """拖拽落点 → 重排（dst 为拖放前的列表索引语义）。"""
        ids = list(self._display_ids)
        if not (0 <= src < len(ids)):
            return
        insert_at = dst - 1 if dst > src else dst
        if insert_at == src or not (0 <= insert_at <= len(ids) - 1):
            return
        moved = ids.pop(src)
        ids.insert(insert_at, moved)
        self._apply_display_order(ids)
        self.refresh()
        self.table.selectRow(insert_at)

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
