"""视觉构件：等宽数字字体、pill 徽章委托、状态圆点标签。

三者都是「同一套绘制细节在多处复用」的东西（列徽章要挂流量表，将来规则
表也能挂；状态点要给状态栏，将来别处也能用），塞进任何一个具体面板都不合
适，单开一个模块。

两条必须守住的规则：

1. **徽章委托不能丢行底色**。错误红 / mock 绿 / 黄高亮 / 斑马纹 / 选中蓝底
   都是行级的视觉信号，委托一旦自己整格重画就全没了。所以 `paint()` 先让
   样式画一遍背景（把 text 清空），只在上面叠一个 pill。
2. **pill 配色派生自语义色而不是再写一套 hex**。深浅两套值已经在 theme 里
   定过了，这里改成同色相的低透明度底 + 原色文字，主题切换自动跟着变。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
)

from app.ui import theme

# 等宽字体候选栈：macOS / Windows / Linux 各挑装机率最高的，Qt 的 "Monospace"
# 兜底在部分平台上会退化成比例字体，再用 StyleHint 补一层。
_MONO_CANDIDATES = (
    "SF Mono", "Menlo", "Monaco",
    "Cascadia Mono", "Consolas",
    "JetBrains Mono", "DejaVu Sans Mono",
)

#: 按 point size 缓存，避免每格都跑一遍字体族扫描
_mono_cache: dict[int, QFont] = {}

#: pill 左右内边距 / 最小宽度 / 高度（22px 行高里的舒适尺寸）
PILL_PAD_X = 6
PILL_MIN_WIDTH = 30
PILL_HEIGHT = 15


def mono_font(point_size: int | None = None) -> QFont:
    """跨平台等宽字体：数值列能逐位比对的关键。

    返回的是**副本**——调用方自己 setBold/setPointSize 不会污染下一个格子。
    `point_size=None` 表示沿用控件字号。
    """
    key = point_size or 0
    cached = _mono_cache.get(key)
    if cached is not None:
        return QFont(cached)

    family = ""
    # QFontDatabase.families() 要 QGuiApplication 已存在；没起来时走 styleHint 兜底
    if QApplication.instance() is not None:
        families = set(QFontDatabase.families())
        family = next((c for c in _MONO_CANDIDATES if c in families), "")
    font = QFont(family)
    if not family:
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
    if point_size:
        font.setPointSize(point_size)
    _mono_cache[key] = font
    return QFont(font)


# ---------------------------------------------------------------- 语义色

_METHOD_TOKENS = {
    "GET": "info",
    "POST": "ok",
    "PUT": "warn",
    "PATCH": "warn",
    "DELETE": "error",
    "HEAD": "hint",
    "OPTIONS": "hint",
    "CONNECT": "info",
    "TRACE": "hint",
}


def method_color(method: str) -> QColor | None:
    """HTTP 方法的语义色；未知方法返回 None（交给默认绘制，不画 pill）。"""
    token = _METHOD_TOKENS.get((method or "").strip().upper())
    return theme.color(token) if token else None


def badge_colors(fg: QColor, selected: bool) -> tuple[QColor, QColor]:
    """pill 的 (底色, 文字色)：语义色的低透明度底 + 语义色原文。

    选中行是蓝底（深浅下都是饱和蓝），语义色文字对比度撑不住，改成「白色
    半透明底 + 选中前景色（恒白）」——与蓝底同色系，不会显脏。
    """
    if selected:
        return QColor(255, 255, 255, 64), theme.color("sel_fg")
    bg = QColor(fg)
    bg.setAlpha(46 if theme.is_dark_app() else 34)
    return bg, fg


# ---------------------------------------------------------------- 徽章委托


class BadgeDelegate(QStyledItemDelegate):
    """把某个列画成圆角 pill（方法 / 状态码）。

    `color_of` 是 index → QColor | None 的取值函数；返回 None（未知方法、
    无状态码）时整体回落默认绘制——没有语义信息就别给装饰。
    """

    def __init__(self, color_of, parent=None):
        super().__init__(parent)
        self._color_of = color_of

    def _text(self, index) -> str:
        value = index.data(Qt.ItemDataRole.DisplayRole)
        return "" if value is None else str(value)

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        fg = self._color_of(index)
        text = self._text(index)
        if fg is None or not text or text == "-":
            super().paint(painter, option, index)
            return

        # 1) 背景仍交给样式：选中蓝底 / 错误红行 / mock 绿行 / 斑马纹全靠它
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""                      # 只画背景与焦点框，文字自己来
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, opt, painter, option.widget
        )

        # 2) 在保留的底色上叠 pill
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        bg, text_color = badge_colors(fg, selected)
        font = QFont(option.font)
        width = min(
            max(QFontMetrics(font).horizontalAdvance(text) + PILL_PAD_X * 2,
                PILL_MIN_WIDTH),
            max(option.rect.width() - 4, 0),
        )
        height = min(option.rect.height() - 3, PILL_HEIGHT)
        rect = QRectF(option.rect)
        rect.setWidth(width)
        rect.setHeight(height)
        rect.moveCenter(QRectF(option.rect).center())

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QPen(text_color))
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        base = super().sizeHint(option, index)
        text = self._text(index)
        if not text or text == "-":
            return base
        font = QFont(option.font)
        width = max(
            QFontMetrics(font).horizontalAdvance(text) + PILL_PAD_X * 2 + 4,
            base.width(),
        )
        return QSize(width, base.height())


class StatusBadgeDelegate(BadgeDelegate):
    """状态码徽章：2xx 绿 / 3xx 蓝 / 4xx 橙 / 5xx 红（配色复用 status_color）。"""

    def __init__(self, parent=None):
        from app.ui.flow_store import status_color

        def color_of(index) -> QColor | None:
            try:
                return status_color(int(index.data(Qt.ItemDataRole.DisplayRole)))
            except (TypeError, ValueError):
                return None

        super().__init__(color_of, parent)


class MethodBadgeDelegate(BadgeDelegate):
    """方法徽章：GET 蓝 / POST 绿 / PUT·PATCH 橙 / DELETE 红 / 其余灰。"""

    def __init__(self, parent=None):
        def color_of(index) -> QColor | None:
            return method_color(self._text(index))

        super().__init__(color_of, parent)


# ---------------------------------------------------------------- 状态圆点


class StatusDotLabel(QLabel):
    """状态栏用的「圆点 + 文字」标签。

    之前直接在文案里写 `● 抓包中`——U+25CF 的渲染完全取决于当前字体，
    中文字体里是居中偏下的实心圆，英文字体里可能变方块或空白，还会跟着
    font-weight 一起抖。改成 QPainter 画，跨平台、跨字体口径一致。

    文字让位靠 styleSheet 的 padding-left（由 `dot_style()` 拼），不在这里
    改 QLabel 的边距，避免和调用方自己设的样式表打架。
    """

    DOT_RADIUS = 3.5
    #: 圆点左边距：与 padding-left 一起定（“点”和“字”之间的呼吸)
    DOT_LEFT = 6

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._dot_key = "hint"

    def set_dot(self, key: str) -> None:
        """设置圆点语义色 token（hint / ok / warn / error …）。"""
        self._dot_key = key

    def dot_style(self, key: str, extra: str = "") -> str:
        """拼一份给自己的样式表：圆点颜色 + 让位 + 可选附加。"""
        return (
            f"padding-left: {int(self.DOT_LEFT + self.DOT_RADIUS * 2 + 5)}px; "
            f"color: {theme.css(key)};{extra}"
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(theme.color(self._dot_key)))
        size = self.DOT_RADIUS * 2
        painter.drawEllipse(
            QRectF(self.DOT_LEFT, self.height() / 2 - self.DOT_RADIUS, size, size)
        )
        painter.end()
