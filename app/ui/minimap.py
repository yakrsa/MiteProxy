"""流量表右侧的状态码 minimap（快速定位异常请求）。

把当前过滤后可见的每一行画成一个色点，纵向铺在表格右边一条 10px 窄带上：
绿 2xx / 蓝 3xx / 橙 4xx / 红 5xx / 灰 未知。几千条流量里找那个 500，
比横向滚一遍高效得多。点击对应位置跳到该行并滚动到视野中。

实现要点：
- minimap 不进 traffic_splitter（splitter 的 sizes 逻辑只认「列表/详情」两项），
  而是作为 traffic page 横向布局里紧贴表格右侧的独立窄控件，上下布局时隐藏。
- 颜色直接复用 ``flow_store.status_color``，保证和表格里的状态 pill 一致。
- 重绘时机：模型行数变化 / 数据变化 / 表格纵向滚动，由主窗口统一 connect 触发。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from app.ui.flow_store import COL_STATUS, status_color


class StatusMinimap(QWidget):
    def __init__(self, table=None, proxy_model=None, parent=None):
        super().__init__(parent)
        self._table = table
        self._model = proxy_model
        self.setFixedWidth(10)
        self.setMouseTracking(True)
        self.setToolTip(self.tr("状态码分布：2xx 绿 / 3xx 蓝 / 4xx 橙 / 5xx 红。点击跳到对应请求"))

    #: lupdate 走不到的字符串用 tr 声明，运行时 QApplication.translate
    def tr(self, s: str) -> str:
        from PySide6.QtCore import QCoreApplication
        return QCoreApplication.translate("StatusMinimap", s)

    def set_targets(self, table, proxy_model) -> None:
        self._table = table
        self._model = proxy_model
        self.update()

    def _row_count(self) -> int:
        return self._model.rowCount() if self._model is not None else 0

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
        n = self._row_count()
        if n == 0:
            return
        h = self.height()
        w = self.width()

        # 当前可见行范围（视口指示），基于表格纵向滚动条
        if self._table is not None:
            sb = self._table.verticalScrollBar()
            vmax = max(sb.maximum(), 1)
            top = sb.value() / (vmax + sb.pageStep())
            page = sb.pageStep() / (vmax + sb.pageStep())
            p.fillRect(0, int(top * h), w, max(2, int(page * h)),
                       QColor(120, 120, 120, 90))

        dot = max(2, min(6, h // n))
        for r in range(n):
            idx = self._model.index(r, COL_STATUS)
            status = self._model.data(idx)
            color = status_color(status) if isinstance(status, int) else None
            if color is None:
                color = QColor(150, 150, 150)
            y = int((r + 0.5) * h / n) - dot // 2
            p.fillRect(1, y, w - 2, dot, color)

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        n = self._row_count()
        if n == 0 or self._table is None:
            return
        row = int(ev.position().y() / self.height() * n)
        row = max(0, min(n - 1, row))
        self._table.selectRow(row)
        self._table.scrollTo(self._model.index(row, 0))
