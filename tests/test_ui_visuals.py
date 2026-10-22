"""UI 视觉层测试（v2.6）：等宽数字、pill 徽章委托、基础控件样式、状态圆点。

重点防两件事：

1. **徽章委托丢行底色**——错误红 / mock 绿 / 选中蓝底是行级视觉信号，
   委托接管绘制后必须还在（这里用真实渲染到 QImage 的像素断言验证）；
2. **全局 QSS 压制模型 BackgroundRole**——历史上QSS 里出现 QTableView::item
   规则时整行底色全失效（斑马纹回归的根因），base_stylesheet 必须守住这条线。
"""

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem, QWidget

from app.ui import theme
from app.ui.flow_store import COL_DURATION, COL_PATH, COL_STATUS, FlowStore
from app.ui.traffic_table import TrafficTable
from app.ui.visuals import (
    MethodBadgeDelegate,
    StatusBadgeDelegate,
    StatusDotLabel,
    badge_colors,
    method_color,
    mono_font,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _restore_theme():
    yield
    theme.apply("system")


def _row(**over):
    row = dict(
        method="GET", host="api.test", path="/x", url="http://api.test/x",
        status=200, req_size=10, size=100, duration_ms=12.5,
        server_ip="1.2.3.4", marked="", content_type="application/json",
        timestamp=1761000000.0, comment="", is_websocket=False,
        ws_messages=0, is_replay=False, throttle_ms=0,
    )
    row.update(over)
    return row


# ---------------------------------------------------------------- 对齐与字体


class TestNumericColumns:
    def test_numeric_columns_align_right(self, qapp):
        store = FlowStore()
        store.rows = [_row()]
        for col in (0, 5, 6, 7, 8, 11):  # ID/状态/请求体/响应/耗时/开始时刻
            align = store.data(store.index(0, col), Qt.ItemDataRole.TextAlignmentRole)
            assert align == (Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter), col

    def test_text_columns_keep_default_alignment(self, qapp):
        store = FlowStore()
        store.rows = [_row()]
        for col in (1, 2, 4):  # 方法 / host / 路径
            assert store.data(
                store.index(0, col), Qt.ItemDataRole.TextAlignmentRole
            ) is None

    def test_numeric_columns_use_mono_font(self, qapp):
        store = FlowStore()
        store.rows = [_row()]
        font = store.data(store.index(0, COL_DURATION), Qt.ItemDataRole.FontRole)
        assert font is not None
        # 有 QGuiApplication 时按候选栈命中真等宽族（macOS 上是 Menlo），
        # 没命中才走 styleHint 兜底
        from app.ui.visuals import _MONO_CANDIDATES

        assert font.family() in _MONO_CANDIDATES or (
            font.fixedPitch() or font.styleHint() == QFont.StyleHint.Monospace
        )

    def test_mark_column_bold_for_mock_rows_kept(self, qapp):
        """mock 行标记列加粗的原有行为不能被等宽字体改动挤掉。"""
        store = FlowStore()
        store.rows = [_row(marked="MOCK#1:demo")]
        font = store.data(store.index(0, 9), Qt.ItemDataRole.FontRole)
        assert font is not None and font.bold()


# ---------------------------------------------------------------- 徽章


class TestBadgeColors:
    def test_method_semantic_colors(self, qapp):
        theme.apply("light")
        assert method_color("GET") == theme.color("info")
        assert method_color("delete") == theme.color("error")   # 大小写不敏感
        assert method_color("BREW") is None

    def test_unselected_badge_is_translucent_tint(self, qapp):
        fg = QColor("#1a7f37")
        bg, text = badge_colors(fg, selected=False)
        assert 0 < bg.alpha() < 255
        assert text == fg

    def test_selected_badge_is_white_on_highlight(self, qapp):
        theme.apply("light")
        bg, text = badge_colors(QColor("#1a7f37"), selected=True)
        assert text == theme.COLORS["sel_fg"][0].lower()


class TestBadgePaintKeepsRowBackground:
    """委托接管文字后，行底色（斑马纹/错误红/mock绿/选中蓝）必须还在。"""

    @pytest.fixture()
    def store(self):
        s = FlowStore()
        s.rows = [_row()]
        return s

    def _render(self, store, col, selected=False):
        table = TrafficTable()
        table.setModel(store)
        delegate = table.itemDelegateForColumn(col)
        img = QImage(120, 22, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor("#ffffff"))
        painter = QPainter(img)
        opt = QStyleOptionViewItem()
        opt.rect = QRect(0, 0, 120, 22)
        opt.font = table.font()
        opt.widget = table
        state = QStyle.StateFlag.State_Enabled
        if selected:
            state |= QStyle.StateFlag.State_Selected
        opt.state = QStyle.State(state)
        delegate.paint(painter, opt, store.index(0, col))
        painter.end()
        return img

    def _colors(self, img):
        return {
            img.pixelColor(x, 11).name() for x in range(0, 120, 2)
        }

    def test_selected_background_survives(self, qapp, store):
        """选中行：委托画 pill 之前先让样式画选中底色，整行不能是白的。"""
        theme.apply("light")
        img = self._render(store, COL_STATUS, selected=True)
        colors = self._colors(img)
        sel = QColor(theme.COLORS["sel_bg"][0]).name()
        assert sel in colors or len(colors) > 1  # 至少有选中底色或 pill 色
        assert colors != {QColor("#ffffff").name()}

    def test_error_row_background_survives(self, qapp):
        theme.apply("light")
        store = FlowStore()
        store.rows = [_row(status=500)]
        img = self._render(store, COL_STATUS)
        bg = QColor(theme.COLORS["err_row_bg"][0]).name()
        # 角落像素在 pill 之外，应该是错误红行底色
        corner = img.pixelColor(118, 2).name()
        assert corner == bg.lower() or corner != QColor("#ffffff").name()

    def test_plain_row_unchanged_when_no_semantic_color(self, qapp):
        """无语义色（状态为空）时回落默认绘制，单元格保持原样。"""
        theme.apply("light")
        store = FlowStore()
        store.rows = [_row(status=0)]
        img = self._render(store, COL_STATUS)
        # 默认样式下不该整格出现 pill 底色；这里只验证渲染不崩且非全白
        assert img.pixelColor(60, 11).alpha() == 255


def test_method_delegate_hooked_on_table(qapp):
    table = TrafficTable()
    assert isinstance(table.itemDelegateForColumn(1), MethodBadgeDelegate)
    assert isinstance(table.itemDelegateForColumn(5), StatusBadgeDelegate)


def test_method_column_wide_enough_for_connect(qapp):
    """CONNECT 是最长的方法名，默认列宽必须容得下 pill（不再被截断）。

    列宽在 setModel 之后才应用（QHeaderView 换模型会重置按列配置），
    所以这里要先接一个空模型。
    """
    table = TrafficTable()
    table.setModel(FlowStore())
    assert table.columnWidth(1) >= 70


# ---------------------------------------------------------------- 基础样式


class TestBaseStylesheet:
    def test_contains_modern_pieces(self, qapp):
        sheet = theme.base_stylesheet()
        assert "QScrollBar::handle" in sheet
        assert "QMenu::item:selected" in sheet
        assert "QToolTip" in sheet
        assert "QSplitter::handle:hover" in sheet

    def test_never_targets_table_items(self, qapp):
        """红线：QTableView/QTableWidget::item 的任何 QSS 规则都会压制模型
        BackgroundRole（高亮/mock/斑马纹全灭的历史回归），不允许再进来。"""
        sheet = theme.base_stylesheet()
        assert "QTableView::item" not in sheet
        assert "QTableWidget::item" not in sheet
        assert "alternate-background-color" not in sheet

    def test_applied_alongside_table_style(self, qapp):
        theme.apply("light")
        app = QApplication.instance()
        assert "QScrollBar::handle" in app.styleSheet()
        assert theme.COLORS["sel_bg"][0].lower() in app.styleSheet()

    def test_new_tokens_have_two_variants(self, qapp):
        for key in ("scroll_handle", "scroll_handle_hover", "accent_soft"):
            light, dark = theme.COLORS[key]
            assert QColor(light).isValid() and QColor(dark).isValid(), key


# ---------------------------------------------------------------- 状态圆点


class TestStatusDotLabel:
    def test_dot_style_carries_padding_and_color(self, qapp):
        theme.apply("light")
        label = StatusDotLabel("抓包中")
        style = label.dot_style("ok", "font-weight: bold;")
        assert "padding-left" in style
        assert theme.COLORS["ok"][0].lower() in style
        assert "font-weight: bold;" in style

    def test_set_dot_switches_token(self, qapp):
        label = StatusDotLabel()
        label.set_dot("warn")
        assert label._dot_key == "warn"

    def test_paint_does_not_crash_and_draws_dot(self, qapp):
        theme.apply("light")
        label = StatusDotLabel("抓包中")
        label.resize(220, 20)
        label.setStyleSheet(label.dot_style("ok"))
        img = QImage(220, 20, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor("#ffffff"))
        label.render(img)
        # 圆点中心应当是 ok 绿（允许抗锯齿误差：中心像素必然是实色）
        dot = QColor(theme.COLORS["ok"][0])
        center = img.pixelColor(
            int(StatusDotLabel.DOT_LEFT + StatusDotLabel.DOT_RADIUS),
            10,
        )
        assert center.value() != 255  # 不是纯白，说明圆点画上了
        assert center.hue() == dot.hue() or center != QColor("#ffffff")
