"""网络模拟面板（DESIGN.md 3.6）：弱网限速档位 + 域名映射表。

只负责「编辑与展示」，不碰代理：任何改动都只发 changed 信号，
由主窗口落盘并推给代理（单一职责，也便于 offscreen 单测）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.network import (
    DEFAULT_PRESET,
    MapRule,
    ThrottleConfig,
    describe_rule,
    preset_labels,
    preset_values,
)
from app.ui import theme

# 无效配置行（红底红字）与停用行（灰字）：theme.dynamic 就地随主题更新
INVALID_ROW_BG = theme.dynamic("invalid_bg")
INVALID_ROW_FG = theme.dynamic("invalid_fg")
DISABLED_ROW_FG = theme.dynamic("hint")

THROTTLE_HINT = (
    "延迟在响应返回给客户端前施加：档位给的固定延迟 + 按响应体大小折算的传输时间。\n"
    "用来复现 loading 态、超时、骨架屏；不是逐块限速。"
)

MAP_HINT = (
    "两种映射，按「目标」写法自动区分：\n"
    "• Map Remote：目标写 host:port（如 127.0.0.1:8080），把请求转发到该地址——"
    "只替换 scheme + 域名 + 端口，路径与 query 原样保留；\n"
    "• Map Local：目标写本地目录（如 ./static 或 ~/site），按 URL 路径取目录下的文件直接响应，"
    "文件不存在则透传上游（仅 GET/HEAD，防路径穿越）。\n"
    "原域名含 * + ? [ ] ( ) { } | \\ ^ $ 时按正则处理，否则按字面域名精确匹配；"
    "目标写 127.0.0.1:8080 时默认用 http，需要 https 就写 https://host:port。"
)


def _is_broken(rule: MapRule) -> bool:
    """行里填了东西、但 remote/local 两种形态都认不出 → 标红提示会被跳过。

    行内全空不算错（用户点了「+ 添加一行」还没填，不该立刻报红）；
    local 形态（目录路径）也不是错——它有自己的一套生效路径。
    """
    if not (rule.source.strip() or rule.target.strip()):
        return False
    return rule.kind == "unknown"


class NetworkPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False       # 灌数据时屏蔽信号，避免把加载当成用户编辑

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addWidget(self._build_throttle_box())
        root.addWidget(self._build_map_box(), stretch=1)
        root.addWidget(self._build_status_row())

    # ------------------------------------------------------------ 构建

    def _build_throttle_box(self) -> QGroupBox:
        box = QGroupBox("弱网模拟")
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        row = QHBoxLayout()
        row.addWidget(QLabel("档位:"))
        self.preset_combo = QComboBox()
        for key, label in preset_labels():
            self.preset_combo.addItem(label, key)
        self.preset_combo.setToolTip("关闭 = 不做任何延迟")
        row.addWidget(self.preset_combo)

        row.addSpacing(12)
        row.addWidget(QLabel("自定义延迟:"))
        self.latency_spin = QSpinBox()
        self.latency_spin.setRange(0, 30_000)
        self.latency_spin.setSingleStep(50)
        self.latency_spin.setSuffix(" ms")
        self.latency_spin.setToolTip("每个响应固定等待的时间（上限 30 秒）")
        row.addWidget(self.latency_spin)

        row.addWidget(QLabel("速率:"))
        self.rate_spin = QSpinBox()
        self.rate_spin.setRange(0, 10_000_000)
        self.rate_spin.setSingleStep(50)
        self.rate_spin.setSuffix(" kbps")
        self.rate_spin.setToolTip("按速率把响应体大小折算成传输时间，0 = 不限速")
        row.addWidget(self.rate_spin)

        row.addStretch(1)
        self.throttle_state = QLabel("")
        row.addWidget(self.throttle_state)
        layout.addLayout(row)

        hint = QLabel(THROTTLE_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.css('hint')};")
        layout.addWidget(hint)
        self._hint_labels = [hint]

        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.latency_spin.valueChanged.connect(self._on_numbers_changed)
        self.rate_spin.valueChanged.connect(self._on_numbers_changed)
        return box

    def _build_map_box(self) -> QGroupBox:
        box = QGroupBox("域名映射（Map Remote / Map Local）")
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        self.map_table = QTableWidget(0, 3)
        self.map_table.setHorizontalHeaderLabels(
            ["启用", "原域名", "目标 host:port / 本地目录"]
        )
        self.map_table.verticalHeader().setVisible(False)
        self.map_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.map_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.map_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.map_table.setColumnWidth(0, 56)
        layout.addWidget(self.map_table, stretch=1)

        row = QHBoxLayout()
        self.add_btn = QPushButton("+ 添加一行")
        self.del_btn = QPushButton("删除选中行")
        row.addWidget(self.add_btn)
        row.addWidget(self.del_btn)
        row.addStretch(1)
        self.map_state = QLabel("")
        row.addWidget(self.map_state)
        layout.addLayout(row)

        hint = QLabel(MAP_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.css('hint')};")
        layout.addWidget(hint)
        self._hint_labels.append(hint)
        theme.add_listener(self._retheme)

        self.add_btn.clicked.connect(self._on_add_row)
        self.del_btn.clicked.connect(self._on_del_rows)
        self.map_table.itemChanged.connect(self._on_item_changed)
        return box

    def _build_status_row(self) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label, stretch=1)
        return wrapper

    # ------------------------------------------------------------ 配置同步

    def load_config(self, throttle: ThrottleConfig, rules: list[MapRule]) -> None:
        self._loading = True
        try:
            idx = self.preset_combo.findData(throttle.preset)
            self.preset_combo.setCurrentIndex(max(idx, 0))
            self.latency_spin.setValue(int(throttle.latency_ms))
            self.rate_spin.setValue(int(throttle.rate_kbps))

            self.map_table.setRowCount(0)
            for rule in rules:
                self._append_row(rule)
            self._sync_throttle_numbers()
            self._refresh_states()
        finally:
            self._loading = False

    def to_throttle(self) -> ThrottleConfig:
        """当前面板值（纯读取，不改动控件——避免和信号形成回路）。"""
        return ThrottleConfig(
            preset=self.preset_combo.currentData() or DEFAULT_PRESET,
            latency_ms=self.latency_spin.value(),
            rate_kbps=self.rate_spin.value(),
        )

    def to_rules(self) -> list[MapRule]:
        rules = []
        for r in range(self.map_table.rowCount()):
            rules.append(
                MapRule(
                    source=self._text(r, 1),
                    target=self._text(r, 2),
                    enabled=self._checked(r),
                )
            )
        return rules

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    @property
    def is_editing_custom(self) -> bool:
        return self.preset_combo.currentData() == "custom"

    # ------------------------------------------------------------ 行操作

    def _append_row(self, rule: MapRule) -> None:
        row = self.map_table.rowCount()
        self.map_table.insertRow(row)

        check = QTableWidgetItem()
        check.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        check.setCheckState(
            Qt.CheckState.Checked if rule.enabled else Qt.CheckState.Unchecked
        )
        self.map_table.setItem(row, 0, check)
        self.map_table.setItem(row, 1, QTableWidgetItem(rule.source))
        self.map_table.setItem(row, 2, QTableWidgetItem(rule.target))

    def _on_add_row(self) -> None:
        if self._loading:
            return
        self._loading = True
        try:
            self._append_row(MapRule(source="", target="", enabled=True))
        finally:
            self._loading = False
        self.map_table.setCurrentCell(self.map_table.rowCount() - 1, 1)
        self.map_table.editItem(self.map_table.item(self.map_table.rowCount() - 1, 1))
        self._after_edit()

    def _on_del_rows(self) -> None:
        if self._loading:
            return
        rows = sorted(
            {i.row() for i in self.map_table.selectedIndexes()}, reverse=True
        )
        if not rows:
            return
        self._loading = True
        try:
            for r in rows:
                self.map_table.removeRow(r)
        finally:
            self._loading = False
        self._after_edit()

    def _on_item_changed(self, _item) -> None:
        if self._loading:
            return
        self._after_edit()

    # ------------------------------------------------------------ 内部

    def _on_preset_changed(self) -> None:
        if self._loading:
            return
        self._loading = True
        try:
            self._sync_throttle_numbers()
        finally:
            self._loading = False
        self._after_edit()

    def _on_numbers_changed(self) -> None:
        if self._loading:
            return
        # 手动改了数字 → 自动切到「自定义」，否则下次加载会被档位表覆盖掉。
        # 切换的同时同步一次控件可用状态（否则输入框会停在禁用态，看着像坏了）。
        self._loading = True
        try:
            if self.preset_combo.currentData() != "custom":
                idx = self.preset_combo.findData("custom")
                self.preset_combo.setCurrentIndex(max(idx, 0))
            self._sync_throttle_numbers()
        finally:
            self._loading = False
        self._after_edit()

    def _sync_throttle_numbers(self) -> None:
        key = self.preset_combo.currentData() or DEFAULT_PRESET
        custom = key == "custom"
        for w in (self.latency_spin, self.rate_spin):
            w.setEnabled(custom)
        if not custom:
            _, _, latency, rate = preset_values(key)
            self.latency_spin.setValue(latency)
            self.rate_spin.setValue(rate)

    def _after_edit(self) -> None:
        self._refresh_states()
        self.changed.emit()

    def _refresh_states(self) -> None:
        cfg = self.to_throttle()
        if not cfg.enabled:
            self.throttle_state.setText("未启用")
        else:
            parts = []
            if cfg.latency_ms:
                parts.append(f"延迟 {cfg.latency_ms} ms")
            if cfg.rate_kbps:
                parts.append(f"限速 {cfg.rate_kbps} kbps")
            self.throttle_state.setText("生效中：" + " + ".join(parts))

        for r in range(self.map_table.rowCount()):
            rule = MapRule(
                source=self._text(r, 1), target=self._text(r, 2), enabled=self._checked(r)
            )
            hint = describe_rule(rule)
            invalid = _is_broken(rule)
            for col in range(3):
                item = self.map_table.item(r, col)
                if item is None:
                    continue
                item.setToolTip(hint)
                if invalid:
                    item.setBackground(INVALID_ROW_BG)
                    item.setForeground(INVALID_ROW_FG)
                elif not rule.enabled:
                    item.setBackground(QBrush())
                    item.setForeground(DISABLED_ROW_FG)
                else:
                    # 清掉刷子 = 回到主题默认前景/背景（深色主题下别写死颜色）
                    item.setBackground(QBrush())
                    item.setForeground(QBrush())
        self._refresh_map_state()

    def _retheme(self) -> None:
        """主题切换：说明文字重染 + 映射行按当前状态重新着色。"""
        for hint in self._hint_labels:
            hint.setStyleSheet(f"color: {theme.css('hint')};")
        self._refresh_states()

    def _refresh_map_state(self) -> None:
        rules = self.to_rules()
        broken = [r for r in rules if _is_broken(r)]
        active = [r for r in rules if r.is_usable() and not _is_broken(r)]
        text = f"已启用 {len(active)} 条映射"
        if broken:
            text += f"，{len(broken)} 条填写不完整（已跳过）"
        self.map_state.setText(text)

    def _text(self, row: int, col: int) -> str:
        item = self.map_table.item(row, col)
        return item.text().strip() if item is not None else ""

    def _checked(self, row: int) -> bool:
        item = self.map_table.item(row, 0)
        return item is not None and item.checkState() == Qt.CheckState.Checked
