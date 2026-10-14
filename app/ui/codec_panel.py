"""编码转换面板（对齐 Fiddler 的 TextWizard）。

只做「文本进 / 文本出」：转换逻辑全在 app/codec.py（纯函数、可单测），
本模块只负责编辑框、下拉与按钮。实时转换带 180ms 防抖，超过 LIVE_LIMIT
就交回给用户点按钮——避免粘贴几 MB 文本后每敲一个字都全量重算。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.codec import (
    BY_KEY,
    LIVE_LIMIT,
    QUICK_KEYS,
    REVERSE,
    groups,
    run,
)

HINT_COLOR = "#6b6b6b"
ERROR_COLOR = "#e5534b"


def _mono_font() -> QFont:
    font = QFont("ui-monospace, SF Mono, Menlo, Consolas, monospace")
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


class CodecPanel(QWidget):
    """编码转换工具页。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = _mono_font()
        self._last_result = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addLayout(self._build_picker_row())
        root.addWidget(self._build_editors(), stretch=1)
        root.addLayout(self._build_action_row())
        root.addWidget(self._build_status())

        # 实时转换（防抖）
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self.run_now)

        self.input_edit.textChanged.connect(self._schedule)
        # 初始落在第一个真实转换（索引 0 是禁用的分组标题）
        self.set_key(QUICK_KEYS[0])
        self._sync_quick_buttons()
        self._update_counts()

    # ------------------------------------------------------------ 构建

    def _build_picker_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        row.addWidget(QLabel("常用:"))
        self.quick_buttons: dict[str, QPushButton] = {}
        for key in QUICK_KEYS:
            btn = QPushButton(BY_KEY[key].label)
            btn.setCheckable(True)
            btn.setToolTip(BY_KEY[key].hint)
            btn.clicked.connect(lambda _=False, k=key: self.set_key(k))
            self.quick_buttons[key] = btn
            row.addWidget(btn)

        row.addSpacing(10)
        row.addWidget(QLabel("转换:"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(220)
        for name, items in groups():
            self.combo.addItem(f"— {name} —", None)
            index = self.combo.count() - 1
            item = self.combo.model().item(index)
            if item is not None:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            for transform in items:
                self.combo.addItem(transform.label, transform.key)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        row.addWidget(self.combo)

        self.reverse_btn = QPushButton("反向 ⇄")
        self.reverse_btn.setToolTip("切到反向转换，并把结果填回输入（如 编码 → 解码）")
        self.reverse_btn.clicked.connect(self._on_reverse)
        row.addWidget(self.reverse_btn)

        row.addStretch(1)
        return row

    def _build_editors(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)

        in_box = QGroupBox("输入")
        in_layout = QVBoxLayout(in_box)
        self.input_edit = QPlainTextEdit()
        self.input_edit.setFont(self._font)
        self.input_edit.setPlaceholderText("把要转换的内容贴在这里…")
        in_layout.addWidget(self.input_edit)
        in_count = QHBoxLayout()
        in_count.addStretch(1)
        self.input_count = QLabel("")
        self.input_count.setStyleSheet(f"color: {HINT_COLOR};")
        in_count.addWidget(self.input_count)
        in_layout.addLayout(in_count)

        out_box = QGroupBox("结果")
        out_layout = QVBoxLayout(out_box)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setFont(self._font)
        self.output_edit.setReadOnly(True)
        self.output_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        out_layout.addWidget(self.output_edit)
        out_count = QHBoxLayout()
        out_count.addStretch(1)
        self.output_count = QLabel("")
        self.output_count.setStyleSheet(f"color: {HINT_COLOR};")
        out_count.addWidget(self.output_count)
        out_layout.addLayout(out_count)

        splitter.addWidget(in_box)
        splitter.addWidget(out_box)
        splitter.setSizes([300, 300])
        return splitter

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        self.run_btn = QPushButton("立即转换")
        self.run_btn.clicked.connect(self.run_now)
        row.addWidget(self.run_btn)

        self.feed_btn = QPushButton("结果填回输入 ↑")
        self.feed_btn.setToolTip("把结果放回输入框，便于连续做多次转换")
        self.feed_btn.clicked.connect(self._on_feed_back)
        row.addWidget(self.feed_btn)

        self.copy_btn = QPushButton("复制结果")
        self.copy_btn.clicked.connect(self.copy_result)
        row.addWidget(self.copy_btn)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.clicked.connect(self._on_clear)
        row.addWidget(self.clear_btn)

        row.addStretch(1)
        return row

    def _build_status(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {HINT_COLOR};")
        layout.addWidget(self.status_label)
        return box

    # ------------------------------------------------------------ 对外

    @property
    def current_key(self) -> str:
        key = self.combo.currentData()
        return key if isinstance(key, str) else QUICK_KEYS[0]

    def set_key(self, key: str) -> None:
        index = self.combo.findData(key)
        if index >= 0:
            self.combo.setCurrentIndex(index)
        else:  # pragma: no cover - 仅在传入未知 key 时
            self.run_now()

    def set_input(self, text: str, key: str | None = None) -> None:
        """外部灌入内容（如右键菜单「在编码转换中打开 body」）。

        灌完立即出结果——调用方拿到面板时结果就该是就绪的，不该等防抖定时器。
        """
        if key:
            self.set_key(key)
        self.input_edit.setPlainText(text)
        self.run_now()

    def run_now(self) -> None:
        """执行一次转换，结果写进输出框。"""
        self._timer.stop()
        key = self.current_key
        text = self.input_edit.toPlainText()
        result = run(key, text)
        self._last_result = result

        if result.error:
            self.output_edit.setPlainText("")
            self._set_status(result.error, is_error=True)
        else:
            self.output_edit.setPlainText(result.text)
            label = BY_KEY[key].label
            note = result.note or f"已执行「{label}」"
            self._set_status(note, is_error=False)
        self._update_counts()

    def copy_result(self) -> bool:
        text = self.output_edit.toPlainText()
        if not text:
            self._set_status("结果为空，无可复制内容", is_error=True)
            return False
        QApplication.clipboard().setText(text)
        self._set_status(
            f"已复制 {len(text)} 字符到剪贴板", is_error=False
        )
        return True

    # ------------------------------------------------------------ 内部

    def _schedule(self) -> None:
        self._update_counts()
        if len(self.input_edit.toPlainText().encode("utf-8")) > LIVE_LIMIT:
            self._timer.stop()
            self._set_status(
                f"内容超过 {LIVE_LIMIT // 1024}KB，已暂停自动转换——点「立即转换」执行",
                is_error=False,
            )
            return
        self._timer.start()

    def _on_combo_changed(self, _index: int) -> None:
        self._sync_quick_buttons()
        self.run_now()

    def _on_reverse(self) -> None:
        key = self.current_key
        target = REVERSE.get(key)
        if not target:
            self._set_status(
                f"「{BY_KEY[key].label}」没有反向转换（哈希不可逆）", is_error=False
            )
            return
        output = self.output_edit.toPlainText()
        self.set_key(target)
        if output:
            self.input_edit.setPlainText(output)
        # 无论有没有可回填的内容都重跑一次：点按钮就该立刻看到结果，
        # 而不是等 180ms 防抖（也避免 key 未变时信号不触发导致结果滞留）
        self.run_now()

    def _on_feed_back(self) -> None:
        output = self.output_edit.toPlainText()
        if not output:
            self._set_status("结果为空", is_error=False)
            return
        self.input_edit.setPlainText(output)
        self.run_now()

    def _on_clear(self) -> None:
        self.input_edit.clear()
        self.output_edit.clear()
        self._set_status("", is_error=False)
        self._update_counts()

    def _sync_quick_buttons(self) -> None:
        """四个常用按钮互斥高亮，且只在当前转换就是它们之一时亮。"""
        current = self.current_key
        for key, btn in self.quick_buttons.items():
            btn.setChecked(key == current)
        self.reverse_btn.setEnabled(current in REVERSE)

    def _set_status(self, text: str, *, is_error: bool) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color: {ERROR_COLOR};" if is_error else f"color: {HINT_COLOR};"
        )
        self.status_label.setToolTip(text if is_error else "")

    def _update_counts(self) -> None:
        def describe(text: str) -> str:
            if not text:
                return "0 字符"
            return f"{len(text)} 字符 / {len(text.encode('utf-8'))} 字节"

        self.input_count.setText(describe(self.input_edit.toPlainText()))
        self.output_count.setText(describe(self.output_edit.toPlainText()))
