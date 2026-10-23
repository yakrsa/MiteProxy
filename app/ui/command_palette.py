"""命令面板（Ctrl/Cmd+K）：一个可搜索的快捷动作启动器。

唤起后在弹层里输入关键字，实时过滤出匹配的命令（标题 + 关键词），
上下键选择、回车执行、Esc / 点外部关闭。命令列表由主窗口在唤起时构建
（部分标题随状态变化，如「启动代理 / 停止代理」），每条命令带一个
``run`` 回调，执行后弹层关闭再触发回调，避免回调里的对话框被弹层挡住。

命令标题在传入前已由主窗口用 ``self.tr(...)`` 翻好（i18n 在构建期完成），
本面板只负责展示与筛选，不再做翻译。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QLineEdit,
)


class CommandPalette(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Popup：点外部 / Esc 自动关闭，不挡主窗口交互
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setMinimumWidth(460)
        self.setMaximumHeight(420)
        self._commands: list[dict] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.query = QLineEdit()
        self.query.setPlaceholderText(self.tr("输入命令名或动作…"))
        self.query.setClearButtonEnabled(True)
        root.addWidget(self.query)

        self.list = QListWidget()
        self.list.setUniformItemSizes(True)
        root.addWidget(self.list)

        self.query.textChanged.connect(self._filter)
        self.query.installEventFilter(self)
        # 双击直接执行
        self.list.itemActivated.connect(lambda _item: self._run_current())

    # ---------------------------------------------------------- 命令注入

    def set_commands(self, commands: list[dict]) -> None:
        self._commands = list(commands)

    def _filter(self) -> None:
        text = self.query.text().strip().lower()
        self.list.clear()
        for cmd in self._commands:
            hay = f"{cmd.get('title', '')} {cmd.get('keywords', '')}".lower()
            if not text or text in hay:
                item = QListWidgetItem(cmd.get("title", ""))
                item.setData(Qt.ItemDataRole.UserRole, cmd)
                hint = cmd.get("hint")
                if hint:
                    item.setToolTip(hint)
                self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    # ---------------------------------------------------------- 键盘

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        if obj is self.query and isinstance(ev, QKeyEvent) \
                and ev.type() == QKeyEvent.Type.KeyPress:
            key = ev.key()
            if key == Qt.Key.Key_Escape:
                self.reject()
                return True
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self._move_selection(1 if key == Qt.Key.Key_Down else -1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._run_current()
                return True
        return super().eventFilter(obj, ev)

    def _move_selection(self, delta: int) -> None:
        count = self.list.count()
        if count == 0:
            return
        cur = self.list.currentRow()
        if cur < 0:
            cur = 0
        nxt = max(0, min(count - 1, cur + delta))
        self.list.setCurrentRow(nxt)

    def _run_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        cmd = item.data(Qt.ItemDataRole.UserRole)
        if not cmd:
            return
        run = cmd.get("run")
        if not callable(run):
            return
        self.accept()
        run()

    # ---------------------------------------------------------- 显示

    def showEvent(self, _ev) -> None:  # noqa: N802
        self.query.clear()
        self._filter()
        self.query.setFocus()
        self.query.selectAll()
