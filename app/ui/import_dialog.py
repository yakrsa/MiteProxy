"""Fiddler 规则导入预览对话框（DESIGN.md 3.4.3）。

列出解析出的规则（可勾选）+ 跳过清单及原因，确认后合入规则库。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.rules import Rule
from app.ui import dialogs
from app.ui import theme

SOURCE_LABELS = {"farx": "FARX", "js": "CustomRules.js", "manual": "手动"}


def _match_summary(rule: Rule) -> str:
    type_labels = {
        "exact": "精确",
        "contains": "包含",
        "wildcard": "通配",
        "regex": "正则",
    }
    t = type_labels.get(rule.match.type, rule.match.type)
    if rule.match.method:
        return f"[{t}·{rule.match.method}] {rule.match.value}"
    return f"[{t}] {rule.match.value}"


def _action_summary(rule: Rule) -> str:
    if rule.action.redirect_url:
        parts = [f"重定向→{rule.action.redirect_url}"]
        if rule.action.latency_ms:
            parts.append(f"延迟{rule.action.latency_ms}ms")
        return " · ".join(parts)
    parts = [str(rule.action.status)]
    if rule.action.latency_ms:
        parts.append(f"延迟{rule.action.latency_ms}ms")
    if rule.action.body_source == "file":
        parts.append(f"文件:{rule.action.file_path}")
    elif rule.action.body:
        body = rule.action.body.replace("\n", " ")
        parts.append(body[:40] + ("…" if len(body) > 40 else ""))
    if rule.action.headers:
        parts.append(f"{len(rule.action.headers)}个header")
    return " · ".join(parts)


class ImportPreviewDialog(QDialog):
    def __init__(
        self,
        rules: list[Rule],
        skipped: list[tuple[str, str]],
        source_name: str,
        parent=None,
    ):
        super().__init__(parent)
        self.rules = rules
        self.setWindowTitle(f"导入 Fiddler 规则 — {source_name}")
        self.resize(720, 480)
        self._build_ui(rules, skipped)

    def _build_ui(self, rules: list[Rule], skipped: list[tuple[str, str]]) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel(
                f"识别到 <b>{len(rules)}</b> 条可导入规则，"
                f"<b>{len(skipped)}</b> 条跳过。勾选要导入的规则："
            )
        )

        # 全选/全不选
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        select_all = QPushButton("全选")
        select_none = QPushButton("全不选")
        select_all.clicked.connect(lambda: self._set_all_checked(True))
        select_none.clicked.connect(lambda: self._set_all_checked(False))
        btn_layout.addWidget(select_all)
        btn_layout.addWidget(select_none)
        btn_layout.addStretch(1)
        layout.addWidget(btn_row)

        self.table = QTableWidget(len(rules), 5)
        self.table.setHorizontalHeaderLabels(["", "名称", "匹配", "动作", "来源"])
        header = self.table.horizontalHeader()
        # 第 0 列（复选框）固定宽度：绝不被长 URL 经 ResizeToContents 挤没。
        # 匹配/动作列改 Interactive（可拖动查看、超出省略），不用 ResizeToContents
        # ——长 URL 会把整表撑爆、把名称/选择列压消失（导入多规则时的压缩 bug）。
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 30)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(2, 240)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 150)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i, rule in enumerate(rules):
            cb = QCheckBox()
            cb.setChecked(True)
            self.table.setCellWidget(i, 0, cb)
            self.table.setItem(i, 1, QTableWidgetItem(rule.name))
            self.table.setItem(i, 2, QTableWidgetItem(_match_summary(rule)))
            self.table.setItem(i, 3, QTableWidgetItem(_action_summary(rule)))
            self.table.setItem(
                i, 4, QTableWidgetItem(SOURCE_LABELS.get(rule.source, rule.source))
            )
        # 表格占主要垂直空间（stretch=1）：否则下方长长的跳过清单会把它压成一条，
        # 「勾选规则」的选择区域高度被吃没（导入多规则时的压缩 bug）。
        layout.addWidget(self.table, stretch=1)

        if skipped:
            skip_lines = "<br>".join(
                f"• <b>{name}</b>：{reason}" for name, reason in skipped[:20]
            )
            if len(skipped) > 20:
                skip_lines += f"<br>• ……等共 {len(skipped)} 条"
            skip_label = QLabel(skip_lines)
            skip_label.setWordWrap(True)
            skip_label.setContentsMargins(14, 0, 0, 0)
            skip_label.setStyleSheet(f"color: {theme.css('hint')};")
            # 跳过清单可折叠、默认收起：26 条原因若平铺会把上面的规则选择区域
            # 挤压/盖没。默认只占一行标题，需要看原因时点一下展开（内容限高可滚动）。
            self.skip_scroll = QScrollArea()
            self.skip_scroll.setWidget(skip_label)
            self.skip_scroll.setWidgetResizable(True)
            self.skip_scroll.setMaximumHeight(140)
            self.skip_scroll.setVisible(False)

            self.skip_toggle = QToolButton()
            self.skip_toggle.setText(f"跳过的规则及原因（{len(skipped)} 条）")
            self.skip_toggle.setCheckable(True)
            self.skip_toggle.setChecked(False)
            self.skip_toggle.setToolTip("点击展开 / 收起跳过的规则及原因")
            self.skip_toggle.setArrowType(Qt.ArrowType.RightArrow)
            self.skip_toggle.setStyleSheet(
                f"color: {theme.css('hint')}; border: none; text-align: left;"
            )
            self.skip_toggle.toggled.connect(self._on_skip_toggled)
            layout.addWidget(self.skip_toggle)
            layout.addWidget(self.skip_scroll)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("导入所选")
        dialogs.cn_button_box(buttons)     # Cancel → 取消（Ok 已自定义"导入所选"，保留）
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_rules(self) -> list[Rule]:
        out = []
        for i, rule in enumerate(self.rules):
            cb = self.table.cellWidget(i, 0)
            if isinstance(cb, QCheckBox) and cb.isChecked():
                out.append(rule)
        return out

    def _set_all_checked(self, checked: bool) -> None:
        for i in range(self.table.rowCount()):
            cb = self.table.cellWidget(i, 0)
            if isinstance(cb, QCheckBox):
                cb.setChecked(checked)

    def _on_skip_toggled(self, checked: bool) -> None:
        """展开/收起跳过清单：内容显隐 + 折叠箭头方向随之切换。"""
        self.skip_scroll.setVisible(checked)
        self.skip_toggle.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
