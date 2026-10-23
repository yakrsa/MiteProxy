"""详情面板顶部的请求概览卡（一眼看清这条会话的关键事实）。

放在详情面板 tab 上方的一条紧凑横条：方法 pill + 状态码 pill + URL（等宽、省略），
下面一行小字给出耗时 / 大小 / 内容类型 / 服务端 IP。跟着选中流量刷新，
配色复用列表里的 method_color / status_color（深浅主题一致），主题切换时经
``theme.add_listener`` 重绘。

数据口径与流量列表、耗时分析对账行同源：耗时走 ``addons.capture.summarize``
（request_span_ms），避免和详情页耗时页各算各的、数字对不上。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.flow_store import status_color
from app.ui.visuals import badge_colors, method_color, mono_font


def _fmt_bytes(n: int) -> str:
    if n <= 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB")
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.0f} {u}" if u == "B" else f"{f:.1f} {u}"
        f /= 1024
    return f"{f:.1f} GB"


def _fmt_duration(ms: float) -> str:
    if ms <= 0:
        return "—"
    if ms < 1000:
        return f"{ms:.0f} ms"
    return f"{ms / 1000:.2f} s"


def _safe_summary(flow) -> dict:
    """取流量摘要；真实 flow 走 ``CaptureAddon.summarize`` 保证口径同源。

    详情面板测试里会用 ``SimpleNamespace`` 之类的轻量替身（缺 ``scheme`` 等
    字段），此时 summarize 会抛 AttributeError——UI 不该被展示逻辑带崩，
    所以退回一层 ``getattr`` 兜底，字段缺失就给空值。
    """
    try:
        from addons.capture import CaptureAddon

        return CaptureAddon.summarize(flow)
    except Exception:
        req = getattr(flow, "request", None)
        res = getattr(flow, "response", None)
        method = getattr(req, "method", "") if req is not None else ""
        host = getattr(req, "pretty_host", "") if req is not None else ""
        scheme = getattr(req, "scheme", "") if req is not None else ""
        path = getattr(req, "path", "") if req is not None else ""
        url = f"{scheme}://{host}{path}" if scheme or host else ""
        status = int(getattr(res, "status_code", 0) or 0) if res is not None else 0
        ctype = ""
        if res is not None:
            headers = getattr(res, "headers", None)
            if headers is not None:
                ctype = headers.get("content-type", "") or ""
        return {
            "method": method,
            "url": url,
            "status": status,
            "duration_ms": 0,
            "size": 0,
            "req_size": 0,
            "content_type": ctype,
            "server_ip": "",
        }


class OverviewCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._flow = None
        self._build_ui()
        theme.add_listener(self._retheme)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)

        # 第一行：方法 pill + 状态码 pill + 右侧留白（状态点等后续可放）
        top = QHBoxLayout()
        top.setSpacing(6)
        self.method_pill = QLabel("")
        self.method_pill.setObjectName("ov_method")
        self.method_pill.setVisible(False)
        self.status_pill = QLabel("")
        self.status_pill.setObjectName("ov_status")
        self.status_pill.setVisible(False)
        top.addWidget(self.method_pill)
        top.addWidget(self.status_pill)
        top.addStretch(1)
        root.addLayout(top)

        # URL（等宽、省略，长 URL 不撑爆卡片）
        self.url_label = QLabel("")
        self.url_label.setObjectName("ov_url")
        self.url_label.setFont(mono_font())
        self.url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.url_label.setWordWrap(False)
        root.addWidget(self.url_label)

        # 第二行：耗时 / 大小 / 内容类型 / 服务端 IP，小字灰标
        meta = QHBoxLayout()
        meta.setSpacing(14)
        self.duration_label = QLabel("")
        self.size_label = QLabel("")
        self.type_label = QLabel("")
        self.ip_label = QLabel("")
        for w in (self.duration_label, self.size_label, self.type_label, self.ip_label):
            w.setObjectName("ov_meta")
            w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            meta.addWidget(w)
        meta.addStretch(1)
        root.addLayout(meta)
        self._retheme()

    # ---------------------------------------------------------- 配色

    @staticmethod
    def _paint_pill(label: QLabel, text: str, color) -> None:
        """把 label 画成圆角 pill（color 为 None 时退化为纯文本，不画底色）。"""
        if not text:
            label.setVisible(False)
            return
        label.setVisible(True)
        label.setText(text)
        if color is None:
            label.setStyleSheet("QLabel{color: palette(text); border-radius:4px; padding:1px 6px;}")
            return
        bg, fg = badge_colors(color, False)
        rgba = f"rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()})"
        hex_fg = f"#{fg.red():02x}{fg.green():02x}{fg.blue():02x}"
        label.setStyleSheet(
            f"QLabel{{background:{rgba}; color:{hex_fg}; "
            f"border-radius:4px; padding:1px 6px; font-weight:600;}}"
        )

    def _retheme(self) -> None:
        """主题切换后重绘（概览卡配色都是运行时取的语义色）。"""
        if self._flow is not None:
            self.set_flow(self._flow)
        else:
            self.url_label.setStyleSheet("QLabel#ov_url{color: palette(text);}")
            meta_css = "QLabel#ov_meta{color: palette(mid); font-size:11px;}"
            for w in (self.duration_label, self.size_label, self.type_label, self.ip_label):
                w.setStyleSheet(meta_css)

    # ---------------------------------------------------------- 数据

    def set_flow(self, flow) -> None:
        self._flow = flow
        self.setVisible(True)
        s = _safe_summary(flow)
        self._paint_pill(self.method_pill, s.get("method") or "", method_color(s.get("method")))
        status = int(s.get("status") or 0)
        if status:
            reason = ""
            res = getattr(flow, "response", None)
            if res is not None:
                reason = f" {getattr(res, 'reason', '') or ''}".rstrip()
            self._paint_pill(
                self.status_pill, f"{status}{reason}", status_color(status)
            )
        else:
            self._paint_pill(self.status_pill, "", None)
            self.status_pill.setVisible(False)

        self.url_label.setText(s.get("url") or "")
        self.url_label.setToolTip(s.get("url") or "")
        self.url_label.setStyleSheet("QLabel#ov_url{color: palette(text);}")

        meta_css = "QLabel#ov_meta{color: palette(mid); font-size:11px;}"
        self.duration_label.setText(self.tr("耗时 {0}").format(_fmt_duration(s.get("duration_ms") or 0)))
        self.duration_label.setStyleSheet(meta_css)
        size = int(s.get("size") or 0)
        req_size = int(s.get("req_size") or 0)
        self.size_label.setText(
            self.tr("大小 {0}").format(_fmt_bytes(size))
            + (self.tr("（请求 {0}）").format(_fmt_bytes(req_size)) if req_size else "")
        )
        self.size_label.setStyleSheet(meta_css)
        ctype = (s.get("content_type") or "").split(";")[0].strip()
        self.type_label.setText(self.tr("类型 {0}").format(ctype or "—"))
        self.type_label.setStyleSheet(meta_css)
        self.ip_label.setText(self.tr("服务端 {0}").format(s.get("server_ip") or "—"))
        self.ip_label.setStyleSheet(meta_css)

    def clear(self) -> None:
        self._flow = None
        self.setVisible(False)
