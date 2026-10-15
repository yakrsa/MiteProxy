"""日志面板：把应用运行日志实时显示出来，并支持级别筛选 / 清空 / 打开磁盘日志。

- 应用所有模块都用 ``logging.getLogger(__name__)`` 打日志（INFO/WARNING/ERROR），
  之前只进 stderr（打包后落到 macOS 系统日志，界面看不到）。
- 这里加一个「日志」标签页：通过 ``QtLogHandler`` 把记录用 Qt 信号投递到主线程，
  避免代理线程跨线程直接碰 GUI；同时 ``app.main`` 会再挂一个滚动文件 handler，
  把日志落盘到 ``~/.miteproxy/logs/miteproxy.log``（带大小上限，不会无限增长）。
- 与底部状态栏互补：状态栏是「刚发生了什么」（几秒消失），
  日志页是「完整历史」（可筛选、可清空、重启后仍能从文件查）。
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.rules import CONFIG_DIR

#: 磁盘日志路径：~/.miteproxy/logs/miteproxy.log（main 里据此挂 RotatingFileHandler）
def get_log_path() -> Path:
    return CONFIG_DIR / "logs" / "miteproxy.log"


class QtLogHandler(QObject, logging.Handler):
    """把 logging 记录经 Qt 信号投递到主线程，跨线程安全。

    必须是 QObject 子类，Signal 才能在实例上绑定（否则访问到的是未绑定的
    Signal 类，没有 connect/emit）。多重继承里 QObject 放第一顺位。
    """

    #: (已格式化文本, 级别 levelno)
    new_record = Signal(str, int)

    def __init__(self) -> None:
        QObject.__init__(self)
        logging.Handler.__init__(self)
        self.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )

    def emit(self, record) -> None:  # noqa: A003 (logging 约定名)
        try:
            text = self.format(record)
            self.new_record.emit(text, record.levelno)
        except Exception:  # pragma: no cover - 日志本身出错不应崩界面
            self.handleError(record)


#: 各级别在文本区里的颜色（红/琥珀在深浅色主题下都看得清）
_LEVEL_COLORS = {
    logging.ERROR: "#e5484d",
    logging.WARNING: "#d9a23a",
}

#: 级别筛选下拉：文案 -> 最低级别阈值（记录 levelno >= 阈值才显示）
_FILTERS = [
    ("全部", logging.DEBUG),
    ("INFO 及以上", logging.INFO),
    ("WARNING 及以上", logging.WARNING),
    ("ERROR 及以上", logging.ERROR),
]

#: 内存里最多保留的行数（防止长时间运行把文本区撑爆；磁盘文件另有滚动上限）
_MAX_LINES = 5000


class LogPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lines: list[tuple[str, int]] = []  # (文本, levelno)
        self._threshold = logging.DEBUG

        # ---- 顶部工具栏：级别筛选 / 打开文件 / 清空
        bar = QHBoxLayout()
        bar.addWidget(QLabel("级别:"))
        self.level_combo = QComboBox()
        for label, lvl in _FILTERS:
            self.level_combo.addItem(label, lvl)
        self.level_combo.setCurrentIndex(0)
        self.level_combo.currentIndexChanged.connect(self._on_filter_changed)
        bar.addWidget(self.level_combo)
        bar.addStretch(1)

        self.open_btn = QPushButton("打开日志文件")
        self.open_btn.setToolTip("在访达中打开滚动日志文件（macOS）")
        self.open_btn.clicked.connect(self._open_log)
        bar.addWidget(self.open_btn)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setToolTip("清空当前显示的日志（不影响磁盘文件）")
        self.clear_btn.clicked.connect(self._clear)
        bar.addWidget(self.clear_btn)

        # ---- 日志文本区（只读、等宽、不自动换行便于看时间戳/路径）
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.text.setFont(_mono_font())
        self.text.setObjectName("log_text")

        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(self.text)

        # ---- 挂到 root logger；测试里可能多次构造 MainWindow，
        #      复用一个已存在的 handler，避免叠加出重复行。
        root = logging.getLogger()
        existing = next(
            (h for h in root.handlers if isinstance(h, QtLogHandler)), None
        )
        if existing is None:
            self._handler = QtLogHandler()
            self._handler.new_record.connect(self._append)
            root.addHandler(self._handler)
        else:
            self._handler = existing
            if not self._handler.receivers(self._handler.new_record):
                self._handler.new_record.connect(self._append)

    # ------------------------------------------------------------------ 数据
    def _append(self, text: str, levelno: int) -> None:
        self._lines.append((text, levelno))
        if len(self._lines) > _MAX_LINES:
            self._lines = self._lines[-_MAX_LINES:]
        if levelno >= self._threshold:
            self._append_line(text, levelno)
            self._autoscroll()

    def _append_line(self, text: str, levelno: int) -> None:
        color = _LEVEL_COLORS.get(levelno)
        if color:
            self.text.append(f'<span style="color:{color}">{_esc(text)}</span>')
        else:
            self.text.append(_esc(text))

    def _render(self) -> None:
        """按当前筛选重新渲染整个文本区（切换级别时调用）。"""
        self.text.clear()
        for text, levelno in self._lines:
            if levelno >= self._threshold:
                self._append_line(text, levelno)
        self._autoscroll()

    def _on_filter_changed(self, idx: int) -> None:
        self._threshold = self.level_combo.itemData(idx)
        self._render()

    def _clear(self) -> None:
        self._lines = []
        self.text.clear()

    # ------------------------------------------------------------------ 辅助
    def _autoscroll(self) -> None:
        sb = self.text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _open_log(self) -> None:
        path = get_log_path()
        if not path.exists():
            return
        if platform.system() == "Darwin":
            subprocess.run(["open", "-R", str(path)], check=False)
        elif platform.system() == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]  # 仅 Windows
        else:
            subprocess.run(["xdg-open", str(path)], check=False)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mono_font() -> QFont:
    f = QFont("Menlo, Monaco, Consolas, monospace")
    f.setPointSize(11)
    return f
