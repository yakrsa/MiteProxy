"""重放对比对话框（对齐 Fiddler 的 Compare 窗口，DESIGN.md 3.6）。

左边原响应、右边重放后的新响应，底部差异报告：
- 两边 body 都能解析成 JSON → **键级结构化 diff**（app/jsondiff.py），
  整个 JSON 重排也不会全行飘红；
- 否则 → **行级文本 diff**（difflib，app/textutil.unified_diff）；
- 二进制且解码失败 → 只报"相同/不同"，不硬渲染乱码。

非模态：对比窗口开着不影响继续看流量列表（Fiddler 也是这样）。
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.jsondiff import diff_json, format_diff_report
from app.jsonutil import parse_json
from app.textutil import decode_body, unified_diff
from app.ui.detail_panel import MessagePane, truncation_flags

log = logging.getLogger(__name__)

#: 报告区最大行数：diff 可能几千行，全渲染会卡
REPORT_MAX_LINES = 2000


def _response_of(flow):
    return getattr(flow, "response", None)


def _request_of(flow):
    return getattr(flow, "request", None)


def _safe_content(message) -> bytes:
    if message is None:
        return b""
    try:
        return message.get_content(strict=False) or b""
    except Exception:
        return b""


def _safe_raw_len(message) -> int:
    if message is None:
        return 0
    try:
        return len(message.raw_content or b"")
    except Exception:
        return 0


def _content_type(message) -> str:
    if message is None:
        return ""
    try:
        return message.headers.get("content-type", "") or ""
    except Exception:
        return ""


def _headers_items(message) -> list[tuple[str, str]]:
    if message is None:
        return []
    try:
        return [(str(k), str(v)) for k, v in message.headers.items(multi=True)]
    except TypeError:
        return [(str(k), str(v)) for k, v in message.headers.items()]
    except Exception:
        return []


def diff_headers(
    old_items: list[tuple[str, str]], new_items: list[tuple[str, str]]
) -> list[str]:
    """响应 headers 差异报告行。同名多值按多重集合比较。"""
    old_map: dict[str, list[str]] = {}
    for k, v in old_items:
        old_map.setdefault(k, []).append(v)
    new_map: dict[str, list[str]] = {}
    for k, v in new_items:
        new_map.setdefault(k, []).append(v)

    lines: list[str] = []
    for key in new_map:
        if key not in old_map:
            for v in new_map[key]:
                lines.append(f"+ {key}: {v}")
    for key in old_map:
        if key not in new_map:
            for v in old_map[key]:
                lines.append(f"- {key}: {v}")
        elif sorted(old_map[key]) != sorted(new_map[key]):
            lines.append(f"~ {key}: {' | '.join(old_map[key])} → {' | '.join(new_map[key])}")
    return lines


class CompareDialog(QDialog):
    """原 flow vs 重放新 flow 的响应对比。非模态，可一直开着。"""

    def __init__(self, original_flow, new_flow, parent=None, wrap_default: bool = True):
        super().__init__(parent)
        self.setWindowTitle(self.tr("重放对比"))
        self.resize(1120, 760)
        self._original_flow = original_flow
        self._new_flow = new_flow
        self._report_text = ""

        self._build_ui(wrap_default)
        self._fill()

    # ------------------------------------------------------------ UI

    def _build_ui(self, wrap_default: bool) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.summary_label = QLabel("")
        self.summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.old_pane = MessagePane(wrap_default=wrap_default)
        self.new_pane = MessagePane(wrap_default=wrap_default)
        for pane, title in ((self.old_pane, self.tr("原响应")), (self.new_pane, self.tr("新响应"))):
            box = QWidget()
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(0, 0, 0, 0)
            box_layout.setSpacing(2)
            box_layout.addWidget(QLabel(f"<b>{title}</b>"))
            box_layout.addWidget(pane)
            splitter.addWidget(box)
        splitter.setSizes([520, 520])
        layout.addWidget(splitter, stretch=3)

        report_label = QLabel(self.tr("<b>差异报告</b>"))
        layout.addWidget(report_label)
        self.report_edit = QPlainTextEdit()
        self.report_edit.setReadOnly(True)
        self.report_edit.setMaximumBlockCount(REPORT_MAX_LINES)
        font = QFont("Menlo")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.report_edit.setFont(font)
        layout.addWidget(self.report_edit, stretch=2)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        copy_btn = QPushButton(self.tr("复制差异"))
        copy_btn.clicked.connect(self._copy_report)
        close_btn = QPushButton(self.tr("关闭"))
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------ 填充

    def _fill(self) -> None:
        req_old = _request_of(self._original_flow)
        req_new = _request_of(self._new_flow)
        url = ""
        for req in (req_new, req_old):
            if req is not None:
                url = getattr(req, "pretty_url", "") or ""
                break

        old_res = _response_of(self._original_flow)
        new_res = _response_of(self._new_flow)
        self._fill_pane(self.old_pane, old_res, req_old, self._original_flow)
        self._fill_pane(self.new_pane, new_res, req_new, self._new_flow)

        verdict, report = self._build_report(old_res, new_res)
        self._report_text = report
        self.report_edit.setPlainText(report or self.tr("（无差异）"))

        def _desc(res, message) -> str:
            if res is not None:
                return f"{res.status_code} · {_safe_raw_len(res)} B"
            if message is not None:
                return self.tr("无响应（{0}）").format(
                    getattr(message, "error", "") or self.tr("未知原因")
                )
            return QCoreApplication.translate("CompareDialog", "无响应")

        old_desc = _desc(old_res, self._original_flow)
        new_desc = _desc(new_res, self._new_flow)
        self.summary_label.setText(
            self.tr('{0}\n原响应：{1}\u3000→\u3000新响应：{2}\u3000·\u3000{3}').format(url, old_desc, new_desc, verdict)
        )

    def _fill_pane(self, pane: MessagePane, res, req, flow=None) -> None:
        # 原始 flow 可能来自被截断的会话快照：把截断事实一并交给 body 视图
        truncated_sides, truncated_sizes = truncation_flags(flow)
        if res is not None:
            pane.show_message(
                f"HTTP {res.status_code} {getattr(res, 'reason', '') or ''}".strip(),
                res.headers,
                _safe_content(res),
                _safe_raw_len(res),
                "response" in truncated_sides,
                truncated_sizes.get("response"),
            )
            return
        # 没有响应：退而展示请求，至少能看到重放发出去的内容
        if req is not None:
            pane.show_message(
                self.tr("{0} {1}（无响应）").format(
                    getattr(req, "method", ""), getattr(req, "pretty_url", "")
                ),
                req.headers,
                _safe_content(req),
                _safe_raw_len(req),
                "request" in truncated_sides,
                truncated_sizes.get("request"),
            )
            return
        pane.clear()

    # ------------------------------------------------------------ 差异

    def _build_report(self, old_res, new_res) -> tuple[str, str]:
        """返回 (判定, 报告文本)。"""
        old_bytes = _safe_content(old_res)
        new_bytes = _safe_content(new_res)

        if old_bytes == new_bytes:
            header_lines = diff_headers(
                _headers_items(old_res), _headers_items(new_res)
            )
            if header_lines:
                return (
                    self.tr("body 一致，headers 有差异"),
                    self.tr("Headers 差异：\n") + "\n".join(header_lines),
                )
            return (self.tr("完全一致"), self.tr("两个响应完全一致（body 与 headers 均相同）"))

        # body 不同：先试 JSON 结构化 diff
        old_ct = _content_type(old_res)
        new_ct = _content_type(new_res)
        old_parsed = parse_json(
            old_bytes.decode("utf-8", errors="replace"), strict=False
        )
        new_parsed = parse_json(
            new_bytes.decode("utf-8", errors="replace"), strict=False
        )
        if old_parsed.ok and new_parsed.ok:
            result = diff_json(old_parsed.value, new_parsed.value)
            report = format_diff_report(result)
            header_lines = diff_headers(
                _headers_items(old_res), _headers_items(new_res)
            )
            if header_lines:
                report += self.tr("\n\nHeaders 差异：\n") + "\n".join(header_lines)
            verdict = (
                self.tr('{0} 处差异（JSON 键级）').format(result.count)
                if not result.truncated
                else self.tr("差异过多（JSON 键级，已截断）")
            )
            return (verdict, report)

        # 文本 diff
        old_text = decode_body(old_bytes, old_ct)
        new_text = decode_body(new_bytes, new_ct)
        if old_text is None or new_text is None:
            return (self.tr("二进制内容不同"), self.tr("响应为二进制内容且无法按文本解码，仅确认两者不同。"))
        diff = unified_diff(old_text, new_text)
        verdict = self.tr("文本有差异") if diff else self.tr("解码后一致（原始字节不同，可能是换行/编码差异）")
        return (verdict, diff or self.tr("（无行级差异）"))

    # ------------------------------------------------------------ 复制

    def _copy_report(self) -> None:
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._report_text)

    @property
    def report_text(self) -> str:
        return self._report_text
