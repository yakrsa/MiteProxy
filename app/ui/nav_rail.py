"""左侧导航栏（图标在上、文字在下的横排 rail，悬停展开 / 移走收起）。

为什么不用 QTabWidget 原生的 West 侧栏：Qt 的 QTabBar 在 West/East 形态下
把 tab 文字**无条件旋转 90°**（PySide6 6.12 没有暴露 setVerticalText 关掉它），
中文竖着躺已经难认，英文长词（Statistics / Mock Rules）直接糊成一团。
所以主窗口藏掉原生 tabBar，用这个自定义 rail 接管导航。

默认收起到「只留图标」（约 48px，给内容区让地方），鼠标移进 rail 就把
文字推出来，移走再收回去——既保留图标的常驻辨识度，又不长期占版面。
展开宽度按当前语言下最长的那个标签算（中英文都能撑开不截断）。

约定：
- 按钮固定尺寸、图标上文字下、选中态整块高亮——中英文都能横着读；
- 与 ``QTabWidget`` 通过 index 一一对应：``current_changed`` 由 rail 发出，
  ``set_current`` 由外部（currentChanged）驱动；
- 不持有业务对象，只认「图标名 + 文案」；选中按钮的图标换成高亮底色上的
  浅色变体，避免深色图标压在蓝底上看不清；
- 收起状态下文字被抠掉，靠 tooltip 兜底；键盘 Tab 聚焦到任意一枚按钮时
  也会展开（不然盲人操作看不到自己在哪页）。
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QToolButton,
    QVBoxLayout,
)

from app.ui import icons, theme

#: 单枚导航按钮的高度（图标 18 + 一行文字的留量）
BUTTON_HEIGHT = 54
#: 收起时 rail 宽度：图标居中，两侧留边距
COLLAPSED_WIDTH = 50
#: 底部「钉住」开关按钮的高度（比导航按钮矮，别抢它们的戏）
PIN_HEIGHT = 30
#: 展开宽度的下限 / 上限（按最长标签算完后夹到这里，别让它抖动）
MIN_LABEL_WIDTH = 84
MAX_LABEL_WIDTH = 152
#: 展开/收起动画时长（毫秒）
ANIM_MS = 150
#: 按住导航按钮拖出多少像素算「想把它拖成浮窗」而不是「想点一下切页」
DRAG_OUT_THRESHOLD = 24


class NavRail(QFrame):
    """图标在上、文字在下的竖排导航栏，鼠标悬停展开、移走收起。"""

    #: 用户点了某页（外部据此切 QTabWidget）
    current_changed = Signal(int)
    #: 用户切换了「钉住」（外部据此持久化偏好）
    pin_toggled = Signal(bool)
    #: 用户把某一页的导航按钮拖了出来（外部据此把该页变成独立浮窗）
    drag_out_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("navRail")
        # 布局的左右边距（按钮宽度要从 rail 宽度里扣掉它）
        self._margins = 12

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 8, 6, 8)
        self._layout.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.current_changed)
        self._buttons: list[QToolButton] = []
        self._labels: list[str] = []
        self._normal_icons: list[QIcon] = []
        self._selected_icons: list[QIcon] = []
        self._current = -1
        # ---- 拖出手势状态（按住按钮拖出阈值即发 drag_out_requested）
        self._drag_index = -1
        self._drag_start = QPoint()
        self._drag_fired = False

        # ---- 展开/收起状态机
        self._label_width = MIN_LABEL_WIDTH
        self._expanded = False   # 当前是否处于展开态
        self._pinned = False     # 钉住：不看鼠标，常驻展开
        self._hover = False      # 鼠标是否在 rail 上（含子控件）
        self._focus = False      # 键盘焦点是否在 rail 的某枚按钮上
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._build_pin_button()

        self.setFixedWidth(COLLAPSED_WIDTH)
        self._apply_style()
        theme.add_listener(self._retheme)

    # ------------------------------------------------------------ 构建

    def add_page(self, normal_icon: QIcon, selected_icon: QIcon, label: str) -> None:
        """加一页导航按钮（调用顺序必须与 QTabWidget.addTab 一致）。"""
        btn = QToolButton(self)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setIconSize(QSize(18, 18))
        btn.setFixedHeight(BUTTON_HEIGHT)
        btn.setFixedWidth(COLLAPSED_WIDTH - self._margins)
        btn.setText(label)
        btn.setIcon(normal_icon)
        btn.setCheckable(True)
        btn.setToolTip(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        # 键盘用户：聚焦到哪枚按钮就把 rail 展开，不然收起态只看得见图标
        btn.installEventFilter(self)
        self._layout.addWidget(btn)
        self._group.addButton(btn, len(self._buttons))
        self._buttons.append(btn)
        self._labels.append(label)
        self._normal_icons.append(normal_icon)
        self._selected_icons.append(selected_icon)
        if len(self._buttons) == 1:
            self._current = 0
            btn.setChecked(True)

    def _build_pin_button(self) -> None:
        """底部「钉住」开关：钉上后不再随鼠标收起，偏好由外部持久化。"""
        btn = QToolButton(self)
        btn.setObjectName("navPin")
        btn.setIcon(icons.icon("pin", 16))
        btn.setIconSize(QSize(16, 16))
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        btn.setFixedSize(COLLAPSED_WIDTH - self._margins, PIN_HEIGHT)
        btn.setToolTip(self.tr("钉住导航栏（保持展开）"))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.toggled.connect(self._on_pin_toggled)
        self._pin_btn = btn

    def finish(self) -> None:
        """按钮全部加完后调用：算展开宽度、吃掉剩余空间、挂上钉住开关。"""
        self._layout.addStretch(1)
        self._layout.addWidget(self._pin_btn)
        self._label_width = self._measure_label_width()
        self._apply_text(False)

    def set_shortcut_hints(self, hints) -> None:
        """给每枚按钮的 tooltip 追加快捷键提示。

        收起态全靠 tooltip 认路，顺手把 Ctrl+N 写在里面——不然用户不知道有这个
        快捷方式，等于白给。
        """
        for btn, label, hint in zip(self._buttons, self._labels, hints):
            btn.setToolTip(f"{label}（{hint}）" if hint else label)

    def set_icons(self, normal: list[QIcon], selected: list[QIcon]) -> None:
        """按 index 重设两套图标（主题切换后重新取色）。"""
        self._normal_icons = list(normal)
        self._selected_icons = list(selected)
        for i, btn in enumerate(self._buttons):
            if i >= len(selected) or i >= len(normal):
                continue
            btn.setIcon(selected[i] if i == self._current else normal[i])

    # ------------------------------------------------------------ 选中态

    def set_current(self, index: int) -> None:
        """程序化选中某页（外部 QTabWidget 的 currentChanged 驱动）。"""
        if not (0 <= index < len(self._buttons)) or index == self._current:
            return
        if 0 <= self._current < len(self._buttons):
            self._buttons[self._current].setIcon(
                self._normal_icons[self._current]
            )
        self._current = index
        btn = self._buttons[index]
        if index < len(self._selected_icons):
            btn.setIcon(self._selected_icons[index])
        btn.setChecked(True)

    # ------------------------------------------------------------ 展开 / 收起

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        """展开 / 收起；重复设置同状态直接返回（动画也一样不重启动）。"""
        expanded = bool(expanded)
        if expanded == self._expanded:
            return
        self._expanded = expanded
        target = self.expanded_width() if expanded else COLLAPSED_WIDTH
        if not animate:
            self._anim.stop()
            self._on_anim_value(target)
            self._apply_text(expanded)
            return
        # 展开时先把文字装回去（渐入时才能一点点露出），收起动画结束再抠掉
        if expanded:
            self._apply_text(True)
        self._anim.stop()
        self._anim.setStartValue(self.width())
        self._anim.setEndValue(target)
        self._anim.start()

    def expanded_width(self) -> int:
        return self._label_width + self._margins

    # ------------------------------------------------------------ 钉住

    def is_pinned(self) -> bool:
        return self._pinned

    def set_pinned(self, pinned: bool, emit: bool = True,
                   animate: bool = True) -> None:
        """钉住 / 取消钉住。

        ``emit=False`` 用于启动时恢复偏好——那是「还原上次的界面」而不是
        「用户刚切换」，不该触发保存信号（会写一次无意义的 settings）。
        ``animate=False`` 同理：开机不该甩一段动画。
        """
        # 屏蔽 toggled：那条回调会立刻按默认方式（带动画）展开，等我们下面按
        # animate 参数再置一次状态时已经成了同状态 no-op——启动恢复偏好要的就是
        # 无动画，所以这里由 set_pinned 自己全权走完。
        self._pin_btn.blockSignals(True)
        try:
            self._pin_btn.setChecked(pinned)
        finally:
            self._pin_btn.blockSignals(False)
        self._pinned = pinned
        self._update_pin_tooltip()
        if emit:
            self.pin_toggled.emit(pinned)
        self.set_expanded(
            self._pinned or self._hover or self._focus, animate=animate
        )

    def _on_pin_toggled(self, checked: bool) -> None:
        """用户点了钉住：状态由 QToolButton 的勾选态驱动（setChecked 也走这里）。"""
        self._pinned = bool(checked)
        self._update_pin_tooltip()
        self._update_expanded()
        self.pin_toggled.emit(self._pinned)

    def _update_pin_tooltip(self) -> None:
        self._pin_btn.setToolTip(
            self.tr("取消钉住（移开鼠标后自动收起）")
            if self._pinned
            else self.tr("钉住导航栏（保持展开）")
        )

    def _on_anim_value(self, value) -> None:
        width = int(value)
        self.setFixedWidth(width)
        btn_width = max(width - self._margins, 26)
        for btn in self._buttons:
            btn.setFixedWidth(btn_width)
        # 钉住按钮跟着变宽（保持与导航按钮左右对齐），但高度不变
        pin = getattr(self, "_pin_btn", None)
        if pin is not None:
            pin.setFixedWidth(btn_width)
        # 收起到位就把文字抠掉。**不用 finished 信号**：那东西只在动画自然跑到
        # 终点时才发，中途被打断（手又挪回来）或 stop() 都不发，反而埋雷——
        # 这里改成按「宽度到位」判定，动画被怎么折腾状态都不会错。
        if not self._expanded and width <= COLLAPSED_WIDTH:
            self._apply_text(False)

    def _apply_text(self, show: bool) -> None:
        """``show=False`` 时把文字清空（只留图标 + tooltip）。"""
        for btn, label in zip(self._buttons, self._labels):
            btn.setText(label if show else "")

    def _measure_label_width(self) -> int:
        """按当前语言下最长的标签估展开宽度（带富余，避免边缘截断）。"""
        if not self._buttons:
            return MIN_LABEL_WIDTH
        fm = self._buttons[0].fontMetrics()
        widest = max((fm.horizontalAdvance(label) for label in self._labels),
                     default=0)
        # +22：按钮内边距 + QSS 12px 字体比默认字体窄带来的误差富余
        return min(max(widest + 22, MIN_LABEL_WIDTH), MAX_LABEL_WIDTH)

    def _update_expanded(self) -> None:
        """悬停 / 聚焦 / 钉住 三者任一成立就展开（钉住优先级最高）。"""
        self.set_expanded(self._pinned or self._hover or self._focus)

    # ------------------------------------------------------------ 事件

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名约定
        etype = event.type()
        if etype == QEvent.Type.FocusIn:
            self._focus = True
            self._update_expanded()
            return super().eventFilter(obj, event)
        if etype == QEvent.Type.FocusOut:
            self._focus = False
            self._update_expanded()
            return super().eventFilter(obj, event)

        index = self._button_index(obj)
        if index < 0:
            return super().eventFilter(obj, event)

        if etype == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_index = index
                self._drag_start = event.position().toPoint()
                self._drag_fired = False
        elif etype == QEvent.Type.MouseMove:
            if self._drag_index == index and not self._drag_fired:
                pos = event.position().toPoint()
                if (pos - self._drag_start).manhattanLength() >= DRAG_OUT_THRESHOLD:
                    self._drag_fired = True
                    # 按钮已被按下：先复位按下态，否则浮窗出来后按钮还是凹的
                    obj.setDown(False)
                    try:
                        self.drag_out_requested.emit(index)
                    except RuntimeError:
                        pass
                    # 吞掉这次移动：页面已被拖走，别让按钮继续按「点一下」处理
                    return True
        elif etype == QEvent.Type.MouseButtonRelease:
            fired = self._drag_fired and self._drag_index == index
            self._drag_index = -1
            self._drag_fired = False
            if fired:
                # 吞掉释放，否则按钮会再发一次 clicked → 又切回被拖走的那页
                return True
        # 注意：**不要**在 Leave 里重置拖拽状态。Windows 上按住鼠标拖出控件
        # 范围照样会发 Leave（macOS 有 grab 时不发），照它重置会让拖出手势
        # 在 Windows 上永远失效——这正是 detachable.py 里踩过的坑。
        return super().eventFilter(obj, event)

    def _button_index(self, obj) -> int:
        """该对象是第几枚导航按钮；不是导航按钮返回 -1。"""
        for i, btn in enumerate(self._buttons):
            if btn is obj:
                return i
        return -1

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 命名约定
        self._hover = True
        self._update_expanded()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名约定
        self._hover = False
        self._update_expanded()
        super().leaveEvent(event)

    # ------------------------------------------------------------ 样式

    def _apply_style(self) -> None:
        bg = theme.css("alt_row")
        grid = theme.css("grid_line")
        soft = theme.css("accent_soft")
        sel_bg = theme.css("sel_bg")
        sel_fg = theme.css("sel_fg")
        # 钉住开关不参与「当前页」的选择语义：checked 用浅色块（soft）而非
        # 选中页的强调色（sel_bg），避免和真正选中的那一页混淆。
        self.setStyleSheet(f"""
#navRail {{
    background-color: {bg};
    border-right: 1px solid {grid};
}}
#navRail QToolButton {{
    border: none;
    border-radius: 8px;
    padding: 4px 2px 3px 2px;
    color: palette(window-text);
    font-size: 12px;
}}
#navRail QToolButton:hover {{ background-color: {soft}; }}
#navRail QToolButton:checked {{
    background-color: {sel_bg};
    color: {sel_fg};
}}
/* pin toggle: soft highlight instead of the page-selection accent color */
#navRail QToolButton#navPin {{
    padding: 2px;
    color: palette(window-text);
    opacity: 0.75;
}}
#navRail QToolButton#navPin:hover {{ opacity: 1; background-color: {soft}; }}
#navRail QToolButton#navPin:checked {{
    background-color: {soft};
    color: palette(window-text);
    opacity: 1;
}}
""")

    def _retheme(self) -> None:
        """主题切换：重算样式表与图标颜色（含钉住按钮）。"""
        self._apply_style()
        pin = getattr(self, "_pin_btn", None)
        if pin is not None:
            pin.setIcon(icons.icon("pin", 16))
