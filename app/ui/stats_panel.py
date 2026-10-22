"""统计/概览页（对齐 Fiddler Statistics）：总览卡片 + 域名 / 状态码 / 方法
分布 + 慢请求 Top N + 时间直方图。

职责边界（与网络模拟面板一致）：本页只负责「展示」，不抓数据也不改代理。
主窗口注入 ``flow_provider``（当前列表对应的会话快照），聚合逻辑全部在
``app/stats.py``——MCP 的 ``get_stats`` 工具用的是同一份代码，两边数字
永远对得上。

刷新由主窗口驱动：新流量防抖 500ms 重算、切到本页补一次、清除列表 /
加载会话 / 删除会话立即重算。别在本页里起定时器——面板不可见时算了也
没人看，纯浪费。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QT_TRANSLATE_NOOP, QCoreApplication, QRectF, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.stats import compute_stats
from app.ui.flow_store import format_size, status_color
from app.ui import theme

# 直方图绘制边距（左/右给轴标签留位置，底部给时间轴留位置）
_HIST_MARGIN_X = 8
_HIST_MARGIN_TOP = 6
_HIST_MARGIN_BOTTOM = 18
_HIST_MIN_HEIGHT = 150

PANEL_HINT = QT_TRANSLATE_NOOP(
    "StatsPanel",
    "统计范围 = 当前流量列表中的会话（删除过的行不计入），不受顶部过滤栏影响；\n"
    "耗时与「耗时」列同口径（含弱网延迟），尚未返回响应的会话其耗时会持续增长。\n"
    "双击慢请求可跳到流量列表对应行。",
)

#: 直方图悬停提示（静态方法里没有 self.tr，走 NOOP + 运行时 translate）
_TIP_BUCKET = QT_TRANSLATE_NOOP(
    "StatsPanel", "{0} – {1}  {2} 条 · 下载 {3}"
)


def _clock(iso: str) -> str:
    """ISO 串 → 只留时分秒（直方图轴标签用；跨天也不标日期，画不下）。"""
    if not iso:
        return ""
    return iso.split("T")[-1][:8]


def _fmt_ms(value) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


class _Histogram(QWidget):
    """时间直方图：每桶一根柱（高度 ∝ 请求数），悬停显示该桶的时间范围。

    purposely 不用 Qt Charts：就 48 根柱子，QPainter 几十行搞定，
    还少一个重依赖。空数据时画一句提示，不留一块意义不明的空白。

    柱位不缓存：每次 paintEvent 按当前尺寸现算——窗口缩放时柱子
    跟着走，不会留在旧的几何里（缓存 rect 的话 resize 后点击/悬停
    会错位）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(_HIST_MIN_HEIGHT)
        self.setMouseTracking(True)
        self._buckets: list[dict] = []
        self._max_count = 1
        self._left_label = ""
        self._right_label = ""
        self._empty_text = ""
        self._bar_color = theme.color("info")

    def set_data(self, buckets: list[dict], left_label: str, right_label: str,
                 empty_text: str) -> None:
        self._buckets = list(buckets or [])
        self._max_count = max((int(b.get("count") or 0) for b in self._buckets),
                              default=1) or 1
        self._left_label = left_label
        self._right_label = right_label
        self._empty_text = empty_text
        self.update()

    # ------------------------------------------------------------ 布局

    def _bars(self) -> list[tuple[QRectF, str]]:
        """按当前控件尺寸算每根柱的矩形与提示文案（paint/hover 共用）。"""
        if not self._buckets:
            return []
        area_w = max(1, self.width() - 2 * _HIST_MARGIN_X)
        area_h = max(1, self.height() - _HIST_MARGIN_TOP - _HIST_MARGIN_BOTTOM)
        slot = area_w / len(self._buckets)
        bar_w = max(1.0, slot * 0.72)      # 柱间留缝，密到 48 根也分得清
        bars = []
        for i, b in enumerate(self._buckets):
            count = int(b.get("count") or 0)
            h = area_h * (count / self._max_count)
            x = _HIST_MARGIN_X + i * slot + (slot - bar_w) / 2
            bars.append((
                QRectF(x, _HIST_MARGIN_TOP + area_h - h, bar_w, h),
                self._bucket_tip(b),
            ))
        return bars

    @staticmethod
    def _bucket_tip(bucket: dict) -> str:
        start = _clock(str(bucket.get("start") or ""))
        end = _clock(str(bucket.get("end") or ""))
        count = int(bucket.get("count") or 0)
        size = format_size(int(bucket.get("response_bytes") or 0))
        return QCoreApplication.translate(
            "StatsPanel", _TIP_BUCKET).format(start, end, count, size)

    # ------------------------------------------------------------ 绘制

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            hint = QColor(theme.color("hint"))
            bars = self._bars()
            if not bars:
                painter.setPen(hint)
                painter.drawText(
                    self.rect(), Qt.AlignmentFlag.AlignCenter, self._empty_text
                )
                return
            for rect, _tip in bars:
                # 0 条的桶也画一条贴地的细线，看得出「这里有时间片但没有请求」
                painter.fillRect(rect, self._bar_color)
            painter.setPen(hint)
            base_y = self.height() - _HIST_MARGIN_BOTTOM + 2
            painter.drawText(
                _HIST_MARGIN_X, base_y + 3, 90, 14,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._left_label,
            )
            painter.drawText(
                self.width() - _HIST_MARGIN_X - 90, base_y + 3, 90, 14,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._right_label,
            )
        finally:
            painter.end()

    # ------------------------------------------------------------ 悬停

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        for rect, tip in self._bars():
            if rect.contains(pos):
                # 即时提示（setToolTip 有悬停延迟，看分布时太钝）
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        QToolTip.hideText()

    def leaveEvent(self, event) -> None:
        QToolTip.hideText()

    def _retheme(self) -> None:
        self._bar_color = theme.color("info")
        self.update()


class StatsPanel(QWidget):
    """统计页本体。数据全部来自 ``flow_provider()`` + ``app.stats.compute_stats``。"""

    #: 双击慢请求行 → 主窗口跳到流量列表对应行（传 flow id）
    flow_activated = Signal(str)

    def __init__(self, flow_provider, parent=None):
        super().__init__(parent)
        self._flow_provider = flow_provider

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self._cards = self._build_cards()
        root.addLayout(self._cards["layout"])
        self.pending_hint = QLabel("")
        self.pending_hint.setWordWrap(True)
        self.pending_hint.setStyleSheet(f"color: {theme.css('warn')};")
        self.pending_hint.hide()
        root.addWidget(self.pending_hint)

        middle = QHBoxLayout()
        middle.setSpacing(8)
        middle.addWidget(self._build_hosts_box(), stretch=1)
        dist_col = QVBoxLayout()
        dist_col.setSpacing(8)
        dist_col.addWidget(self._build_status_box())
        dist_col.addWidget(self._build_method_box())
        middle.addLayout(dist_col)
        root.addLayout(middle, stretch=1)

        root.addWidget(self._build_slow_box(), stretch=1)
        self.histogram_box, self.histogram = self._build_timeline_box()
        root.addWidget(self.histogram_box)

        hint = QLabel(QCoreApplication.translate("StatsPanel", PANEL_HINT))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.css('hint')};")
        root.addWidget(hint)
        self._hint_labels = [hint]

        theme.add_listener(self._retheme)
        self.refresh()

    # ------------------------------------------------------------ 构建

    def _build_cards(self) -> dict:
        """顶部总览卡片：六个数字一眼看完「整体怎么样」。"""
        layout = QHBoxLayout()
        layout.setSpacing(8)
        cards = {}
        for key, title in (
            ("total", self.tr("总会话")),
            ("error_rate", self.tr("错误率")),
            ("avg", self.tr("平均耗时")),
            ("p95", self.tr("P95 耗时")),
            ("download", self.tr("下载总量")),
            ("rate", self.tr("请求速率")),
        ):
            box = QGroupBox(title)
            inner = QVBoxLayout(box)
            inner.setContentsMargins(8, 4, 8, 6)
            inner.setSpacing(0)
            value = QLabel("—")
            value.setStyleSheet("font-size: 16pt; font-weight: bold;")
            value.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            sub = QLabel("")
            sub.setStyleSheet(f"color: {theme.css('hint')};")
            sub.setWordWrap(True)
            inner.addWidget(value)
            inner.addWidget(sub)
            layout.addWidget(box)
            cards[key] = (value, sub)
        return {"layout": layout, "cards": cards}

    def _build_hosts_box(self) -> QGroupBox:
        box = QGroupBox(self.tr("按域名（请求数排序）"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        self.hosts_table = self._make_table(
            [self.tr("域名"), self.tr("请求数"), self.tr("错误"),
             self.tr("错误率"), self.tr("平均耗时"), self.tr("最大耗时"),
             self.tr("下载")]
        )
        self.hosts_table.setToolTip(
            self.tr("耗时单位 ms；「下载」为该域名的响应体总量。\n"
                    "只显示前 {0} 个域名（按请求数降序）。").format(50)
        )
        layout.addWidget(self.hosts_table)
        return box

    def _build_status_box(self) -> QGroupBox:
        box = QGroupBox(self.tr("按状态码（次数排序）"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        self.status_table = self._make_table(
            [self.tr("状态码"), self.tr("次数"), self.tr("占比")]
        )
        layout.addWidget(self.status_table)
        return box

    def _build_method_box(self) -> QGroupBox:
        box = QGroupBox(self.tr("按方法（次数排序）"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        self.method_table = self._make_table(
            [self.tr("方法"), self.tr("次数"), self.tr("占比")]
        )
        layout.addWidget(self.method_table)
        return box

    def _build_slow_box(self) -> QGroupBox:
        box = QGroupBox(self.tr("慢请求 Top N（双击跳到对应会话）"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        # URL 列（第 3 列）才是该拉伸的那列——耗时/方法/状态/大小都要按内容宽
        self.slow_table = self._make_table(
            [self.tr("耗时(ms)"), self.tr("方法"), self.tr("状态"),
             self.tr("URL"), self.tr("大小")],
            stretch_col=3,
        )
        self.slow_table.doubleClicked.connect(self._on_slow_double_clicked)
        layout.addWidget(self.slow_table)
        return box

    def _build_timeline_box(self) -> tuple[QGroupBox, _Histogram]:
        box = QGroupBox(self.tr("时间分布（按请求开始时间分桶）"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        hist = _Histogram(box)
        layout.addWidget(hist)
        return box, hist

    def _make_table(self, headers: list[str], stretch_col: int = 0) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setAlternatingRowColors(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(
            stretch_col, QHeaderView.ResizeMode.Stretch
        )
        for col in range(len(headers)):
            if col != stretch_col:
                header.setSectionResizeMode(
                    col, QHeaderView.ResizeMode.ResizeToContents
                )
        return table

    # ------------------------------------------------------------ 刷新

    def refresh(self) -> None:
        """重新聚合并刷新全部区块（主窗口在新流量/清空/加载会话时调用）。"""
        try:
            flows = list(self._flow_provider())
        except Exception:
            flows = []
        self._show(compute_stats(flows))

    def _show(self, stats: dict) -> None:
        total = int(stats.get("total") or 0)
        errors = int(stats.get("errors") or 0)
        pending = int(stats.get("pending") or 0)
        span = float((stats.get("timeline") or {}).get("span_seconds") or 0)

        cards = self._cards["cards"]
        self._card(cards["total"], str(total),
                   self.tr("WebSocket {0} · 重放 {1}").format(
                       stats.get("websockets", 0), stats.get("replays", 0)))
        if total:
            self._card(cards["error_rate"],
                       f"{float(stats.get('error_rate') or 0) * 100:.1f}%",
                       self.tr("{0} / {1} 条（4xx/5xx）").format(errors, total))
        else:
            self._card(cards["error_rate"], "—", self.tr("暂无会话"))
        avg = _fmt_ms(stats.get("avg_duration_ms"))
        self._card(cards["avg"], f"{avg} ms",
                   self.tr("最大 {0} ms").format(_fmt_ms(stats.get("max_duration_ms"))))
        self._card(cards["p95"], f"{_fmt_ms(stats.get('p95_duration_ms'))} ms",
                   self.tr("95% 的请求快于此线"))
        self._card(cards["download"], format_size(int(stats.get("response_bytes") or 0)),
                   self.tr("上传 {0}").format(
                       format_size(int(stats.get("request_bytes") or 0))))
        if span > 0 and total:
            self._card(cards["rate"],
                       self.tr("{0} 条/秒").format(f"{total / span:.1f}"),
                       self.tr("时间跨度 {0} 秒").format(f"{span:.1f}"))
        else:
            self._card(cards["rate"], "—", self.tr("时间跨度 {0} 秒").format(f"{span:.1f}"))

        if pending > 0:
            self.pending_hint.setText(self.tr(
                "{0} 条会话尚未返回响应，其耗时与大小会持续增长。").format(pending))
            self.pending_hint.show()
        else:
            self.pending_hint.hide()

        self._fill_hosts(stats.get("hosts") or [], total)
        self._fill_status(stats.get("statuses") or [], total)
        self._fill_method(stats.get("methods") or [], total)
        self._fill_slow(stats.get("slow_requests") or [])
        self._fill_timeline(stats.get("timeline") or {})

    def _card(self, pair, value: str, sub: str) -> None:
        value_label, sub_label = pair
        value_label.setText(value)
        sub_label.setText(sub)

    # ------------------------------------------------------------ 各区块

    def _fill_hosts(self, rows: list[dict], total: int) -> None:
        table = self.hosts_table
        table.setRowCount(0)
        for r in rows:
            row = table.rowCount()
            table.insertRow(row)
            rate = float(r.get("error_rate") or 0)
            cells = [
                str(r.get("host") or ""),
                str(int(r.get("count") or 0)),
                str(int(r.get("errors") or 0)),
                f"{rate * 100:.1f}%",
                _fmt_ms(r.get("avg_duration_ms")),
                _fmt_ms(r.get("max_duration_ms")),
                format_size(int(r.get("response_bytes") or 0)),
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                table.setItem(row, col, item)
            if int(r.get("errors") or 0) > 0:
                # 错误数标红：域名表一眼看出「谁在报错」
                err_item = table.item(row, 2)
                if err_item is not None:
                    err_item.setForeground(theme.color("error"))

    def _fill_status(self, rows: list[dict], total: int) -> None:
        table = self.status_table
        table.setRowCount(0)
        for r in rows:
            status = int(r.get("status") or 0)
            count = int(r.get("count") or 0)
            row = table.rowCount()
            table.insertRow(row)
            label = self.tr("无响应") if status == 0 else str(status)
            item = QTableWidgetItem(label)
            color = status_color(status)
            if color is not None:
                item.setForeground(color)
            table.setItem(row, 0, item)
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, 1, count_item)
            pct = QTableWidgetItem(
                f"{count / total * 100:.1f}%" if total else "—"
            )
            pct.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, 2, pct)

    def _fill_method(self, rows: list[dict], total: int) -> None:
        table = self.method_table
        table.setRowCount(0)
        for r in rows:
            count = int(r.get("count") or 0)
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(str(r.get("method") or "")))
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, 1, count_item)
            pct = QTableWidgetItem(
                f"{count / total * 100:.1f}%" if total else "—"
            )
            pct.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, 2, pct)

    def _fill_slow(self, rows: list[dict]) -> None:
        table = self.slow_table
        table.setRowCount(0)
        for r in rows:
            row = table.rowCount()
            table.insertRow(row)
            status = int(r.get("status") or 0)
            url = str(r.get("url") or "")
            cells = [
                (_fmt_ms(r.get("duration_ms")), None),
                (str(r.get("method") or ""), None),
                (self.tr("无响应") if status == 0 else str(status),
                 status_color(status)),
                (url, None),
                (format_size(int(r.get("response_bytes") or 0)), None),
            ]
            for col, (text, color) in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (0, 2, 4):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if color is not None:
                    item.setForeground(color)
                # id 挂在 UserRole 上供双击跳转用（不显示、不参与任何排序）
                item.setData(Qt.ItemDataRole.UserRole, str(r.get("id") or ""))
                table.setItem(row, col, item)
            if url:
                table.item(row, 3).setToolTip(url)

    def _fill_timeline(self, timeline: dict) -> None:
        buckets = timeline.get("buckets") or []
        span = float(timeline.get("span_seconds") or 0)
        self.histogram_box.setTitle(self.tr(
            "时间分布（按请求开始时间分桶，跨度 {0} 秒）").format(f"{span:.1f}"))
        if buckets:
            left = _clock(str(buckets[0].get("start") or ""))
            right = _clock(str(buckets[-1].get("end") or ""))
        else:
            left = right = ""
        self.histogram.set_data(
            buckets, left, right, self.tr("暂无数据（开始抓包后自动统计）")
        )

    # ------------------------------------------------------------ 交互

    def _on_slow_double_clicked(self, index) -> None:
        item = self.slow_table.item(index.row(), 0)
        if item is None:
            return
        flow_id = item.data(Qt.ItemDataRole.UserRole) or ""
        if flow_id:
            self.flow_activated.emit(str(flow_id))

    def _retheme(self) -> None:
        for label in self._hint_labels:
            label.setStyleSheet(f"color: {theme.css('hint')};")
        self.pending_hint.setStyleSheet(f"color: {theme.css('warn')};")
        self.histogram._retheme()
