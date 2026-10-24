"""域名过滤页（Fiddler 式 Filter 页）：黑名单 / 白名单两个列表 + 启用开关。

设计要点：
- 与顶部过滤栏（``traffic_table.FilterBar``）**共用同一份 FilterConfig**：
  页面改完发 ``changed``，主窗口落盘并推给代理模型；别处改了配置也通过
  ``load_config()`` 灌回来。两处永远是同一份内容，不会各说各话。
- 黑白名单是两个独立列表，各自增量维护（右键加入、页面添加都是追加去重），
  启用开关只能启用其中一个（关闭 / 黑名单 / 白名单 三态）。
- 只负责「编辑与展示」，不碰持久化与代理模型，便于 offscreen 单测。
"""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt, QT_TRANSLATE_NOOP, QCoreApplication, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.filter_model import (
    LIST_BLACK,
    LIST_WHITE,
    FilterConfig,
    add_domains,
    host_matches,
    normalize_domain,
)

#: 三态开关的 item data
SWITCH_OFF = "off"

HINT_TEXT = QT_TRANSLATE_NOOP(
    "FilterPanel",
    "黑名单与白名单是两个独立列表，各自增量维护；「启用」一次只生效其中一个。\n"
    "• 黑名单：命中域名的请求从列表隐藏；\n"
    "• 白名单：只显示命中域名的请求，其余全部隐藏；\n"
    "写 example.com 会同时覆盖 api.example.com 这类子域；"
    "写不带点的词（如 google）则按关键字子串匹配。\n"
    "在流量列表里右键任意请求，可以直接把它所属域名加进来。"
)


def _host_suffixes(host: str) -> list[str]:
    """``api.example.com`` → ``[api.example.com, example.com, com]``。

    名单条目 ``example.com`` 命中的是「host 等于它」或「host 是它的子域」——
    也就是**条目是 host 的某个后缀**。所以枚举 host 的各级后缀去查表一次即可，
    不必拿每条名单去和每个 host 做字符串运算。
    """
    if not host:
        return []
    labels = host.split(".")
    return [".".join(labels[i:]) for i in range(len(labels))]


def _apply_counts(table: QTableWidget, host_counts: dict) -> None:
    """把每行的命中数写进第 1 列（索引化，见 ``update_counts`` 的说明）。"""
    rows = table.rowCount()
    if rows == 0:
        return
    if not host_counts:                      # 没流量 → 计数全清
        for r in range(rows):
            item = table.item(r, 1)
            if item is not None:
                item.setText("")
        return

    # 先按行登记：带点条目进后缀字典，不带点条目（关键字）进列表
    dotted: dict[str, list[int]] = {}
    keywords: list[tuple[str, int]] = []
    for r in range(rows):
        name = table.item(r, 0)
        entry = normalize_domain(name.text()) if name is not None else ""
        if not entry:
            continue
        if "." in entry:
            dotted.setdefault(entry, []).append(r)
        else:
            keywords.append((entry, r))
    if not dotted and not keywords:
        return

    totals = [0] * rows
    for host, n in host_counts.items():
        h = normalize_domain(host)
        if not h:
            continue
        hit_rows: set[int] = set()
        for suffix in _host_suffixes(h):
            for r in dotted.get(suffix, ()):
                hit_rows.add(r)
        # 不带点的条目按关键字做子串匹配（兼容手输 google 这类片段词的老用法）
        for entry, r in keywords:
            if entry in h:
                hit_rows.add(r)
        for r in hit_rows:
            totals[r] += n

    for r in range(rows):
        item = table.item(r, 1)
        if item is not None:
            value = totals[r]
            item.setText(str(value) if value else "")


class _DomainTable(QTableWidget):
    """域名 + 实时命中数的只读表格（双击不改内容，编辑走下方输入框）。"""

    def __init__(self, parent=None):
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(
            [self.tr("域名"), self.tr("命中")]
        )
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 46)
        # 命中数列右对齐 + 数字用等宽感（借 tabular 数字，视觉上不跳动）
        self.horizontalHeaderItem(1).setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )


class _DomainPickerDialog(QDialog):
    """从当前会话里挑域名：按条数倒序列出出现过的 host，多选后批量加入。

    手工敲域名只适合零星补一两条；真实场景往往是「这屏几十个请求里我不想看
    的那几个域名」，直接列出会话里已有的 host（带条数、支持搜索）挑勾更快。
    已经在名单里、或被现有条目覆盖的域名直接不列——加进去也是去重后无事发生，
    占着列表反而干扰。
    """

    def __init__(self, host_counts: dict, existing, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("从当前流量挑选域名"))
        self.resize(430, 460)

        covered = [normalize_domain(e) for e in (existing or [])]
        covered = [c for c in covered if c]
        rows: list[tuple[str, int]] = []
        ignored = 0
        for host, n in (host_counts or {}).items():
            key = normalize_domain(host)
            if not key:
                continue
            if key in covered or any(host_matches(key, e) for e in covered):
                ignored += 1
                continue
            rows.append((key, int(n)))
        rows.sort(key=lambda kv: (-kv[1], kv[0]))

        root = QVBoxLayout(self)
        root.setSpacing(8)

        self.filter_edit = QLineEdit()
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setPlaceholderText(self.tr("输入片段过滤域名"))
        self.filter_edit.textChanged.connect(self._apply_filter)
        root.addWidget(self.filter_edit)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(
            [self.tr("域名"), self.tr("条数")]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)     # 已按条数倒序排好，别让用户再排乱
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 56)
        for host, n in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(host))
            count_item = QTableWidgetItem(str(n))
            count_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(r, 1, count_item)
        root.addWidget(self.table, stretch=1)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(f"color: {theme.css('hint')};")
        root.addWidget(self.summary)
        self._update_summary(len(rows), ignored)

        btn_row = QHBoxLayout()
        self.select_all_btn = QPushButton(self.tr("全选"))
        self.clear_btn = QPushButton(self.tr("清空选择"))
        self.select_all_btn.clicked.connect(self.table.selectAll)
        self.clear_btn.clicked.connect(self.table.clearSelection)
        btn_row.addWidget(self.select_all_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch(1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            self.tr("加入列表")
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            self.tr("取消")
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        btn_row.addWidget(self.buttons)
        root.addLayout(btn_row)

        has_rows = bool(rows)
        for w in (self.select_all_btn, self.clear_btn,
                  self.buttons.button(QDialogButtonBox.StandardButton.Ok)):
            w.setEnabled(has_rows)
        self.filter_edit.setEnabled(has_rows)
        if not has_rows:
            self.summary.setText(
                self.tr("当前会话里没有新的域名可选（都已经在这个列表里了）")
            )

    # ------------------------------------------------------------ 结果

    def selected_domains(self) -> list[str]:
        """用户勾选的域名（保持表格里的顺序 / 原文）。"""
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        out = []
        for r in rows:
            item = self.table.item(r, 0)
            if item is not None and not self.table.isRowHidden(r):
                out.append(item.text())
        return out

    # ------------------------------------------------------------ 内部

    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            host = (item.text() if item is not None else "").lower()
            self.table.setRowHidden(r, bool(needle) and needle not in host)

    def _update_summary(self, shown: int, ignored: int) -> None:
        base = self.tr('当前会话里有 {0} 个域名可加入（按条数倒序）').format(shown)
        if ignored:
            base += self.tr('；另有 {0} 个已在列表里或被现有域名覆盖').format(
                ignored
            )
        base += self.tr('；可多选，确定后增量追加到这里')
        self.summary.setText(base)


class FilterPanel(QWidget):
    """域名过滤页：两个列表 + 启用开关 + 类型隐藏 + 预设入口。"""

    #: 任意编辑（含列表增删、开关切换）→ 主窗口落盘并推模型
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False       # 灌配置时屏蔽信号，避免把加载当成编辑
        self._host_provider = None  # 注入式数据源：当前会话 host → 条数

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addWidget(self._build_switch_box())
        # 两个列表上下排（详情面板默认只有 ~300px 宽，并排会让域名列被压成
        # 一屏放不下几个字）；用竖向 Splitter 让用户按需调整两边的比例。
        lists_split = QSplitter(Qt.Orientation.Vertical)
        lists_split.setChildrenCollapsible(False)
        lists_split.addWidget(self._build_list_box(LIST_BLACK))
        lists_split.addWidget(self._build_list_box(LIST_WHITE))
        lists_split.setSizes([1, 1])
        root.addWidget(lists_split, stretch=1)
        root.addWidget(self._build_hint())

        self.switch_combo.currentIndexChanged.connect(self._on_changed)
        self.hide_connect_cb.toggled.connect(self._on_changed)
        self.hide_image_cb.toggled.connect(self._on_changed)

    # ------------------------------------------------------------ 构建

    def _build_switch_box(self) -> QGroupBox:
        box = QGroupBox(self.tr("域名过滤"))
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        # 第一行：启用开关。**必须单独一行**：详情面板常态只有 ~300px 宽，
        # 「启用: + 三态下拉 + 两个复选框」挤一排会把复选框整体挤出面板外
        # （实测 300px 时溢出 208px，直接被裁掉看不见）。
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(self.tr("启用:")))
        self.switch_combo = QComboBox()
        self.switch_combo.addItem(
            self.tr("关闭"), SWITCH_OFF
        )
        self.switch_combo.addItem(
            self.tr("黑名单（隐藏这些域名）"), LIST_BLACK
        )
        self.switch_combo.addItem(
            self.tr("白名单（只显示这些域名）"), LIST_WHITE
        )
        self.switch_combo.setToolTip(
            self.tr("三态互斥：一次只启用黑名单或白名单，关掉则两个列表都不生效")
        )
        # 下限按最长条目估；上方 stretch 兜底，窄屏下优先压缩的是留白，
        # 下拉自己只会缩到内容宽度（QComboBox 省略号截断），不会挤坏别的控件。
        self.switch_combo.setMinimumWidth(150)
        row.addWidget(self.switch_combo)
        row.addStretch(1)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(12)
        self.hide_connect_cb = QCheckBox(self.tr("隐藏 CONNECT"))
        self.hide_image_cb = QCheckBox(self.tr("隐藏 Image"))
        self.hide_connect_cb.setToolTip(
            self.tr("隐藏 HTTPS 隧道的 CONNECT 请求，只看真实的 HTTP 会话")
        )
        self.hide_image_cb.setToolTip(
            self.tr("按 content-type 与扩展名识别图片请求并隐藏")
        )
        row2.addWidget(self.hide_connect_cb)
        row2.addWidget(self.hide_image_cb)
        row2.addStretch(1)
        layout.addLayout(row2)
        return box

    def _build_list_box(self, which: str) -> QGroupBox:
        if which == LIST_BLACK:
            title = self.tr("黑名单（命中的域名隐藏）")
            tip = self.tr("域名加入这里后，命中它的请求不再显示在流量列表")
        else:
            title = self.tr("白名单（只显示命中的域名）")
            tip = self.tr("只显示命中这里的请求，其余全部隐藏；留空 = 不过滤")
        box = QGroupBox(title)
        box.setToolTip(tip)
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        table = _DomainTable(self)
        layout.addWidget(table, stretch=1)

        row = QHBoxLayout()
        row.setSpacing(6)
        edit = QLineEdit()
        edit.setClearButtonEnabled(True)
        edit.setPlaceholderText(self.tr("域名，如 example.com，回车添加"))
        edit.setToolTip(self.tr("回车或点「添加」追加；域名会同时覆盖它的子域"))
        edit.returnPressed.connect(lambda: self._on_add(which))
        add_btn = QPushButton(self.tr("添加"))
        add_btn.setToolTip(self.tr("追加到列表（增量，不会覆盖已有内容）"))
        add_btn.clicked.connect(lambda: self._on_add(which))
        row.addWidget(edit, stretch=1)
        row.addWidget(add_btn)
        layout.addLayout(row)

        # 第二排：批量入口 + 删除。分两排是因为详情面板常态宽度只有 ~300px，
        # 三个按钮加输入框挤一排会把输入框压得只剩几十像素。
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        pick_btn = QPushButton(self.tr("从流量选…"))
        pick_btn.setToolTip(
            self.tr("列出当前会话里出现过的域名（带条数），勾选后批量追加到这里")
        )
        pick_btn.clicked.connect(lambda: self._on_pick(which))
        del_btn = QPushButton(self.tr("删除选中"))
        del_btn.clicked.connect(lambda: self._on_delete(which))
        row2.addWidget(pick_btn)
        row2.addWidget(del_btn)
        row2.addStretch(1)
        layout.addLayout(row2)

        if which == LIST_BLACK:
            self.black_table = table
            self.black_input = edit
            self.black_del_btn = del_btn
            self.black_pick_btn = pick_btn
        else:
            self.white_table = table
            self.white_input = edit
            self.white_del_btn = del_btn
            self.white_pick_btn = pick_btn
        return box

    def _build_hint(self) -> QLabel:
        hint = QLabel(QCoreApplication.translate("FilterPanel", HINT_TEXT))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.css('hint')};")
        return hint

    # ------------------------------------------------------------ 数据源

    def set_host_provider(self, provider) -> None:
        """注入「当前会话 host → 条数」的数据源。

        会话数据由主窗口持有（``FlowStore``），这里不持有业务对象、也不 import
        主窗口，只认一个可调用对象——offscreen 单测塞个假 dict 就能跑。
        命中数刷新与「从流量选…」共用这一份口径。
        """
        self._host_provider = provider

    # ------------------------------------------------------------ 配置同步

    def load_config(self, config: FilterConfig) -> None:
        """从外部灌入配置（启动恢复 / 顶部栏改 / 套用预设都走这里）。"""
        self._loading = True
        try:
            if config.enabled:
                idx = self.switch_combo.findData(config.active_list)
            else:
                idx = self.switch_combo.findData(SWITCH_OFF)
            self.switch_combo.setCurrentIndex(max(idx, 0))
            self.hide_connect_cb.setChecked(config.hide_connect)
            self.hide_image_cb.setChecked(config.hide_image)
            self._fill_table(self.black_table, config.blacklist)
            self._fill_table(self.white_table, config.whitelist)
            self._update_del_enabled()
        finally:
            self._loading = False

    def to_config(self) -> FilterConfig:
        data = self.switch_combo.currentData()
        return FilterConfig(
            blacklist=self._entries(self.black_table),
            whitelist=self._entries(self.white_table),
            enabled=data != SWITCH_OFF,
            active_list=LIST_BLACK if data == LIST_BLACK else LIST_WHITE,
            hide_connect=self.hide_connect_cb.isChecked(),
            hide_image=self.hide_image_cb.isChecked(),
        )

    def _fill_table(self, table: QTableWidget, entries) -> None:
        table.setRowCount(0)
        for e in entries:
            self._append_row(table, e)

    def _append_row(self, table: QTableWidget, entry: str) -> None:
        row = table.rowCount()
        table.insertRow(row)
        name_item = QTableWidgetItem(entry)
        name_item.setFlags(
            name_item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )
        count_item = QTableWidgetItem("")
        count_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        count_item.setFlags(count_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row, 0, name_item)
        table.setItem(row, 1, count_item)

    def _entries(self, table: QTableWidget) -> list[str]:
        return [
            table.item(r, 0).text()
            for r in range(table.rowCount())
            if table.item(r, 0) is not None
        ]

    # ------------------------------------------------------------ 命中数

    def update_counts(self, host_counts: Counter) -> None:
        """按当前流量刷新每个域名的命中数（主窗口在流量变化时调）。

        ``host_counts`` 是 host → 条数的计数器；空白名单 / 空流量时显示空。

        匹配走索引，不再「每条名单条目 × 每个 host」暴力比对：把 host 拆成它
        自己的各级后缀（``a.b.c`` → ``a.b.c`` / ``b.c`` / ``c``），名单里带点的
        条目按域名登记进 dict 查一次即可命中。原先是 O(条目数 × host 数) 且每次
        都要调函数 + 做字符串运算，名单攒到几十条、会话上千时每次防抖刷新都会
        肉眼可见地卡一下。
        """
        for table in (self.black_table, self.white_table):
            _apply_counts(table, host_counts or {})

    # ------------------------------------------------------------ 交互

    def _on_add(self, which: str) -> None:
        edit = self.black_input if which == LIST_BLACK else self.white_input
        text = edit.text()
        # 逗号 / 分号 / 空白都能分隔，和顶部过滤栏的输入口径一致
        raw = [p for p in text.replace(";", ",").replace("\n", ",").split(",")]
        domains = [normalize_domain(p) for p in raw]
        if self._append_domains(which, domains):
            edit.clear()

    def _on_pick(self, which: str) -> None:
        """从当前会话挑域名批量加入（「选 20 个请求一次性加黑名单」场景）。

        名单数据来源由外部注入（``set_host_provider``）：过滤页不持有会话，
        只认一个「返回 host→条数」的可调用对象，便于 offscreen 单测。
        """
        provider = getattr(self, "_host_provider", None)
        counts = provider() if provider is not None else {}
        table = self.black_table if which == LIST_BLACK else self.white_table
        dlg = _DomainPickerDialog(counts, self._entries(table), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._append_domains(which, dlg.selected_domains())

    def _append_domains(self, which: str, domains) -> bool:
        """把域名增量追加进指定列表，返回是否真的有新增（决定要不要清输入框）。

        去重交给 ``add_domains``：列表已经是 Append 语义，重复项不会被塞进来。
        """
        table = self.black_table if which == LIST_BLACK else self.white_table
        wanted = [d for d in (domains or []) if d]
        if not wanted:
            return False
        existing = self._entries(table)
        merged = add_domains(existing, wanted)
        added = merged[len(existing):]
        if not added:
            return False
        self._fill_table(table, merged)
        self._on_changed()
        self._update_del_enabled()
        return True

    def _on_delete(self, which: str) -> None:
        table = self.black_table if which == LIST_BLACK else self.white_table
        rows = sorted({i.row() for i in table.selectedIndexes()})
        if not rows:
            return
        for r in reversed(rows):
            table.removeRow(r)
        self._on_changed()
        self._update_del_enabled()

    def _on_changed(self) -> None:
        if self._loading:
            return
        self._update_del_enabled()
        self.changed.emit()

    def _update_del_enabled(self) -> None:
        for btn, table in (
            (self.black_del_btn, self.black_table),
            (self.white_del_btn, self.white_table),
        ):
            has = bool(table.selectedIndexes())
            btn.setEnabled(has)
