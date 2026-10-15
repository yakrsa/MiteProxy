"""Mock 规则编辑器对话框（DESIGN.md 3.3 / 3.3.1~3.3.3）。

覆盖：四种匹配、请求方法过滤（任意 / GET / POST / …）、内联 / 本地文件 /
重定向到其他 URL 三种响应模式、任意状态码 + 预设、自定义 headers、模拟延迟。
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.rules import (
    CONTAINS,
    EXACT,
    MAX_LATENCY_MS,
    REGEX,
    WILDCARD,
    Action,
    Match,
    Rule,
    RuleStore,
)
from app.ui import theme

STATUS_PRESETS = [200, 400, 401, 403, 404, 429, 500, 502, 503, 504]

MATCH_LABELS = [
    (EXACT, "精确（完整 URL 相等）"),
    (CONTAINS, "包含（URL 含子串）"),
    (WILDCARD, "通配符（* 不含 /，** 任意）"),
    (REGEX, "正则表达式"),
]

METHODS = ["", "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]

METHOD_LABELS = {
    "": "任意方法",
    "GET": "GET",
    "POST": "POST",
    "PUT": "PUT",
    "DELETE": "DELETE",
    "PATCH": "PATCH",
    "HEAD": "HEAD",
    "OPTIONS": "OPTIONS",
}


class RuleEditorDialog(QDialog):
    def __init__(self, store: RuleStore, rule: Rule | None = None, parent=None):
        super().__init__(parent)
        self.store = store
        self.rule = rule or Rule.create()
        self.setWindowTitle("编辑 Mock 规则" if rule else "新增 Mock 规则")
        self.setMinimumWidth(640)
        self._build_ui()
        self._load_rule()

    # ------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        # macOS 上 QFormLayout 默认字段不横向拉伸（Mac 风格字段保持自身
        # 尺寸），名称/URL 输入框会缩成一小截——明确要求所有非固定字段占满列宽
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.name_edit = QLineEdit()
        form.addRow("规则名称:", self.name_edit)

        # URL 值很可能很长：类型下拉单独一行，值输入框另起一行占满整行
        match_type_row = QWidget()
        match_type_layout = QHBoxLayout(match_type_row)
        match_type_layout.setContentsMargins(0, 0, 0, 0)
        self.match_type_combo = QComboBox()
        for mtype, label in MATCH_LABELS:
            self.match_type_combo.addItem(label, mtype)
        match_type_layout.addWidget(self.match_type_combo)
        match_type_layout.addStretch(1)
        self.match_value_edit = QLineEdit()
        self.match_value_edit.setPlaceholderText("如 /api/user/list 或 https?://.*/v1/.*")
        match_col = QWidget()
        match_layout = QVBoxLayout(match_col)
        match_layout.setContentsMargins(0, 0, 0, 0)
        match_layout.setSpacing(6)
        match_layout.addWidget(match_type_row)
        match_layout.addWidget(self.match_value_edit)
        form.addRow("URL 匹配:", match_col)

        # 请求方法过滤（比 Fiddler 好：不用自己拼正则区分方法）
        self.method_combo = QComboBox()
        for m in METHODS:
            self.method_combo.addItem(METHOD_LABELS.get(m, m), m)
        form.addRow("请求方法:", self.method_combo)

        # 从抓包请求生成 Mock 时带入的原始请求 Body（只读参考，不参与 URL 匹配）
        self.req_body_edit = QPlainTextEdit()
        self.req_body_edit.setReadOnly(True)
        self.req_body_edit.setMaximumHeight(70)
        self.req_body_edit.setPlaceholderText(
            "从抓包请求带入的原始请求 Body（仅参考，不参与 URL 匹配）"
        )
        form.addRow("请求 Body:", self.req_body_edit)

        # 状态码 + 预设
        status_row = QWidget()
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_edit = QLineEdit("200")
        self.status_edit.setMaximumWidth(70)
        status_layout.addWidget(self.status_edit)
        for code in STATUS_PRESETS:
            btn = QPushButton(str(code))
            btn.setMaximumWidth(44)
            btn.clicked.connect(lambda _=False, c=code: self.status_edit.setText(str(c)))
            status_layout.addWidget(btn)
        status_layout.addStretch(1)
        form.addRow("状态码(100-599):", status_row)

        # 延迟
        self.latency_edit = QLineEdit("0")
        self.latency_edit.setMaximumWidth(90)
        latency_row = QWidget()
        latency_layout = QHBoxLayout(latency_row)
        latency_layout.setContentsMargins(0, 0, 0, 0)
        latency_layout.addWidget(self.latency_edit)
        latency_layout.addWidget(QLabel("毫秒（0 = 不延迟）"))
        latency_layout.addStretch(1)
        form.addRow("模拟延迟:", latency_row)

        # body 来源（三种模式：内联 / 本地文件 / 重定向到其他 URL）
        source_row = QWidget()
        source_layout = QHBoxLayout(source_row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        self.inline_radio = QRadioButton("直接输入内容")
        self.file_radio = QRadioButton("返回本地文件")
        self.redirect_radio = QRadioButton("重定向到其他 URL")
        self.inline_radio.setChecked(True)
        source_layout.addWidget(self.inline_radio)
        source_layout.addWidget(self.file_radio)
        source_layout.addWidget(self.redirect_radio)
        source_layout.addStretch(1)
        form.addRow("响应内容:", source_row)

        # 重定向目标（redirect 模式专用）
        self.redirect_edit = QLineEdit()
        self.redirect_edit.setPlaceholderText(
            "如 https://staging.example.com/api/user，支持 $1 替换（正则捕获组）"
        )
        form.addRow("重定向到:", self.redirect_edit)

        self.body_edit = QPlainTextEdit()
        self.body_edit.setPlaceholderText("响应 body，如 JSON / HTML …")
        form.addRow("Body:", self.body_edit)

        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("命中时读取该文件内容返回（请求时读取，改文件即生效）")
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self.file_path_edit, stretch=1)
        file_layout.addWidget(browse_btn)
        form.addRow("文件路径:", file_row)

        # headers
        headers_row = QWidget()
        headers_layout = QVBoxLayout(headers_row)
        headers_layout.setContentsMargins(0, 0, 0, 0)
        self.headers_table = QTableWidget(0, 2)
        self.headers_table.setHorizontalHeaderLabels(["Header", "Value"])
        self.headers_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.headers_table.setMaximumHeight(120)
        self.headers_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        headers_layout.addWidget(self.headers_table)
        hbtn_row = QWidget()
        hbtn_layout = QHBoxLayout(hbtn_row)
        hbtn_layout.setContentsMargins(0, 0, 0, 0)
        add_h = QPushButton("添加 Header")
        add_h.clicked.connect(lambda: self.headers_table.insertRow(self.headers_table.rowCount()))
        del_h = QPushButton("删除选中行")
        del_h.clicked.connect(self._delete_header_row)
        hbtn_layout.addWidget(add_h)
        hbtn_layout.addWidget(del_h)
        hbtn_layout.addStretch(1)
        headers_layout.addWidget(hbtn_row)
        form.addRow("Headers:", headers_row)

        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"color: {theme.css('error')};")
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for radio in (self.inline_radio, self.file_radio, self.redirect_radio):
            radio.toggled.connect(self._sync_source_widgets)
        self._sync_source_widgets()

    # ------------------------------------------------------------ 数据

    def _load_rule(self) -> None:
        r = self.rule
        self.name_edit.setText(r.name)
        idx = self.match_type_combo.findData(r.match.type)
        self.match_type_combo.setCurrentIndex(max(idx, 0))
        self.match_value_edit.setText(r.match.value)
        midx = self.method_combo.findData(r.match.method or "")
        self.method_combo.setCurrentIndex(max(midx, 0))
        self.req_body_edit.setPlainText(getattr(r, "request_body", ""))
        self.status_edit.setText(str(r.action.status))
        self.latency_edit.setText(str(r.action.latency_ms))
        if r.action.redirect_url:
            self.redirect_radio.setChecked(True)
            self.redirect_edit.setText(r.action.redirect_url)
        elif r.action.body_source == "file":
            self.file_radio.setChecked(True)
            self.file_path_edit.setText(r.action.file_path or "")
        else:
            self.inline_radio.setChecked(True)
            self.body_edit.setPlainText(r.action.body)
        self.headers_table.setRowCount(0)
        for k, v in r.action.headers.items():
            row = self.headers_table.rowCount()
            self.headers_table.insertRow(row)
            self.headers_table.setItem(row, 0, QTableWidgetItem(k))
            self.headers_table.setItem(row, 1, QTableWidgetItem(v))

    def _collect(self) -> tuple[bool, str]:
        name = self.name_edit.text().strip()
        if not name:
            return False, "规则名称不能为空"
        match_type = self.match_type_combo.currentData()
        match_value = self.match_value_edit.text().strip()
        if not match_value:
            return False, "匹配值不能为空"
        if match_type == REGEX:
            try:
                re.compile(match_value)
            except re.error as e:
                return False, f"正则无效: {e}"
        method = self.method_combo.currentData() or ""

        try:
            latency = int(self.latency_edit.text().strip() or "0")
        except ValueError:
            return False, "延迟必须是整数毫秒"
        if not (0 <= latency <= MAX_LATENCY_MS):
            return False, f"延迟必须在 0~{MAX_LATENCY_MS} 毫秒之间"

        # ---- 重定向模式：status/headers/body 均不生效
        if self.redirect_radio.isChecked():
            redirect_url = self.redirect_edit.text().strip()
            if not redirect_url:
                return False, "重定向目标不能为空"
            if not (redirect_url.startswith("http://") or redirect_url.startswith("https://")):
                return False, "重定向目标必须以 http:// 或 https:// 开头"
            action = Action(redirect_url=redirect_url, latency_ms=latency)
            return True, self._apply(name, match_type, match_value, method, action)

        try:
            status = int(self.status_edit.text().strip())
        except ValueError:
            return False, "状态码必须是整数"
        if not (100 <= status <= 599):
            return False, "状态码必须在 100~599 之间"

        headers = {}
        for row in range(self.headers_table.rowCount()):
            k_item = self.headers_table.item(row, 0)
            v_item = self.headers_table.item(row, 1)
            if k_item is None or not k_item.text().strip():
                continue
            headers[k_item.text().strip()] = (v_item.text() if v_item else "")

        if self.file_radio.isChecked():
            file_path = self.file_path_edit.text().strip()
            if not file_path:
                return False, "请选择本地文件路径"
            import os

            if not os.path.isfile(os.path.expanduser(file_path)):
                return False, f"文件不存在: {file_path}"
            action = Action(
                status=status,
                headers=headers,
                body_source="file",
                body="",
                file_path=file_path,
                latency_ms=latency,
            )
        else:
            action = Action(
                status=status,
                headers=headers,
                body_source="inline",
                body=self.body_edit.toPlainText(),
                latency_ms=latency,
            )
        return True, self._apply(name, match_type, match_value, method, action)

    def _apply(
        self,
        name: str,
        match_type: str,
        match_value: str,
        method: str,
        action: Action,
    ) -> str:
        is_new = not any(
            r.id == self.rule.id for r in self.store.all()
        )
        self.rule.name = name
        self.rule.match = Match(type=match_type, value=match_value, method=method)
        self.rule.action = action
        if is_new:
            self.store.add(self.rule)
        else:
            self.store.update(
                self.rule.id,
                name=name,
                match={"type": match_type, "value": match_value, "method": method},
                action=action.to_dict(),
            )
        return "ok"

    # ------------------------------------------------------------ 事件

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 mock 响应文件")
        if path:
            self.file_path_edit.setText(path)

    def _delete_header_row(self) -> None:
        for idx in sorted(
            {i.row() for i in self.headers_table.selectedIndexes()}, reverse=True
        ):
            self.headers_table.removeRow(idx)

    def _sync_source_widgets(self) -> None:
        redirect = self.redirect_radio.isChecked()
        is_file = self.file_radio.isChecked()
        self.body_edit.setVisible(not is_file and not redirect)
        self.file_path_edit.setVisible(is_file)
        self.redirect_edit.setVisible(redirect)
        # 重定向模式下 status/headers 都不生效：置灰防止用户白配一场
        self.status_edit.setEnabled(not redirect)
        self.headers_table.setEnabled(not redirect)

    def _on_accept(self) -> None:
        ok, msg = self._collect()
        if not ok:
            self.error_label.setText(msg)
            return
        self.accept()
