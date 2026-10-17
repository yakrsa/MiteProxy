"""意见反馈对话框（v1.15）：填写内容 -> 附诊断信息 -> 提交 GitHub Issue。

网络发送用 QNetworkAccessManager 异步执行（不阻塞 UI，且自动跟随
系统代理设置——用户开着本应用代理时也照常走通）。测试通过
``transport`` 注入假实现。
"""

from __future__ import annotations

import json

from PySide6.QtCore import QUrl, Qt
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app import feedback as fb


class FeedbackDialog(QDialog):
    def __init__(self, parent=None, transport=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("意见反馈"))
        self.setMinimumWidth(520)
        # transport: 可注入的发送函数 (url, data, headers) -> None，
        # 结果仍需经 finish_transport(status, raw, err) 回流；None 用真网络。
        self._transport = transport
        self._reply: QNetworkReply | None = None
        self._nam = QNetworkAccessManager(self) if transport is None else None
        self._build_ui()
        self._check_token()

    # ---------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(self.tr("遇到问题或有功能建议？描述越具体越容易定位：")))
        self.nick_edit = QLineEdit()
        self.nick_edit.setPlaceholderText(self.tr("你的昵称（必填，≤64 字符；会显示在 issue 标题上）"))
        self.nick_edit.setMaxLength(fb.NICKNAME_MAX_LEN)
        layout.addWidget(self.nick_edit)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(self.tr("一句话概括（必填），如：导入 Fiddler 规则后中文乱码"))
        layout.addWidget(self.title_edit)

        self.body_edit = QPlainTextEdit()
        self.body_edit.setPlaceholderText(
            self.tr("详细描述（必填）：做了什么操作、期望的结果、实际的结果…")
        )
        layout.addWidget(self.body_edit, 1)

        hint = QLabel(
            self.tr('提交后会自动附带 App 版本 / 系统信息，并以公开 issue 形式创建到 GitHub（{0}）。昵称会显示在 issue 标题上，便于我们回复与追溯。').format(fb.GITHUB_REPO)
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.diag_view = QPlainTextEdit()
        self.diag_view.setReadOnly(True)
        self.diag_view.setPlainText(fb.collect_diagnostics())
        self.diag_view.setFixedHeight(84)
        layout.addWidget(self.diag_view)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.submit_btn = QPushButton(self.tr("提交"))
        self.submit_btn.setDefault(True)
        self.submit_btn.clicked.connect(self._on_submit)
        cancel_btn = QPushButton(self.tr("取消"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.submit_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

    # ---------------------------------------------------------------- 提交

    def _check_token(self) -> None:
        if not fb.get_token():
            self._show_status(
                self.tr('开发者尚未配置反馈通道，请到 GitHub 手动提 issue：{0}').format(fb.NEW_ISSUE_URL),
                error=True,
            )
            self.submit_btn.setEnabled(False)

    def _on_submit(self) -> None:
        nickname = self.nick_edit.text().strip()
        title = self.title_edit.text().strip()
        content = self.body_edit.toPlainText().strip()
        if not nickname:
            self._show_status(self.tr("请填写昵称（必填，会显示在 issue 标题上）。"), error=True)
            return
        if not title or not content:
            self._show_status(self.tr("标题和内容都需要填写。"), error=True)
            return
        if self._reply is not None:
            return  # 已在提交中
        self.submit_btn.setEnabled(False)
        self._show_status(self.tr("正在提交…"))
        body = fb.build_issue_body(content, fb.collect_diagnostics(), nickname)
        data = fb.payload(fb.build_issue_title(nickname, title), body)
        headers = fb.headers(fb.get_token())
        if self._transport is not None:
            self._transport(fb.ISSUES_API, data, headers)
        else:
            self._send_network(fb.ISSUES_API, data, headers)

    def _send_network(self, url: str, data: dict, headers: dict) -> None:
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(fb.REQUEST_TIMEOUT_MS)
        for key, value in headers.items():
            request.setRawHeader(key.encode("utf-8"), value.encode("utf-8"))
        payload_bytes = json.dumps(data).encode("utf-8")
        self._reply = self._nam.post(request, payload_bytes)
        self._reply.finished.connect(self._on_network_finished)

    def finish_transport(self, status: int, raw: bytes = b"", err: str = "") -> None:
        """注入 transport 的测试/假实现通过它回流结果。"""
        self._settle(*fb.parse_issue_response(status, raw, err))

    def _on_network_finished(self) -> None:
        reply = self._reply
        if reply is None:
            return
        status = reply.attribute(
            QNetworkRequest.Attribute.HttpStatusCodeAttribute
        )
        status = int(status) if status is not None else 0
        err = reply.errorString() if reply.error() != QNetworkReply.NetworkError.NoError else ""
        raw = bytes(reply.readAll())
        reply.deleteLater()
        self._reply = None
        self._settle(*fb.parse_issue_response(status, raw, err))

    def _settle(self, ok: bool, message: str, issue_url: str) -> None:
        self.submit_btn.setEnabled(True)
        if ok:
            self.status_label.setVisible(False)
            from PySide6.QtWidgets import QMessageBox

            box = QMessageBox(self)
            box.setWindowTitle(self.tr("意见反馈"))
            box.setText(message + (f"\n{issue_url}" if issue_url else ""))
            box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.exec()
            self.accept()
        else:
            self._show_status(message, error=True)

    def _show_status(self, text: str, error: bool = False) -> None:
        self.status_label.setVisible(True)
        self.status_label.setStyleSheet(
            "color: #c62828;" if error else "color: inherit;"
        )
        self.status_label.setText(text)
