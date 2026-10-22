"""两条会话对比对话框（路线图 #5：选中两条会话比差异）。

与「重放并对比」（CompareDialog）的分工：
- CompareDialog 比的是**同一条会话改前/改后**（重放副本 vs 原 flow）；
- 本对话框比的是**任意两条独立会话**——典型场景「线上域名 vs 测试域名
  同一个接口的返回差在哪」「两次请求的 headers 哪里不一样」。

对比覆盖整条报文而不只是响应：
- 请求行（方法 / URL / HTTP 版本）+ 请求 headers；
- 响应状态行 + 响应 headers；
- body：两边都能解析成 JSON → 键级结构化 diff（app/jsondiff.py），
  否则行级文本 diff（app/textutil.unified_diff），二进制只报相同/不同。

非模态：开着不影响继续看流量列表（与 CompareDialog 一致）。
"""

from __future__ import annotations

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
from app.ui.compare_dialog import (
    _content_type,
    _headers_items,
    _request_of,
    _response_of,
    _safe_content,
    _safe_raw_len,
    diff_headers,
)
from app.ui.detail_panel import MessagePane, truncation_flags

#: 报告区最大行数：diff 可能几千行，全渲染会卡
REPORT_MAX_LINES = 2000


def _http_version(msg) -> str:
    try:
        return str(getattr(msg, "http_version", "") or "")
    except Exception:
        return ""


class FlowDiffDialog(QDialog):
    """flow_a（左）vs flow_b（右）的全报文对比。非模态，可一直开着。"""

    def __init__(self, flow_a, flow_b, parent=None, wrap_default: bool = True):
        super().__init__(parent)
        self.setWindowTitle(self.tr("会话对比"))
        self.resize(1120, 780)
        self._flow_a = flow_a
        self._flow_b = flow_b
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
        self.pane_a = MessagePane(wrap_default=wrap_default)
        self.pane_b = MessagePane(wrap_default=wrap_default)
        for pane, flow, title in (
            (self.pane_a, self._flow_a, self.tr("会话 A")),
            (self.pane_b, self._flow_b, self.tr("会话 B")),
        ):
            box = QWidget()
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(0, 0, 0, 0)
            box_layout.setSpacing(2)
            box_layout.addWidget(QLabel(f"<b>{title}</b>"))
            box_layout.addWidget(pane)
            splitter.addWidget(box)
        splitter.setSizes([520, 520])
        layout.addWidget(splitter, stretch=3)

        layout.addWidget(QLabel(self.tr("<b>差异报告</b>")))
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
        # 有响应的会话展示响应（排查返回差异是主场景）；没有响应的退化展示请求，
        # 至少能看到发出去的内容
        for pane, flow in ((self.pane_a, self._flow_a), (self.pane_b, self._flow_b)):
            self._fill_pane(pane, flow)

        verdict, report = self._build_report()
        self._report_text = report
        self.report_edit.setPlainText(report or self.tr("（无差异）"))

        self.summary_label.setText(
            self.tr("{0}\n会话 A：{1}\u3000→\u3000会话 B：{2}\u3000·\u3000{3}").format(
                self._flow_url(self._flow_a) or self.tr("（无 URL）"),
                self._flow_desc(self._flow_a),
                self._flow_desc(self._flow_b),
                verdict,
            )
        )

    def _fill_pane(self, pane: MessagePane, flow) -> None:
        # 原始 flow 可能来自被截断的会话快照：把截断事实一并交给 body 视图
        truncated_sides, truncated_sizes = truncation_flags(flow)
        res = _response_of(flow)
        req = _request_of(flow)
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

    @staticmethod
    def _flow_url(flow) -> str:
        req = _request_of(flow)
        if req is None:
            return ""
        return getattr(req, "pretty_url", "") or ""

    def _flow_desc(self, flow) -> str:
        res = _response_of(flow)
        if res is not None:
            return f"{res.status_code} · {_safe_raw_len(res)} B"
        req = _request_of(flow)
        if req is not None:
            return self.tr("无响应")
        return QCoreApplication.translate("FlowDiffDialog", "空会话")

    # ------------------------------------------------------------ 差异

    def _build_report(self) -> tuple[str, str]:
        """返回 (判定, 报告文本)。请求 + 响应全报文。"""
        lines: list[str] = []
        req_a, req_b = _request_of(self._flow_a), _request_of(self._flow_b)
        res_a, res_b = _response_of(self._flow_a), _response_of(self._flow_b)

        # ---- 请求行（方法 / URL / 版本）
        if req_a is not None and req_b is not None:
            if (getattr(req_a, "method", ""), self._flow_url(self._flow_a),
                    _http_version(req_a)) != (
                    getattr(req_b, "method", ""), self._flow_url(self._flow_b),
                    _http_version(req_b)):
                lines.append(self.tr("【请求行】"))
                if getattr(req_a, "method", "") != getattr(req_b, "method", ""):
                    lines.append(self.tr("  方法: {0} → {1}").format(
                        getattr(req_a, "method", ""), getattr(req_b, "method", "")
                    ))
                if self._flow_url(self._flow_a) != self._flow_url(self._flow_b):
                    lines.append(self.tr("  URL: {0}").format(self._flow_url(self._flow_a)))
                    lines.append(self.tr("    → {0}").format(self._flow_url(self._flow_b)))
                va, vb = _http_version(req_a), _http_version(req_b)
                if va != vb:
                    lines.append(self.tr("  HTTP 版本: {0} → {1}").format(
                        va or "-", vb or "-"))

        # ---- 请求 headers
        if req_a is not None and req_b is not None:
            req_header_lines = diff_headers(
                _headers_items(req_a), _headers_items(req_b)
            )
            if req_header_lines:
                lines.append(self.tr("【请求 Headers】"))
                lines.extend(f"  {line}" for line in req_header_lines)

        # ---- 响应状态行
        if res_a is not None and res_b is not None:
            if (res_a.status_code, getattr(res_a, "reason", "")) != (
                    res_b.status_code, getattr(res_b, "reason", "")):
                lines.append(self.tr("【响应状态行】"))
                lines.append(self.tr("  {0} {1} → {2} {3}").format(
                    res_a.status_code, getattr(res_a, "reason", "") or "",
                    res_b.status_code, getattr(res_b, "reason", "") or "",
                ))
        elif (res_a is None) != (res_b is None):
            lines.append(self.tr("【响应】"))
            lines.append(self.tr("  一边有响应、一边没有（A: {0}，B: {1}）").format(
                self.tr("有") if res_a is not None else self.tr("无"),
                self.tr("有") if res_b is not None else self.tr("无"),
            ))

        # ---- 响应 headers
        if res_a is not None and res_b is not None:
            res_header_lines = diff_headers(
                _headers_items(res_a), _headers_items(res_b)
            )
            if res_header_lines:
                lines.append(self.tr("【响应 Headers】"))
                lines.extend(f"  {line}" for line in res_header_lines)

        # ---- body
        body_verdict, body_report = self._diff_body(res_a, res_b)
        if body_report:
            lines.append(self.tr("【Body】"))
            lines.extend(f"  {line}" for line in body_report.splitlines())

        if not lines:
            return (self.tr("完全一致"), "")

        verdict_parts = []
        if req_a is not None and req_b is not None and (
                getattr(req_a, "method", "") != getattr(req_b, "method", "")
                or self._flow_url(self._flow_a) != self._flow_url(self._flow_b)):
            verdict_parts.append(self.tr("请求不同"))
        verdict_parts.append(body_verdict)
        verdict = self.tr("、").join(verdict_parts) if verdict_parts else self.tr("有差异")
        return (verdict, "\n".join(lines))

    def _diff_body(self, res_a, res_b) -> tuple[str, str]:
        """body 差异：JSON 键级优先，其次文本行级，二进制只报相同/不同。"""
        old_bytes = _safe_content(res_a)
        new_bytes = _safe_content(res_b)

        if old_bytes == new_bytes:
            if not old_bytes:
                return (self.tr("body 均为空"), "")
            return (self.tr("body 一致"), "")

        old_ct = _content_type(res_a)
        new_ct = _content_type(res_b)
        old_parsed = parse_json(
            old_bytes.decode("utf-8", errors="replace"), strict=False
        )
        new_parsed = parse_json(
            new_bytes.decode("utf-8", errors="replace"), strict=False
        )
        if old_parsed.ok and new_parsed.ok:
            result = diff_json(old_parsed.value, new_parsed.value)
            verdict = (
                self.tr('{0} 处差异（JSON 键级）').format(result.count)
                if not result.truncated
                else self.tr("差异过多（JSON 键级，已截断）")
            )
            return (verdict, format_diff_report(result))

        old_text = decode_body(old_bytes, old_ct)
        new_text = decode_body(new_bytes, new_ct)
        if old_text is None or new_text is None:
            return (self.tr("二进制内容不同"),
                    self.tr("响应为二进制内容且无法按文本解码，仅确认两者不同。"))
        diff = unified_diff(old_text, new_text)
        verdict = (
            self.tr("文本有差异") if diff
            else self.tr("解码后一致（原始字节不同，可能是换行/编码差异）")
        )
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
