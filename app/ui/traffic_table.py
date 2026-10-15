"""流量表格 + 过滤栏 + 搜索栏（DESIGN.md 3.2 / 3.2.1 / 3.2.2）。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
)


class FilterBar(QWidget):
    """域名过滤（黑/白名单）+ 类型隐藏。变更即发信号，由主窗口持久化。"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        layout.addWidget(QLabel("域名:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("隐藏(黑名单)", "blacklist")
        self.mode_combo.addItem("只显示(白名单)", "whitelist")
        self.mode_combo.setToolTip("黑名单：隐藏含关键词的域名；白名单：只显示含关键词的域名")
        layout.addWidget(self.mode_combo)

        self.keywords_edit = QLineEdit()
        self.keywords_edit.setPlaceholderText("关键词，逗号分隔；留空 = 不过滤")
        self.keywords_edit.setClearButtonEnabled(True)
        layout.addWidget(self.keywords_edit, stretch=1)

        self.hide_connect_cb = QCheckBox("隐藏 CONNECT")
        self.hide_image_cb = QCheckBox("隐藏 Image")
        layout.addWidget(self.hide_connect_cb)
        layout.addWidget(self.hide_image_cb)

        self.mode_combo.currentIndexChanged.connect(self.changed)
        self.keywords_edit.textChanged.connect(self.changed)
        self.hide_connect_cb.toggled.connect(self.changed)
        self.hide_image_cb.toggled.connect(self.changed)

    # ------------------------------------------------------------ 配置同步

    def load_config(self, config: FilterConfig) -> None:
        self._block_signals(True)
        idx = self.mode_combo.findData(config.host_mode)
        self.mode_combo.setCurrentIndex(max(idx, 0))
        self.keywords_edit.setText(", ".join(config.host_keywords))
        self.hide_connect_cb.setChecked(config.hide_connect)
        self.hide_image_cb.setChecked(config.hide_image)
        self._block_signals(False)

    def to_config(self) -> FilterConfig:
        keywords = [
            k.strip() for k in self.keywords_edit.text().split(",") if k.strip()
        ]
        return FilterConfig(
            host_mode=self.mode_combo.currentData(),
            host_keywords=keywords,
            hide_connect=self.hide_connect_cb.isChecked(),
            hide_image=self.hide_image_cb.isChecked(),
        )

    def _block_signals(self, block: bool) -> None:
        for w in (
            self.mode_combo,
            self.keywords_edit,
            self.hide_connect_cb,
            self.hide_image_cb,
        ):
            w.blockSignals(block)


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
        self.input.setPlaceholderText("搜索 URL / Headers / Body …")
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
        self.case_btn.setToolTip("区分大小写")
        self.case_btn.setMaximumWidth(32)
        layout.addWidget(self.case_btn)

        self.count_label = QLabel("")
        self.count_label.setMinimumWidth(110)
        layout.addWidget(self.count_label)

        self.prev_btn = QPushButton("↑")
        self.next_btn = QPushButton("↓")
        for b in (self.prev_btn, self.next_btn):
            b.setMaximumWidth(30)
            b.setToolTip("在匹配项间跳转（Enter / Shift+Enter）")
            layout.addWidget(b)

        close_btn = QPushButton("✕")
        close_btn.setMaximumWidth(30)
        close_btn.setToolTip("关闭搜索（Esc）")
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
            self.count_label.setText(f"匹配 {matched} / {total} 条")

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
    """

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
        self.setSortingEnabled(True)
        # 注意：列宽策略不能只在这里设一次——QHeaderView::setModel() 会把
        # 按列设置的 resize 模式与宽度全部重置回默认（120px），而主窗口是
        # 构造之后才 setModel()。所以真正的配置在 setModel() 里做。

    def _apply_column_layout(self) -> None:
        """列宽策略（v1.15）：序号/方法/状态/大小/耗时 这类短内容列给紧凑
        定宽；host 默认 220px（约为原平分宽度的一半，可拖动调整），路径
        设为 Stretch 吃掉全部剩余宽度，窗口越宽看得越多；标记列定宽可拖。
        """
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setDefaultSectionSize(120)
        header.setSectionResizeMode(COL_PATH, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(COL_HOST, 220)
        self.setColumnWidth(COL_ID, 40)
        self.setColumnWidth(COL_METHOD, 56)
        self.setColumnWidth(COL_SERVER_IP, 110)
        self.setColumnWidth(COL_STATUS, 48)
        self.setColumnWidth(COL_REQ_SIZE, 64)
        self.setColumnWidth(COL_RESP_SIZE, 64)
        self.setColumnWidth(COL_DURATION, 64)
        self.setColumnWidth(COL_MARK, 140)

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
        """滚到"最新端"：倒序时最新在顶，正序时在底。"""
        model = self.model()
        if model is None or model.rowCount() == 0:
            return
        row = 0 if newest_first else model.rowCount() - 1
        self.scrollTo(model.index(row, 0))

    def keyPressEvent(self, event):  # noqa: N802
        # Ctrl+F 由主窗口全局处理；这里不拦截
        super().keyPressEvent(event)
