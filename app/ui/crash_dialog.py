"""崩溃诊断上报对话框：把上次异常退出的证据整理成 issue 发给开发者。

设计取向是**用户看得见、能拒绝**：

- 发送前必须让用户看到完整内容（预览框），不搞静默后台上传；
- 默认不含请求地址（``actions.log`` 里带 URL 与 query），要用户主动勾选才给；
- 两个勾选项分别控制「操作轨迹」与「请求地址」，随时可改，预览实时刷新；
- 明确告知会创建公开 issue。

网络发送复用 :mod:`app.feedback` 的 GitHub Issues 通道（同一 token、同一仓库），
用 QNetworkAccessManager 异步发送，测试通过 ``transport`` 注入假实现。
"""

from __future__ import annotations

import json

from PySide6.QtCore import QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app import feedback as fb


class CrashReportDialog(QDialog):
    """询问并发送上次崩溃/卡死的诊断报告。"""

    #: 用户选择「不再提示」：由调用方负责把偏好落盘（本对话框不碰设置）
    mute_requested = Signal()

    def __init__(self, summary: dict, parent=None, transport=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("上次异常退出"))
        self.setMinimumSize(680, 560)
        self.summary = summary or {}
        # transport: 可注入的发送函数 (url, data, headers) -> None；
        # 结果仍需经 finish_transport(status, raw, err) 回流；None 用真网络。
        self._transport = transport
        self._reply: QNetworkReply | None = None
        #: 是否已有一次提交在途。用独立标志而不是看 _reply：注入假 transport 时
        #: 根本没有 reply，只靠 _reply 判断会让连点发出重复 issue。
        self._sending = False
        self._nam = QNetworkAccessManager(self) if transport is None else None
        self._build_ui()
        self._refresh_preview()

    # ---------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        head = QLabel(self.tr(
            "上次 MiteProxy 没有正常退出（崩溃或界面卡死）。"
            "把这份诊断报告发给开发者，能大幅缩短定位时间。"
        ))
        head.setWordWrap(True)
        layout.addWidget(head)

        self.actions_check = QCheckBox(self.tr("包含最近的操作记录（双击了哪条请求、各步耗时、内存占用）"))
        self.actions_check.setChecked(True)
        self.actions_check.toggled.connect(self._refresh_preview)
        layout.addWidget(self.actions_check)

        self.urls_check = QCheckBox(self.tr("包含请求地址（URL 的域名与路径；query 参数一律抹掉）"))
        self.urls_check.setChecked(False)
        self.urls_check.toggled.connect(self._refresh_preview)
        layout.addWidget(self.urls_check)

        layout.addWidget(QLabel(self.tr("即将发送的内容（登录凭据已自动去除）：")))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.preview, 1)

        hint = QLabel(self.tr(
            "将以公开 issue 形式提交到 GitHub（{0}）。"
            "涉及内部接口时请先自行确认是否允许公开。"
        ).format(fb.GITHUB_REPO))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.mute_btn = QPushButton(self.tr("不再提示"))
        self.mute_btn.clicked.connect(self._on_mute)
        row.addWidget(self.mute_btn)
        row.addStretch(1)
        self.later_btn = QPushButton(self.tr("稍后再说"))
        self.later_btn.clicked.connect(self.reject)
        row.addWidget(self.later_btn)
        self.send_btn = QPushButton(self.tr("发送诊断报告"))
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self._on_send)
        row.addWidget(self.send_btn)
        layout.addLayout(row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

    def _refresh_preview(self) -> None:
        self.preview.setPlainText(self.build_body())

    def build_body(self) -> str:
        """按当前勾选状态组装正文（也是预览显示的内容）。"""
        return fb.build_crash_body(
            self.summary,
            fb.collect_diagnostics(),
            include_actions=self.actions_check.isChecked(),
            include_urls=self.urls_check.isChecked(),
        )

    def _show_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: #c0392b;" if error else "")
        self.status_label.setVisible(True)

    # ---------------------------------------------------------------- 提交

    def _on_send(self) -> None:
        if self._sending:
            return                       # 已在发送中，别重复提交
        self._sending = True
        self.send_btn.setEnabled(False)
        self._show_status(self.tr("正在提交…"))
        title = fb.crash_issue_title(self.summary)
        # 用 bug 标签：崩溃报告就是 bug，反馈通道那条 feedback 留给用户主动反馈
        data = fb.payload(title, self.build_body(), labels=["bug"])
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
        self._reply = self._nam.post(request, json.dumps(data).encode("utf-8"))
        self._reply.finished.connect(self._on_network_finished)

    def _on_network_finished(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
        self.finish_transport(
            int(status), bytes(reply.readAll()), reply.errorString() if not status else ""
        )
        reply.deleteLater()

    def finish_transport(self, status: int, raw: bytes = b"", err: str = "") -> None:
        """发送结果回流（真网络与测试注入共用）。"""
        self._sending = False
        ok, message, url = fb.parse_issue_response(status, raw, err)
        self._show_status(message + (f" {url}" if url else ""), error=not ok)
        if ok:
            self._clear_pending()
            self.accept()
        else:
            self.send_btn.setEnabled(True)

    # ---------------------------------------------------------------- 结局

    def _clear_pending(self) -> None:
        try:
            from app import crashreport

            crashreport.clear_pending_crash()
        except Exception:                # noqa: BLE001 - 上报成功已足够，清标记失败无碍
            pass

    def _on_mute(self) -> None:
        """不再提示：清掉这份摘要并通知调用方落盘偏好。"""
        self._clear_pending()
        self.mute_requested.emit()
        self.reject()

    def reject(self) -> None:  # noqa: D102 - 覆盖仅为标记已提示
        # 用户看过但没发（含「稍后再说」）：标记已提示，下次启动不再弹，
        # 摘要仍留着，可从菜单补发。
        try:
            from app import crashreport

            crashreport.mark_pending_prompted()
        except Exception:                # noqa: BLE001
            pass
        super().reject()
