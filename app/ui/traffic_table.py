"""流量表格 + 过滤栏 + 搜索栏（DESIGN.md 3.2 / 3.2.1 / 3.2.2）。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableView,
    QWidget,
)

from app.ui.filter_model import (
    SCOPE_BODY,
    SCOPE_HEADERS,
    SCOPE_URL,
    FilterConfig,
    FlowFilterProxyModel,
    SearchConfig,
)
from app.ui.flow_store import (
    COLUMN_KEYS,
    COL_DURATION,
    COL_HOST,
    COL_ID,
    COL_MARK,
    COL_METHOD,
    COL_PATH,
    COL_REQ_SIZE,
    COL_RESP_SIZE,
    COL_SERVER_IP,
    COL_STATUS,
    column_index,
)
from app.ui.visuals import MethodBadgeDelegate, StatusBadgeDelegate


class FilterBar(QWidget):
    """域名过滤（黑/白名单 + 启用开关）+ 类型隐藏。变更即发信号，由主窗口持久化。

    与详情面板的「过滤」页（``app.ui.filter_panel.FilterPanel``）共用同一份
    ``FilterConfig``：这里只显示并编辑**当前启用**的那个列表，另一个列表在
    过滤页里维护；两处内容永远一致（都由主窗口回灌）。
    """

    changed = Signal()
    #: 「预设」菜单即将弹出：主窗口借此机会重建菜单内容（动态数据）
    preset_menu_about_to_show = Signal()
    #: 用户请求打开「过滤」页（顶部栏 → 详情面板页签）
    filter_page_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # 最近一次 load_config 灌进来的**完整**配置。顶部栏只展示一个列表，
        # 切列表 / 提交时得知道另一份是什么——否则会把另一份抹掉（真踩过）。
        self._config = FilterConfig()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        layout.addWidget(QLabel(self.tr("域名过滤:")))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(self.tr("关闭"), "off")
        self.mode_combo.addItem(self.tr("黑名单(隐藏)"), "blacklist")
        self.mode_combo.addItem(self.tr("白名单(只显示)"), "whitelist")
        self.mode_combo.setToolTip(
            self.tr("三态互斥：一次只启用黑名单或白名单，关掉则两个列表都不生效")
        )
        layout.addWidget(self.mode_combo)

        self.keywords_edit = QLineEdit()
        self.keywords_edit.setClearButtonEnabled(True)
        self.keywords_edit.setToolTip(
            self.tr("编辑当前启用的列表（逗号分隔）；另一份列表在「过滤」页维护")
        )
        layout.addWidget(self.keywords_edit, stretch=1)

        self.hide_connect_cb = QCheckBox(self.tr("隐藏 CONNECT"))
        self.hide_image_cb = QCheckBox(self.tr("隐藏 Image"))
        layout.addWidget(self.hide_connect_cb)
        layout.addWidget(self.hide_image_cb)

        # 过滤预设（路线图 #7）：一个按钮 + 动态菜单。菜单内容由主窗口在
        # aboutToShow 时重建（预设列表 / 当前套用 / 是否已手改偏离），
        # FilterBar 本身不碰持久化——和列显隐菜单同一套路。
        self.preset_btn = QPushButton(self.tr("预设"))
        self.preset_btn.setToolTip(
            self.tr("过滤预设：把当前过滤条件存成命名预设，切换场景一键套用"
                    "（域名黑白名单 + 隐藏 CONNECT/Image）")
        )
        self.preset_menu = QMenu(self)
        self.preset_menu.aboutToShow.connect(self.preset_menu_about_to_show)
        self.preset_btn.setMenu(self.preset_menu)
        layout.addWidget(self.preset_btn)

        # 跳转到「过滤」页：域名过滤的完整编辑界面（两个列表 + 命中数）
        self.page_btn = QPushButton(self.tr("过滤页"))
        self.page_btn.setToolTip(
            self.tr("打开详情面板的「过滤」页：黑白名单两个列表一起看，"
                    "带每个域名的实时命中数")
        )
        self.page_btn.clicked.connect(self.filter_page_requested)
        layout.addWidget(self.page_btn)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.keywords_edit.textChanged.connect(self.changed)
        self.hide_connect_cb.toggled.connect(self.changed)
        self.hide_image_cb.toggled.connect(self.changed)

    # ------------------------------------------------------------ 配置同步

    def load_config(self, config: FilterConfig) -> None:
        self._config = config
        self._block_signals(True)
        if config.enabled:
            idx = self.mode_combo.findData(config.active_list)
        else:
            idx = self.mode_combo.findData("off")
        self.mode_combo.setCurrentIndex(max(idx, 0))
        self.keywords_edit.setText(", ".join(config.active_entries))
        self.hide_connect_cb.setChecked(config.hide_connect)
        self.hide_image_cb.setChecked(config.hide_image)
        self._update_edit_state()
        self._block_signals(False)

    def to_config(self) -> FilterConfig:
        data = self.mode_combo.currentData()
        keywords = [
            k.strip() for k in self.keywords_edit.text().split(",") if k.strip()
        ]
        cur = self._config or FilterConfig()
        hide_connect = self.hide_connect_cb.isChecked()
        hide_image = self.hide_image_cb.isChecked()
        if data == "whitelist":
            return FilterConfig(
                blacklist=list(cur.blacklist), whitelist=keywords,
                enabled=True, active_list="whitelist",
                hide_connect=hide_connect, hide_image=hide_image,
            )
        if data == "off":
            # 关掉不清列表：按「关之前正在看的那份」把内容放回它自己的坑位
            if cur.active_list == "whitelist":
                black, white = list(cur.blacklist), keywords
            else:
                black, white = keywords, list(cur.whitelist)
            return FilterConfig(
                blacklist=black, whitelist=white,
                enabled=False, active_list=cur.active_list,
                hide_connect=hide_connect, hide_image=hide_image,
            )
        return FilterConfig(
            blacklist=keywords, whitelist=list(cur.whitelist),
            enabled=True, active_list="blacklist",
            hide_connect=hide_connect, hide_image=hide_image,
        )

    def _block_signals(self, block: bool) -> None:
        for w in (
            self.mode_combo,
            self.keywords_edit,
            self.hide_connect_cb,
            self.hide_image_cb,
        ):
            w.blockSignals(block)

    def _on_mode_changed(self) -> None:
        """切换列表：输入框内容必须先换成新列表的，再发 changed。

        顺序很重要——如果直接发 changed，箱子里的还是**上一个列表**的内容，
        会被当成新列表的内容提交：白名单 a.test 时切到黑名单，原来存着的
        黑名单 b.test 当场被抹掉（真实踩过）。所以这里先把文本换源再发。
        """
        data = self.mode_combo.currentData()
        cur = self._config or FilterConfig()
        if data == "whitelist":
            entries = cur.whitelist
        elif data == "off":
            entries = cur.active_entries      # 关掉时保持「关之前看的那份」
        else:
            entries = cur.blacklist
        self._block_signals(True)
        self.keywords_edit.setText(", ".join(entries))
        self._block_signals(False)
        self._update_edit_state()
        self.changed.emit()

    def _update_edit_state(self) -> None:
        data = self.mode_combo.currentData()
        off = data == "off"
        self.keywords_edit.setEnabled(not off)
        if off:
            self.keywords_edit.setPlaceholderText(self.tr("域名过滤已关闭"))
        elif data == "whitelist":
            self.keywords_edit.setPlaceholderText(
                self.tr("白名单域名，逗号分隔；支持通配符 *（如 *.apple.com）")
            )
        else:
            self.keywords_edit.setPlaceholderText(
                self.tr("黑名单域名，逗号分隔；支持通配符 *（如 *.apple.com）")
            )


class SearchBar(QWidget):
    """Ctrl+F 搜索栏：关键字 + 范围 + 大小写 + 匹配跳转。"""

    closed = Signal()
    config_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.input = QLineEdit()
        self.input.setPlaceholderText(self.tr("搜索 URL / Headers / Body …"))
        self.input.setClearButtonEnabled(True)
        layout.addWidget(self.input, stretch=1)

        self.url_cb = QCheckBox("URL")
        self.headers_cb = QCheckBox("Headers")
        self.body_cb = QCheckBox("Body")
        self.url_cb.setChecked(True)
        for cb in (self.url_cb, self.headers_cb, self.body_cb):
            layout.addWidget(cb)

        self.case_btn = QPushButton("Aa")
        self.case_btn.setCheckable(True)
        self.case_btn.setToolTip(self.tr("区分大小写"))
        self.case_btn.setMaximumWidth(32)
        layout.addWidget(self.case_btn)

        self.count_label = QLabel("")
        self.count_label.setMinimumWidth(110)
        layout.addWidget(self.count_label)

        self.prev_btn = QPushButton("↑")
        self.next_btn = QPushButton("↓")
        for b in (self.prev_btn, self.next_btn):
            b.setMaximumWidth(30)
            b.setToolTip(self.tr("在匹配项间跳转（Enter / Shift+Enter）"))
            layout.addWidget(b)

        close_btn = QPushButton("✕")
        close_btn.setMaximumWidth(30)
        close_btn.setToolTip(self.tr("关闭搜索（Esc）"))
        close_btn.clicked.connect(self.closed)
        layout.addWidget(close_btn)

        self.input.textChanged.connect(self._on_text_changed)
        self.input.returnPressed.connect(self.next_btn.click)
        for cb in (self.url_cb, self.headers_cb, self.body_cb):
            cb.toggled.connect(self.config_changed)
        self.case_btn.toggled.connect(self.config_changed)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)  # debounce 300ms（见 3.2.2）
        self._debounce.timeout.connect(self.config_changed)

    # ------------------------------------------------------------ 交互

    def focus_input(self) -> None:
        self.show()
        self.input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.input.selectAll()

    def _on_text_changed(self) -> None:
        self._debounce.start()

    def set_match_count(self, matched: int, total: int) -> None:
        if not self.input.text():
            self.count_label.setText("")
        else:
            self.count_label.setText(self.tr('匹配 {0} / {1} 条').format(matched, total))

    # ------------------------------------------------------------ 配置

    def to_config(self) -> SearchConfig:
        cfg = SearchConfig()
        cfg.text = self.input.text()
        cfg.case_sensitive = self.case_btn.isChecked()
        scopes = set()
        if self.url_cb.isChecked():
            scopes.add(SCOPE_URL)
        if self.headers_cb.isChecked():
            scopes.add(SCOPE_HEADERS)
        if self.body_cb.isChecked():
            scopes.add(SCOPE_BODY)
        cfg.scopes = scopes or {SCOPE_URL}
        return cfg


class TrafficTable(QTableView):
    """流量列表；选中变化由主窗口接去更新详情面板。

    多选（Ctrl/Shift 点选）用于批量导出与批量复制；详情面板只跟随第一个选中项。

    键盘快捷键（仅在本表获得焦点时生效）：
    - R：重放选中请求；E：编辑后重放选中请求（由主窗口接去执行）；
    - Ctrl+X：清空流量列表（在主窗口绑定）。
    """

    # 选中某条请求后按 R / E 触发的重放信号（无修饰键）
    replay_requested = Signal()
    edit_replay_requested = Signal()
    # 表头右键：弹出列显隐菜单（主窗口构建菜单内容，这里只转发位置）
    column_menu_requested = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(22)   # Fiddler 式紧凑行高
        header = self.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self.column_menu_requested)
        self.setSortingEnabled(True)
        # 方法 / 状态码画成圆角 pill（HTTP 语义色），一眼分得清哪张有问题。
        # 委托里背景仍交给 style 画，错误红行 / mock 绿行 / 选中蓝底不受影响。
        self.setItemDelegateForColumn(COL_METHOD, MethodBadgeDelegate(self))
        self.setItemDelegateForColumn(COL_STATUS, StatusBadgeDelegate(self))
        # 注意：列宽策略不能只在这里设一次——QHeaderView::setModel() 会把
        # 按列设置的 resize 模式与宽度全部重置回默认（120px），而主窗口是
        # 构造之后才 setModel()。所以真正的配置在 setModel() 里做。

        # 空态引导：没有流量时显示居中提示，替代一片白（鼠标穿透，不挡交互）
        self.empty_overlay = QLabel(
            self.tr("还没有抓到请求\n\n点击左下角状态点开始抓包，或检查过滤条件是否把全部流量藏起来了"),
            self,
        )
        self.empty_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_overlay.setWordWrap(True)
        self.empty_overlay.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.empty_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.empty_overlay.setStyleSheet(
            "QLabel{color: #9aa0a6; font-size: 13px; padding: 24px;}"
        )
        self.empty_overlay.setVisible(False)
        self._density = "comfortable"
        self.set_row_density(self._density)

    #: 行密度 → 行高（px）。舒适档略高于默认 22，紧凑档更窄，长列表更省眼。
    DENSITY_ROW_HEIGHT = {"comfortable": 24, "compact": 18}

    def set_row_density(self, mode: str) -> None:
        """切换流量列表行密度（舒适 / 紧凑），立即生效并记住模式。"""
        if mode not in self.DENSITY_ROW_HEIGHT:
            mode = "comfortable"
        self._density = mode
        self.verticalHeader().setDefaultSectionSize(self.DENSITY_ROW_HEIGHT[mode])

    def _apply_column_layout(self) -> None:
        """列宽策略（v1.15）：全部 Interactive 定宽、支持拖动，不做任何
        自动 Stretch——左右分栏等窄布局下 Stretch 列会被挤压到 0（路径
        整列消失的回归），定宽 + 拖动是最稳的方案。
        """
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(24)
        header.setDefaultSectionSize(120)
        self.setColumnWidth(COL_ID, 40)
        # 方法列要容得下最长的 CONNECT（pill = 文本宽 + 左右内边距）
        self.setColumnWidth(COL_METHOD, 72)
        self.setColumnWidth(COL_HOST, 220)
        self.setColumnWidth(COL_SERVER_IP, 110)
        self.setColumnWidth(COL_PATH, 440)
        self.setColumnWidth(COL_STATUS, 48)
        self.setColumnWidth(COL_REQ_SIZE, 64)
        self.setColumnWidth(COL_RESP_SIZE, 64)
        self.setColumnWidth(COL_DURATION, 64)
        self.setColumnWidth(COL_MARK, 280)
        # 可选列（默认隐藏，勾选后才看得见；宽度仍先配好，勾选即合适）
        self.setColumnWidth(column_index("content_type"), 150)
        self.setColumnWidth(column_index("started"), 96)
        self.setColumnWidth(column_index("comment"), 120)

    def hide_column_by_key(self, key: str, hidden: bool) -> bool:
        """按列 key 显示/隐藏（未知 key 返回 False，不炸）。"""
        idx = column_index(key)
        if idx is None:
            return False
        self.setColumnHidden(idx, bool(hidden))
        return True

    def first_visible_column(self) -> int:
        """第一个没被隐藏的列号（跳转/滚动定位用）。

        ``scrollTo`` 传一个隐藏列的 index 时 ``visualRect`` 是空的，
        QAbstractItemView 会直接 return——行选上了但视口纹丝不动，用户
        以为跳转没反应。「#」列可以被用户勾掉，所以定位不能写死列 0。
        极端情况下（全被隐藏）退回 0，至少不炸。
        """
        model = self.model()
        if model is None:
            return 0
        for col in range(model.columnCount()):
            if not self.isColumnHidden(col):
                return col
        return 0

    def setModel(self, model):  # noqa: N802
        """接入模型后清掉初始排序指示（section=-1 → 保持抓包到达顺序）。

        QTableView.setSortingEnabled(True) 会立刻按「当前指示列」排一次；
        默认指示列是 0，虽然按 # 升序恰好等于到达顺序，但显式清掉更不容易
        在后续改动里悄悄变味。同时必须在 setModel 之后应用列宽策略——
        QHeaderView 换模型时会重置全部按列配置。
        """
        super().setModel(model)
        if model is not None:
            self._apply_column_layout()
            self.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
            model.sort(-1)
            # 空态：行数变化时刷新提示的显隐
            model.rowsInserted.connect(self._update_empty_state)
            model.rowsRemoved.connect(self._update_empty_state)
            model.modelReset.connect(self._update_empty_state)
            model.dataChanged.connect(self._update_empty_state)
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        """没有流量时显示居中引导，替代一片白。"""
        model = self.model()
        empty = model is None or model.rowCount() == 0
        self.empty_overlay.setVisible(empty)
        if empty:
            self.empty_overlay.raise_()

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        # overlay 跟随视口尺寸（它贴在视口上，覆盖表体区域）
        if getattr(self, "empty_overlay", None) is not None:
            self.empty_overlay.setGeometry(self.viewport().geometry())

    def is_sorted(self) -> bool:
        return self.horizontalHeader().sortIndicatorSection() >= 0

    # ------------------------------------------------------------ 滚动位置

    def at_bottom(self) -> bool:
        """是否停在最后一行（自动滚动的判断依据）。

        滚动条不可见（行数没撑满视口）时也算"在底部"——否则列表刚有几条时
        永远不自动滚，用户会以为功能坏了。
        """
        bar = self.verticalScrollBar()
        return not bar.isVisible() or bar.value() >= bar.maximum() - 1

    def at_top(self) -> bool:
        bar = self.verticalScrollBar()
        return not bar.isVisible() or bar.value() <= bar.minimum() + 1

    def scroll_to_newest(self, newest_first: bool) -> None:
        """滚到"最新端"：倒序时最新在顶，正序时在底。

        必须用 scrollToTop/scrollToBottom 把滚动条钉到端点，不能用
        ``scrollTo(index)``——后者默认 EnsureVisible 只保证该行可见，
        当最后一行半露在底边时只做最小位移，导致"有时候滚不到最底部"。
        """
        if newest_first:
            self.scrollToTop()
        else:
            self.scrollToBottom()

    def keyPressEvent(self, event):  # noqa: N802
        # Ctrl+F 由主窗口全局处理；这里只拦截无修饰键的 R / E 重放快捷键。
        # 带修饰键（如已有的 Ctrl+R 重放、Ctrl+E 导出）交给主窗口的 QShortcut，
        # 不要在这里抢，否则会双触发。
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            key = event.key()
            if key == Qt.Key.Key_R:
                self.replay_requested.emit()
                return
            if key == Qt.Key.Key_E:
                self.edit_replay_requested.emit()
                return
        super().keyPressEvent(event)
