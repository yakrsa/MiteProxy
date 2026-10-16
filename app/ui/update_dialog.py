"""发现新版本时展示的更新对话框。

只负责「展示 + 引导下载」，不做任何网络请求——版本信息由 app/updater.py
取回后传进来。文案全部走 self.tr()，纳入中英双语。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app import updater as up


class UpdateDialog(QDialog):
    """展示远端版本号、发布日期与变更列表，并提供「前往下载」。"""

    def __init__(self, info: up.VersionInfo, parent=None) -> None:
        super().__init__(parent)
        self._info = info
        self.setWindowTitle(self.tr("发现新版本"))
        self.setMinimumWidth(520)
        self.setMinimumHeight(320)
        self._build_ui()

    # ---------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 版本对照：当前 -> 新版本
        headline = QLabel(
            self.tr("新版本 {0} 已发布（当前 {1}）").format(
                self._info.version, up.CURRENT_VERSION
            )
        )
        headline.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(headline)

        if self._info.published_at:
            when = QLabel(self.tr("发布日期：{0}").format(self._info.published_at))
            when.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(when)

        layout.addWidget(QLabel(self.tr("本次更新内容：")))

        changes = QListWidget(self)
        if self._info.changes:
            for line in self._info.changes:
                item = QListWidgetItem("• " + line)
                item.setToolTip(line)
                changes.addItem(item)
        else:
            # 远端没写变更说明（changes 为空）时也要有话可说，不能空着一块
            changes.addItem(QListWidgetItem(self.tr("（该版本未提供变更说明）")))
        layout.addWidget(changes, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        download_btn = QPushButton(self.tr("前往下载"))
        download_btn.setDefault(True)
        download_btn.clicked.connect(self._open_download)
        btn_row.addWidget(download_btn)
        close_btn = QPushButton(self.tr("关闭"))
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # ---------------------------------------------------------------- 动作

    def _open_download(self) -> None:
        QDesktopServices.openUrl(self._info.download_url)
        self.accept()
