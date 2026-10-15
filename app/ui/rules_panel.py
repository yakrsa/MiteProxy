"""Mock 规则管理面板（DESIGN.md 3.3 / 3.4.3）。"""

from __future__ import annotations

import json
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush
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
        # 列：选 / 序号 / 名称 / 启用 / 匹配 / 动作 / 来源 / 命中 / 创建时间（v1.15+）
        super().__init__(0, 9, parent)
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
        self._checked_ids: set[str] = set()  # 勾选的规则 id（批量操作目标）
        self._loading = False                # refresh 重建时屏蔽 itemChanged
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
        self.export_btn = QPushButton("导出规则")
        self.import_native_btn = QPushButton("导入规则")
        self.batch_enable_btn = QPushButton("启用")
        self.batch_disable_btn = QPushButton("停用")
        self.batch_delete_btn = QPushButton("删除")
        self.batch_export_btn = QPushButton("导出")
        for btn in (
            self.batch_enable_btn,
            self.batch_disable_btn,
            self.batch_delete_btn,
            self.batch_export_btn,
        ):
            btn.setToolTip("对勾选的规则生效；取消全部勾选后自动隐藏")
            btn.hide()
        self.up_btn = QPushButton("上移")
        self.down_btn = QPushButton("下移")
        self.only_enabled_cb = QCheckBox("只显示启用")
        self.only_enabled_cb.setToolTip(
            "勾选后列表只显示启用中的规则；停用规则仍在存储中，取消勾选即可看到。"
        )
        self.export_btn.setToolTip(
            "勾选规则时只导出勾选的；未勾选时导出全部。"
            "MiteProxy 原生 .json 格式，启停状态与顺序一并保存。"
        )
        self.import_native_btn.setToolTip(
            "导入 MiteProxy 导出的 .json 规则文件（追加到现有规则之后，"
            "不覆盖已有规则）。要导 Fiddler 的 .farx 请用旁边的按钮。"
        )
        self.delete_btn.setToolTip(
            "删除当前选中的规则；首列勾选了多条时删除勾选的。"
        )
        for b in (
            self.add_btn,
            self.edit_btn,
            self.delete_btn,
            self.batch_enable_btn,
            self.batch_disable_btn,
            self.batch_delete_btn,
            self.batch_export_btn,
            self.import_btn,
            self.import_native_btn,
            self.export_btn,
            self.up_btn,
            self.down_btn,
        ):
            toolbar.addWidget(b)
        toolbar.addSpacing(12)
        toolbar.addWidget(self.only_enabled_cb)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.table = RuleTable(self)
        # 列布局：勾选框 + 序号 + 名称在前（v1.15 批量操作 redesign：
        # 勾选的才是批量操作目标；序号与流量列表 MOCK#N 徽标对应）
        self.table.setHorizontalHeaderLabels(
            ["选", "序号", "名称", "启用", "匹配", "动作", "来源", "命中", "创建时间"]
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
        # 勾选列/序号列定宽（紧凑，不抢名称列空间）
        self.table.setColumnWidth(0, 32)
        self.table.setColumnWidth(1, 40)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # 批量操作（v1.15）：首列勾选后出现批量按钮，作用于勾选的规则
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.table)

        self.add_btn.clicked.connect(self._on_add)
        self.edit_btn.clicked.connect(self._on_edit)
        self.delete_btn.clicked.connect(self._on_delete)
        self.import_btn.clicked.connect(self._on_import)
        self.import_native_btn.clicked.connect(self._on_import_native)
        self.export_btn.clicked.connect(self._on_export)
        self.batch_enable_btn.clicked.connect(lambda: self._on_batch_set_enabled(True))
        self.batch_disable_btn.clicked.connect(lambda: self._on_batch_set_enabled(False))
        self.batch_delete_btn.clicked.connect(self._on_delete)
        self.batch_export_btn.clicked.connect(self._on_export)
        self.table.itemChanged.connect(self._on_item_changed)
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
        self._loading = True
        self.table.setRowCount(len(visible))
        global_index = {r.id: i + 1 for i, r in enumerate(self.store.all())}
        for i, rule in enumerate(visible):
            # 勾选列：批量操作的目标（勾选状态跨刷新保留）
            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(
                Qt.CheckState.Checked
                if rule.id in self._checked_ids
                else Qt.CheckState.Unchecked
            )
            check.setToolTip("勾选后可对该规则批量启用/停用/删除/导出")
            self.table.setItem(i, 0, check)
            # 序号列：规则在完整列表中的位置（1 起），与流量列表的
            # MOCK#N 徽标一致，方便定位「命中的是第几条」
            seq = QTableWidgetItem(str(global_index.get(rule.id, i + 1)))
            seq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            seq.setForeground(QBrush(theme.color("hint")))
            self.table.setItem(i, 1, seq)
            enabled_item = QTableWidgetItem("✔" if rule.enabled else "—")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            name = rule.name + (" ⚠" if rule.error else "")
            self.table.setItem(i, 2, QTableWidgetItem(name))
            self.table.setItem(i, 3, enabled_item)
            self.table.setItem(i, 4, QTableWidgetItem(_match_summary(rule)))
            self.table.setItem(i, 5, QTableWidgetItem(_action_summary(rule)))
            self.table.setItem(
                i, 6, QTableWidgetItem(SOURCE_LABELS.get(rule.source, rule.source))
            )
            self._fill_hits(i, rule)
            self._fill_created_at(i, rule)
            if rule.error:
                self.table.item(i, 2).setToolTip(rule.error)
        self._loading = False
        self._update_batch_buttons()

    def _fill_hits(self, row: int, rule) -> None:
        """命中列：0 次显示「—」（没干活过），有次数显示数字 + 最近命中时间提示。"""
        item = QTableWidgetItem("—" if not rule.hits else str(rule.hits))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if rule.hits:
            when = datetime.fromtimestamp(rule.last_hit).strftime("%H:%M:%S")
            item.setToolTip(f"最近命中 {when}")
        self.table.setItem(row, 7, item)

    def _fill_created_at(self, row: int, rule) -> None:
        """创建时间列：本地时间格式化；旧规则/导入规则无记录显示「—」。"""
        if rule.created_at:
            text = datetime.fromtimestamp(rule.created_at).strftime("%Y-%m-%d %H:%M")
        else:
            text = "—"
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 8, item)

    # ------------------------------------------------------------ 批量勾选

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """勾选框变化 → 维护 _checked_ids + 批量按钮显隐。"""
        if self._loading or item.column() != 0:
            return
        rule_id = (
            self._display_ids[item.row()]
            if 0 <= item.row() < len(self._display_ids)
            else None
        )
        if rule_id is None:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._checked_ids.add(rule_id)
        else:
            self._checked_ids.discard(rule_id)
        self._update_batch_buttons()

    def _update_batch_buttons(self) -> None:
        """勾选数 > 0 时才显示批量按钮，按钮文字带上数量。"""
        n = len(self._checked_ids)
        has = n > 0
        self.batch_enable_btn.setVisible(has)
        self.batch_disable_btn.setVisible(has)
        self.batch_delete_btn.setVisible(has)
        self.batch_export_btn.setVisible(has)
        self.batch_enable_btn.setText(f"启用({n})")
        self.batch_disable_btn.setText(f"停用({n})")
        self.batch_delete_btn.setText(f"删除({n})")
        self.batch_export_btn.setText(f"导出({n})")

    def _selected_rule_ids(self) -> list[str]:
        """批量操作目标 = 勾选的规则（按显示顺序）。"""
        return [rid for rid in self._display_ids if rid in self._checked_ids]

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
        item = self.table.item(row, 2)  # 名称列（列 0=勾选，列 1=序号）
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
        self.store.update(rule_id, enabled=not rule.enabled)
        self.refresh()

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

    # ------------------------------------------------------------ 批量操作

    def _on_batch_set_enabled(self, enabled: bool) -> None:
        ids = self._selected_rule_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先勾选规则（首列复选框）")
            return
        # 批量更新走 store.update_many：一次锁 + 一次后台落盘，选中很多条也不卡
        self.store.update_many(ids, enabled=enabled)
        self.refresh()

    def _on_delete(self) -> None:
        ids = self._selected_rule_ids()
        if not ids:
            rule = self._current_rule()
            if rule is None:
                return
            ids = [rule.id]
        names = []
        for rule_id in ids:
            rule = self.store.get(rule_id)
            if rule is not None:
                names.append(rule.name)
        if not names:
            return
        target = (
            f"「{names[0]}」" if len(names) == 1
            else f"{len(names)} 条规则（{('、'.join(names[:3]))}{'…' if len(names) > 3 else ''}）"
        )
        reply = QMessageBox.question(self, "确认删除", f"确定删除{target}？")
        if reply == QMessageBox.StandardButton.Yes:
            # 批量删除走 store.delete_many：一次锁 + 一次后台落盘
            self.store.delete_many(ids)
            # 清掉已删规则的勾选，避免批量按钮计数失准
            self._checked_ids.difference_update(ids)
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

    # -------------------------------------------------------- 原生导入/导出

    def _on_export(self) -> None:
        """导出规则为 MiteProxy 原生 .json（与 rules.json 同格式）。

        选中了若干行时只导出选中的；未选中导出全部。
        """
        ids = self._selected_rule_ids()
        if ids:
            rules = [r for r in (self.store.get(i) for i in ids) if r is not None]
            scope = f"勾选的 {len(rules)} 条"
        else:
            rules = self.store.all()
            scope = f"全部 {len(rules)} 条"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出规则",
            "miteproxy-rules.json",
            "MiteProxy 规则 (*.json);;所有文件 (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            payload = {
                "version": 1,
                "exported_from": "MiteProxy",
                "rules": [r.to_dict() for r in rules],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except OSError as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return
        QMessageBox.information(
            self, "导出完成", f"已导出{scope}规则到\n{path}"
        )

    def _on_import_native(self) -> None:
        """导入 MiteProxy 导出的 .json 规则文件（追加，不覆盖现有规则）。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入规则",
            "",
            "MiteProxy 规则 (*.json);;所有文件 (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "导入失败", f"文件读取/解析失败：{e}")
            return
        raw_rules = data.get("rules") if isinstance(data, dict) else data
        if not isinstance(raw_rules, list) or not raw_rules:
            QMessageBox.information(self, "无可导入规则", "文件里没有规则数据。")
            return
        rules = []
        for raw in raw_rules:
            try:
                rules.append(Rule.from_dict(raw))
            except Exception:
                continue  # 单条坏数据跳过，不影响其余
        if not rules:
            QMessageBox.information(self, "无可导入规则", "文件里的规则格式无法识别。")
            return
        count, _ = self.store.merge(rules)
        self.refresh()
        self.import_requested.emit()
        QMessageBox.information(self, "导入完成", f"成功导入 {count} 条规则")
