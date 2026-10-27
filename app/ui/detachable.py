"""把标签页拖出成独立非模态浮窗，并可原位收回。

用法场景：工具页（以及它内部的编码转换 / JSON / 比对 / API 调试 / FIX
子页）这类辅助页面，常常要跟主窗口的流量列表**同时看**——把抓到的 body
粘过去格式化、或者一边改请求一边盯列表。塞在标签页里就得来回切，拖成
独立窗口并排摆着最顺。

设计要点
--------
**浮窗是非模态的**：拖出后主窗口照常抓包、点按钮、切页，不受影响。这靠
``Qt.Window`` 顶层窗口实现（不是 ``Qt.Tool``——后者在 macOS 上会浮在别的
应用之上，抢戏）。

**原位留占位页**：拖出后原索引位置塞一个 ``_Placeholder``（带「收回」
按钮），而不是直接 removeTab。因为主窗口的左侧导航 rail 与 Ctrl+1…N
快捷键都是**按索引**绑定 tab 的（``main_window.py`` 里 rail 的
``current_changed`` 直连 ``tabs.setCurrentIndex``），一旦索引塌陷，后面
所有页的导航和快捷键全错位。留占位页等于把这块改动压到零。

**插拔期间屏蔽信号**：removeTab + insertTab 会各触发一次 currentChanged，
让导航先跳到占位页再跳回来。所以插拔一律包在 ``_quiet()`` 里，事后手动
补发一次 currentChanged 把导航同步到真实当前页。

**关闭即收回**：浮窗的 closeEvent 被拦下，先把页面还给原容器再销毁自己，
绝不能让页面跟着浮窗一起没——面板对象是主窗口长期持有的（信号槽、
后续调用都指着它），误销毁就是野指针崩溃。
"""

from __future__ import annotations

import contextlib

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

#: 浮窗的默认尺寸下限（页面 sizeHint 太小时兜底，别拖出来一条）
MIN_FLOAT_SIZE = QSize(560, 420)
#: 按住标签拖出多少像素算「用户是想拖出去」而不是「想切页」
DRAG_THRESHOLD = 28


class _Placeholder(QWidget):
    """拖出后留在原位的占位页：说明去向 + 一键收回。

    不给空白页是因为：拖出后主窗口那个位置一片空白，用户会以为功能坏了，
    也不知道去哪儿把它找回来。
    """

    #: 用户点了「收回」
    reattach_requested = Signal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("detachPlaceholder")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addStretch(1)

        tip = QLabel(
            self.tr("「{0}」已拖出为独立窗口").format(title)
        )
        tip.setWordWrap(True)
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(tip)

        btn = QPushButton(self.tr("收回"))
        btn.setFixedWidth(96)
        btn.clicked.connect(self.reattach_requested)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addStretch(1)


class FloatWindow(QWidget):
    """承载一个被拖出页面的顶层窗口。

    必须拦 closeEvent：默认行为会连里面的页面一起销毁，而页面是主窗口
    长期持有的对象。
    """

    #: 用户点了关闭（外部据此把页面收回原位）
    close_requested = Signal(object)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle(title)
        # 关掉只隐藏不销毁——销毁时机由 TabDetacher 收回页面后决定
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._closing = False
        self._host = QVBoxLayout(self)
        self._host.setContentsMargins(0, 0, 0, 0)

    def set_page(self, widget: QWidget) -> None:
        """把页面收进来。reparent 前先 hide，避免中间态闪一下。"""
        widget.hide()
        self._host.addWidget(widget)
        widget.show()

    def take_page(self) -> QWidget | None:
        """把页面交出去（reparent 到 None），浮窗不再持有它。"""
        item = self._host.itemAt(0)
        widget = item.widget() if item is not None else None
        if widget is None:
            return None
        self._host.removeWidget(widget)
        widget.hide()
        widget.setParent(None)
        return widget

    @property
    def is_closing(self) -> bool:
        return self._closing

    def closeEvent(self, event):  # noqa: N802 - Qt 命名约定
        """关闭 = 请求收回（外部负责把页面还回去），然后销毁空壳。"""
        if not self._closing:
            self._closing = True
            self.close_requested.emit(self)
        event.accept()
        self.deleteLater()


class TabDetacher(QObject):
    """给一个 QTabWidget 装上「页面可拖出 / 可收回」的能力。

    同一个类同时服务两级：主窗口的顶层页（工具页）和工具页内部的子页
    （编码转换 / JSON / 比对 / API 调试 / FIX）。

    :param tabs: 被管理的 QTabWidget
    :param title_of: 可选，``widget -> 标题``，拖出时给浮窗定标题
    :param tag_of: 可选，``widget -> 标识``，供外部按业务 key 反查
    """

    #: 拖出 / 收回后发出（外部据此刷新菜单、持久化等）
    changed = Signal()

    def __init__(self, tabs: QTabWidget, parent=None,
                 title_of=None, tag_of=None):
        super().__init__(parent)
        self._tabs = tabs
        self._title_of = title_of
        self._tag_of = tag_of
        self._records: dict[int, dict] = {}     # id(widget) -> record
        self._drag_index = -1
        self._drag_start = QPoint()
        self._drag_enabled = False
        self._allowed = None                    # 可选白名单：widget -> bool

    # ------------------------------------------------------------ 查询

    def set_allowed(self, predicate) -> None:
        """限制哪些页面允许拖出（``widget -> bool``）；None 表示全放行。

        详情页签里只有请求/响应适合拖出去，耗时/过滤/WebSocket 拖走了反而
        找不到，所以按页面收窄而不是整条 tabBar 一刀切。
        """
        self._allowed = predicate

    @property
    def tabs(self) -> QTabWidget:
        return self._tabs

    def is_detached(self, widget: QWidget) -> bool:
        return id(widget) in self._records

    def index_detached(self, index: int) -> bool:
        """该索引处是不是「已拖出」——占位页也算。

        拖出后原位站的是 ``_Placeholder`` 而不是原页面，所以除了判原页面
        还得认占位页，否则导航点上去会切到一片空白。
        """
        widget = self._tabs.widget(index)
        if widget is None:
            return False
        if isinstance(widget, _Placeholder):
            return True
        return self.is_detached(widget)

    def window_for(self, widget: QWidget) -> FloatWindow | None:
        return self._records.get(id(widget), {}).get("window")

    def window_for_tag(self, tag) -> FloatWindow | None:
        for rec in self._records.values():
            if rec.get("tag") == tag:
                return rec.get("window")
        return None

    def is_tag_detached(self, tag) -> bool:
        return self.window_for_tag(tag) is not None

    def detached_widgets(self) -> list[QWidget]:
        return [rec["widget"] for rec in self._records.values()]

    def detached_tags(self) -> list:
        return [rec.get("tag") for rec in self._records.values()]

    def nearest_live(self, index: int) -> int:
        """该索引附近第一个不是占位页的索引（拖出后别停在空白页）。"""
        return self._nearest_live(index)

    def widget_for_tag(self, tag):
        """按业务标识取回页面本体（不管它在浮窗里还是标签页里）。"""
        for rec in self._records.values():
            if rec.get("tag") == tag:
                return rec["widget"]
        return None

    def tag_at(self, index: int):
        """某索引处的业务标识；占位页返回它代表的那个被拖出页面的标识。"""
        widget = self._tabs.widget(index)
        if widget is None:
            return None
        if isinstance(widget, _Placeholder):
            for rec in self._records.values():
                if rec.get("placeholder") is widget:
                    return rec.get("tag")
            return None
        return self._tag_of_call(widget, index)

    def any_detached(self) -> bool:
        return bool(self._records)

    # ------------------------------------------------------------ 拖出

    def detach(self, target, title: str | None = None,
               tag=None) -> FloatWindow | None:
        """把一个页面拖成独立浮窗。

        :param target: 页面 widget 或它的索引
        :param title: 浮窗标题，缺省用标签文字
        :param tag: 业务标识（如 "json" / "fix"），供外部反查
        :return: 新建的浮窗；已在浮窗中或索引无效则返回 None
        """
        idx = target if isinstance(target, int) else self._tabs.indexOf(target)
        if idx < 0:
            return None
        widget = self._tabs.widget(idx)
        if widget is None or self.is_detached(widget):
            return None
        if self._allowed is not None and not self._allowed(widget):
            return None

        text = title or self._tabs.tabText(idx) or ""
        icon = self._tabs.tabIcon(idx)
        tip = self._tabs.tabToolTip(idx)
        was_current = self._tabs.currentIndex() == idx

        placeholder = _Placeholder(text, self._tabs)
        with self._quiet():
            self._tabs.removeTab(idx)
            self._tabs.insertTab(idx, placeholder, icon, text)
            self._tabs.setTabToolTip(idx, tip)
            # 别停在一片空白的占位页上：挪到相邻的真实页面
            if was_current:
                self._tabs.setCurrentIndex(self._nearest_live(idx))

        win = FloatWindow(text)
        win.set_page(widget)
        size = widget.size()
        win.resize(
            max(size.width(), MIN_FLOAT_SIZE.width()),
            max(size.height(), MIN_FLOAT_SIZE.height()),
        )

        rec = {
            "widget": widget,
            "index": idx,
            "text": text,
            "icon": icon,
            "tooltip": tip,
            "tag": tag if tag is not None else self._tag_of_call(widget, idx),
            "placeholder": placeholder,
            "window": win,
        }
        self._records[id(widget)] = rec
        win.close_requested.connect(lambda _w, w=widget: self.reattach(w))
        placeholder.reattach_requested.connect(lambda w=widget: self.reattach(w))

        win.show()
        win.raise_()
        self._emit_changed()
        return win

    def detach_by_tag(self, tag, title: str | None = None):
        """按业务标识拖出（页面不在本 tabs 里时返回 None）。"""
        for i in range(self._tabs.count()):
            widget = self._tabs.widget(i)
            if widget is None or self.is_detached(widget):
                continue
            if self._tag_of_call(widget, i) == tag:
                return self.detach(i, title=title, tag=tag)
        return None

    def raise_detached(self, target) -> bool:
        """把已拖出的浮窗提到前面（主窗口不受影响）。

        :param target: 页面 widget，或它原先所在的索引（占位页也算）
        """
        if isinstance(target, int):
            if not self.index_detached(target):
                return False
            widget = self._widget_at_placeholder(target)
        else:
            widget = target
        win = self.window_for(widget) if widget is not None else None
        if win is None:
            return False
        win.show()
        win.raise_()
        win.activateWindow()
        return True

    # ------------------------------------------------------------ 收回

    def reattach(self, widget: QWidget) -> bool:
        """把页面放回原来的索引位置，销毁浮窗。"""
        rec = self._records.pop(id(widget), None)
        if rec is None:
            return False
        win: FloatWindow | None = rec["window"]
        placeholder: QWidget | None = rec["placeholder"]
        idx = rec["index"]

        if win is not None:
            # 先摘页面再关窗：closeEvent 会回调 reattach，_closing 挡住重入
            win.take_page()
            win._closing = True
            win.close()

        with self._quiet():
            ph_idx = self._tabs.indexOf(placeholder) if placeholder is not None else -1
            if ph_idx >= 0:
                self._tabs.removeTab(ph_idx)
            # 索引可能被别的插拔挤过，夹回合法范围
            idx = max(0, min(idx, self._tabs.count()))
            self._tabs.insertTab(idx, widget, rec["icon"], rec["text"])
            if rec["tooltip"]:
                self._tabs.setTabToolTip(idx, rec["tooltip"])
            self._tabs.setCurrentIndex(idx)
        widget.show()
        self._emit_changed()
        return True

    def reattach_all(self) -> None:
        """全部收回（主窗口退出前调用）。"""
        for widget in self.detached_widgets():
            self.reattach(widget)

    def close_all(self, reattach: bool = False) -> None:
        """关掉所有浮窗。

        :param reattach: True 先收回页面再关（正常路径）；
            False 直接关（退出时页面即将随主窗口销毁，不必再插回去）
        """
        for widget in self.detached_widgets():
            if reattach:
                self.reattach(widget)
                continue
            rec = self._records.pop(id(widget), None)
            if rec is None:
                continue
            win = rec.get("window")
            if win is not None:
                # 先摘页面再关：空壳销毁时会把它 layout 里的部件一起带走，
                # 而这些页面是主窗口长期持有的对象（退出后可能还要读它们
                # 的配置），跟着浮窗一起没就是野指针。摘出来挂回宿主标签控件
                # 名下（隐藏态，不是页签），随主窗口一起销毁。
                page = win.take_page()
                if page is not None:
                    page.setParent(self._tabs)
                win._closing = True
                win.close()
            placeholder = rec.get("placeholder")
            if placeholder is not None:
                ph_idx = self._tabs.indexOf(placeholder)
                if ph_idx >= 0:
                    with self._quiet():
                        self._tabs.removeTab(ph_idx)
        self._emit_changed()

    # ------------------------------------------------------------ 拖拽

    def enable_drag(self, enabled: bool = True) -> None:
        """允许按住标签拖出（超过 DRAG_THRESHOLD 像素即触发）。"""
        self._drag_enabled = enabled
        bar = self._tabs.tabBar()
        if enabled:
            bar.setMouseTracking(True)
            bar.installEventFilter(self)
        else:
            bar.removeEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802 - Qt 命名约定
        # 本对象可能已经随页面一起被销毁，而 Qt 仍会往残留的过滤器派一次事件：
        # 这时 Python 侧属性已被清空，摸 self._tabs 就是 AttributeError。
        # （合跑测试时它会打断后续用例，必须挡住）
        try:
            tabs = self._tabs
        except (RuntimeError, AttributeError):
            return False
        # 退出时 tabBar 可能先于本对象被销毁（销毁顺序不由我们决定），
        # 这时再摸它就是 RuntimeError。事件过滤器晚于控件死亡是常态，直接
        # 放行即可——不影响任何功能。
        try:
            bar = tabs.tabBar()
        except RuntimeError:
            return False
        try:
            enabled = self._drag_enabled
        except (RuntimeError, AttributeError):
            return False
        if enabled and obj is bar:
            etype = event.type()
            if etype == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    pos = event.position().toPoint()
                    self._drag_index = bar.tabAt(pos)
                    self._drag_start = pos
            elif etype == QEvent.Type.MouseMove:
                if self._drag_index >= 0:
                    pos = event.position().toPoint()
                    if (pos - self._drag_start).manhattanLength() >= DRAG_THRESHOLD:
                        idx = self._drag_index
                        self._drag_index = -1
                        self.detach(idx)
                        # 吞掉这次移动：否则松手时 QTabBar 还会顺势切页
                        return True
            elif etype in (QEvent.Type.MouseButtonRelease,
                           QEvent.Type.Leave):
                self._drag_index = -1
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------ 内部

    def _tag_of_call(self, widget: QWidget, index: int):
        if self._tag_of is None:
            return index
        try:
            return self._tag_of(widget, index)
        except TypeError:
            return self._tag_of(widget)

    def _widget_at_placeholder(self, index: int):
        """占位页所在的索引对应哪个被拖出的页面（占位页本身不是原页面）。"""
        for rec in self._records.values():
            ph = rec.get("placeholder")
            if ph is not None and self._tabs.indexOf(ph) == index:
                return rec["widget"]
        return None

    def _nearest_live(self, idx: int) -> int:
        """找一个不是占位页的相邻索引（用于拖出后别停在空白页）。"""
        count = self._tabs.count()
        for i in range(idx, count):
            if self._tabs.widget(i) is not None and not self._is_placeholder_at(i):
                return i
        for i in range(idx - 1, -1, -1):
            if self._tabs.widget(i) is not None and not self._is_placeholder_at(i):
                return i
        return 0

    def _is_placeholder_at(self, index: int) -> bool:
        widget = self._tabs.widget(index)
        return widget is not None and isinstance(widget, _Placeholder)

    @contextlib.contextmanager
    def _quiet(self):
        """插拔期间屏蔽 tab 信号，事后补发一次让导航同步到真实当前页。

        不屏蔽的话：removeTab 把当前页甩到邻居、insertTab 又把占位页推上来，
        currentChanged 连发两次，导航的选中态一路乱跳。
        """
        self._tabs.blockSignals(True)
        try:
            yield
        finally:
            self._tabs.blockSignals(False)
            self._tabs.currentChanged.emit(self._tabs.currentIndex())

    def _emit_changed(self) -> None:
        try:
            self.changed.emit()
        except RuntimeError:
            pass


class WidgetFloat(QObject):
    """把一个不在标签控件里的部件（如详情面板）拖成浮窗，并可收回。

    与 ``TabDetacher`` 的分工：后者管 QTabWidget 里的页，必须留占位页保索引；
    这里管的部件直接挂在布局 / splitter 上，拖走后原布局自然收缩，不需要
    占位，也没有索引要保。

    **摘出与放回由调用方负责**，本类只管窗口生命周期：``detach()`` 之前调用方
    先把部件从原布局摘下来，``reattach()`` 交还部件后由调用方塞回去——因为
    怎么塞（恢复 splitter 比例、重设 sizePolicy）只有调用方知道。
    """

    #: 拖出 / 收回后发出
    changed = Signal()
    #: 用户关掉了浮窗，需要调用方把部件放回原布局（参数 = 部件）
    attach_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widget: QWidget | None = None
        self._win: FloatWindow | None = None

    @property
    def widget(self) -> QWidget | None:
        return self._widget

    def window(self) -> FloatWindow | None:
        return self._win

    def is_detached(self) -> bool:
        return self._widget is not None

    def detach(self, widget: QWidget, title: str) -> FloatWindow | None:
        """把部件收进浮窗。已经拖着别的部件时返回 None（一次只拖一个）。"""
        if self._widget is not None or widget is None:
            return None
        win = FloatWindow(title)
        win.set_page(widget)
        size = widget.size()
        win.resize(
            max(size.width(), MIN_FLOAT_SIZE.width()),
            max(size.height(), MIN_FLOAT_SIZE.height()),
        )
        win.close_requested.connect(self._on_close_requested)
        self._widget = widget
        self._win = win
        win.show()
        win.raise_()
        self._emit_changed()
        return win

    def reattach(self) -> QWidget | None:
        """收回并把部件交还调用方（放回布局是调用方的事）。"""
        widget, win = self._widget, self._win
        if widget is None:
            return None
        self._widget = None
        self._win = None
        if win is not None:
            # 先摘页面再关窗：closeEvent 会回调本类，_closing 挡住重入
            win.take_page()
            win._closing = True
            win.close()
        self._emit_changed()
        return widget

    def close(self) -> None:
        """只关窗不收回（退出路径：部件即将随主窗口销毁，不必再塞回去）。"""
        if self._widget is None:
            return
        widget, win = self._widget, self._win
        self._widget = None
        self._win = None
        if win is not None:
            # 同样先把部件摘出来：否则它会随空壳一起被销毁
            win.take_page()
            if widget is not None and self.parent() is not None:
                widget.setParent(self.parent())
            win._closing = True
            win.close()
        self._emit_changed()

    def _on_close_requested(self, _win) -> None:
        widget = self.reattach()
        if widget is not None:
            try:
                self.attach_requested.emit(widget)
            except RuntimeError:
                pass

    def _emit_changed(self) -> None:
        try:
            self.changed.emit()
        except RuntimeError:
            pass
