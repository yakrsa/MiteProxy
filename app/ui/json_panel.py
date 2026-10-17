"""JSON 工具页：格式化（对齐 json.cn）+ 树形浏览 + JSONPath 提取。

这里刻意重用了 body 视图踩坑后定下的那几条规矩：

- **失败绝不吞内容**：非法 JSON 时右侧照样显示原文并在下方面板给出定位
  （第几行第几列 + 出错行 + `^` 指针 + 可能原因），而不是只丢一句英文报错。
- **先完整解析、只截断渲染结果**：解析 4MB 只要约 30ms，卡的是渲染，
  所以闸门放在着色（>256KB 关）与换行（单行 >64KB 关）上。
- **深嵌套不会崩**：`RecursionError` 不是 `ValueError` 子类，解析与树遍历
  都做了防护（遍历本身也用迭代实现）。
- **提示文案不叠加**：状态区每次整体重画（`_paint_status`），不在旧文本上追加。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QCoreApplication, QT_TRANSLATE_NOOP
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.bodyview import (
    BODY_PREVIEW_LIMIT as LIVE_LIMIT,
    HIGHLIGHT_LIMIT,
    RENDER_TEXT_LIMIT,
    WRAP_MAX_LINE_CHARS,
    longest_line,
    truncation_note,
)
from app.jsonpath import find as jsonpath_find
from app.jsonutil import (
    ParseResult,
    count_nodes,
    dumps_json,
    max_depth,
    parse_json,
)
from app.ui.highlight import JsonHighlighter, is_dark
from app.ui import theme

#: 树视图**已构建**节点总数上限（懒加载下按展开量计）：超过就暂停填充并提示
TREE_NODE_LIMIT = 5000
#: 单个节点子项填充上限：展开一个 10 万元素的数组也不至于把列表铺满
TREE_CHILD_LIMIT = 5000

INDENT_ITEMS = (
    (QT_TRANSLATE_NOOP("JsonPanel", "2 空格"), 2),
    (QT_TRANSLATE_NOOP("JsonPanel", "4 空格"), 4),
    (QT_TRANSLATE_NOOP("JsonPanel", "Tab"), "\t"),
)

VIEW_TEXT = "text"
VIEW_TREE = "tree"
VIEW_PATH = "path"

JSONPATH_TIP = QT_TRANSLATE_NOOP(
    "JsonPanel",
    "常用写法：\n"
    "  $.data.list[0].name        取字段\n"
    "  $.data.list[-1]            最后一个\n"
    "  $.data.list[0:5]           切片\n"
    "  $.data.list[*].id          所有元素的 id\n"
    "  $..token                   所有层级里叫 token 的字段\n"
    "  $.list[?(@.price > 10)]    过滤（&& || 组合，=~ 正则）\n"
    "  $['a','b']、$[0,1]         一次取多个\n"
)


def _mono_font() -> QFont:
    font = QFont("ui-monospace, SF Mono, Menlo, Consolas, monospace")
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


class JsonPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = _mono_font()
        self._parsed: ParseResult | None = None
        self._value: object = None
        self._matches: list = []
        self._last_error = None
        self._tree_nodes_built = 0   # 懒加载计数（见 _fill_children）
        self._tree_truncated = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addLayout(self._build_toolbar())
        root.addWidget(self._build_splitter(), stretch=1)
        root.addLayout(self._build_path_row())
        root.addWidget(self._build_status())

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self._auto_format)

        self.input_edit.textChanged.connect(self._schedule)
        self._on_view_changed()      # 让按钮可用状态与初始视图一致
        self._update_counts()

    # ------------------------------------------------------------ 构建

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        self.format_btn = QPushButton(self.tr("格式化"))
        self.format_btn.clicked.connect(lambda: self.run(mode="pretty"))
        row.addWidget(self.format_btn)

        self.minify_btn = QPushButton(self.tr("压缩"))
        self.minify_btn.clicked.connect(lambda: self.run(mode="minify"))
        row.addWidget(self.minify_btn)

        self.check_btn = QPushButton(self.tr("校验"))
        self.check_btn.setToolTip(self.tr("只判断合法性与规模，不渲染内容（超大 JSON 用这个）"))
        self.check_btn.clicked.connect(lambda: self.run(mode="check"))
        row.addWidget(self.check_btn)

        row.addSpacing(10)
        row.addWidget(QLabel(self.tr("缩进:")))
        self.indent_combo = QComboBox()
        for label, value in INDENT_ITEMS:
            self.indent_combo.addItem(
                QCoreApplication.translate("JsonPanel", label), value)
        self.indent_combo.setCurrentIndex(0)
        self.indent_combo.currentIndexChanged.connect(lambda *_: self.run())
        row.addWidget(self.indent_combo)

        row.addWidget(QLabel(self.tr("视图:")))
        self.view_combo = QComboBox()
        self.view_combo.addItem(self.tr("格式化文本"), VIEW_TEXT)
        self.view_combo.addItem(self.tr("树形"), VIEW_TREE)
        self.view_combo.addItem(self.tr("JSONPath 结果"), VIEW_PATH)
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        row.addWidget(self.view_combo)

        self.expand_btn = QPushButton(self.tr("展开全部"))
        self.expand_btn.clicked.connect(self._expand_all)
        row.addWidget(self.expand_btn)
        self.collapse_btn = QPushButton(self.tr("折叠全部"))
        self.collapse_btn.clicked.connect(self._collapse_all)
        row.addWidget(self.collapse_btn)

        self.wrap_cb = QCheckBox(self.tr("换行"))
        self.wrap_cb.setChecked(True)
        self.wrap_cb.setToolTip(
            self.tr('单行超过 {0}KB 时会自动临时关闭（换行对超长单行是超线性开销）').format(WRAP_MAX_LINE_CHARS // 1024)
        )
        self.wrap_cb.toggled.connect(self._on_wrap_toggled)
        row.addWidget(self.wrap_cb)

        row.addStretch(1)

        self.copy_btn = QPushButton(self.tr("复制结果"))
        self.copy_btn.clicked.connect(self.copy_result)
        row.addWidget(self.copy_btn)
        self.clear_btn = QPushButton(self.tr("清空"))
        self.clear_btn.clicked.connect(self._on_clear)
        row.addWidget(self.clear_btn)
        return row

    def _build_splitter(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        in_box = QGroupBox(self.tr("输入"))
        in_layout = QVBoxLayout(in_box)
        self.input_edit = QPlainTextEdit()
        self.input_edit.setFont(self._font)
        self.input_edit.setPlaceholderText(self.tr("把 JSON 贴进来，或用下面的 JSONPath 提取…"))
        in_layout.addWidget(self.input_edit)
        in_bar = QHBoxLayout()
        in_bar.addStretch(1)
        self.input_count = QLabel("")
        self.input_count.setStyleSheet(f"color: {theme.css('hint')};")
        in_bar.addWidget(self.input_count)
        in_layout.addLayout(in_bar)

        out_box = QGroupBox(self.tr("结果"))
        out_layout = QVBoxLayout(out_box)
        self.out_stack = QStackedWidget()

        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setFont(self._font)
        self._highlighter = JsonHighlighter(self.text_view.document())
        self.out_stack.addWidget(self.text_view)

        self.tree_view = QTreeWidget()
        self.tree_view.setColumnCount(3)
        self.tree_view.setHeaderLabels([self.tr("名称"), self.tr("值"), self.tr("类型")])
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tree_view.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        # 懒加载：容器节点首次展开时才构建子节点（itemExpanded 信号），
        # 大数组/大对象不再一次性铺开几百毫秒
        self.tree_view.itemExpanded.connect(self._on_tree_expanded)
        self.out_stack.addWidget(self.tree_view)

        self.path_table = QTableWidget(0, 3)
        self.path_table.setHorizontalHeaderLabels(["#", self.tr("路径"), self.tr("值")])
        self.path_table.verticalHeader().setVisible(False)
        self.path_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.path_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.path_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.out_stack.addWidget(self.path_table)

        out_layout.addWidget(self.out_stack)
        out_bar = QHBoxLayout()
        out_bar.addStretch(1)
        self.output_count = QLabel("")
        self.output_count.setStyleSheet(f"color: {theme.css('hint')};")
        out_bar.addWidget(self.output_count)
        out_layout.addLayout(out_bar)

        splitter.addWidget(in_box)
        splitter.addWidget(out_box)
        splitter.setSizes([500, 500])
        return splitter

    def _build_path_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(QLabel("JSONPath:"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(
            "$.data.list[0].name   $..token   $.l[*].p.max()"
        )
        self.path_edit.setToolTip(
            QCoreApplication.translate("JsonPanel", JSONPATH_TIP))
        self.path_edit.returnPressed.connect(self.run_jsonpath)
        row.addWidget(self.path_edit, stretch=1)

        self.path_btn = QPushButton(self.tr("提取"))
        self.path_btn.setToolTip(
            QCoreApplication.translate("JsonPanel", JSONPATH_TIP))
        self.path_btn.clicked.connect(self.run_jsonpath)
        row.addWidget(self.path_btn)

        self.path_copy_btn = QPushButton(self.tr("复制结果"))
        self.path_copy_btn.clicked.connect(self.copy_path_result)
        row.addWidget(self.path_copy_btn)
        return row

    def _build_status(self) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.status_label, stretch=1)
        self.goto_btn = QPushButton(self.tr("跳到出错位置"))
        self.goto_btn.setVisible(False)
        self.goto_btn.setToolTip(self.tr("把光标移到出错的行列"))
        self.goto_btn.clicked.connect(self._goto_error)
        layout.addWidget(self.goto_btn)
        self.status_label.setStyleSheet(f"color: {theme.css('hint')};")
        self._status_kind = "hint"      # 主题切换时按最近一次状态重染色
        theme.add_listener(self._retheme)
        return box

    # ------------------------------------------------------------ 对外

    def set_text(self, text: str) -> None:
        """外部灌入内容（右键菜单「在 JSON 工具里打开 body」）。"""
        self.input_edit.setPlainText(text)
        self.run(mode="pretty")

    @property
    def current_view(self) -> str:
        return self.view_combo.currentData() or VIEW_TEXT

    def run(self, mode: str = "pretty") -> None:
        """按 mode 处理：pretty（格式化）/ minify（压缩）/ check（只校验）。"""
        self._timer.stop()
        text = self.input_edit.toPlainText()
        if not text.strip():
            self._parsed = None
            self._value = None
            self.text_view.setPlainText("")
            self.tree_view.clear()
            self._set_status("", error=False)
            self._update_counts()
            return

        result = parse_json(text)
        self._parsed = result
        if not result.ok:
            self._value = None
            # 失败也要显示原文：内容不能因为解析不了就不见了
            self._show_text(result.text, colored=False)
            self.tree_view.clear()
            self._set_status(
                result.error.report() if result.error else self.tr("解析失败"),
                error=True,
                goto=result.error,
            )
            self._update_counts()
            return

        self._value = result.value
        notes = list(result.notes)

        if mode == "check":
            # 只报合法性，**不动输出**——否则切到树视图前的自动解析会把
            # 已经格式化好的文本清掉，用户切回「格式化文本」就白屏了
            self._set_status(
                self.tr('✓ 合法 JSON · {0} 个节点 · 最大深度 {1}').format(count_nodes(self._value), max_depth(self._value)),
                error=False,
                ok=True,
            )
            self._update_counts()
            return

        indent = self.indent_combo.currentData()
        ok, dumped = dumps_json(
            self._value, indent=None if mode == "minify" else indent
        )
        if not ok:
            self._show_text(result.text, colored=False)
            self._set_status(dumped, error=True)
            self._update_counts()
            return

        if mode == "minify":
            notes.append(self.tr("已压缩为单行（复制方便，看结构请切「格式化」）"))
        # _show_text 会顺带应用换行闸门，并返回「为什么没换行」
        wrap_note = self._show_text(dumped, colored=True)
        tree_note = self._render_tree_if_needed()

        extra = []
        if len(dumped) > RENDER_TEXT_LIMIT:
            extra.append(self.tr("结果过长已截断"))
        if wrap_note:
            extra.append(wrap_note)
        if tree_note:
            extra.append(tree_note)
        self._set_status(
            " · ".join([p for p in (self.tr('共 {0} 个节点').format(count_nodes(self._value)),
                                    self.tr('最大深度 {0}').format(max_depth(self._value)),
                                    *notes, *extra) if p]),
            error=False,
        )
        self._update_counts()

    def run_jsonpath(self) -> None:
        """执行 JSONPath：结果进「JSONPath 结果」视图。"""
        expr = self.path_edit.text().strip()
        if not expr:
            self._set_status(self.tr("请输入 JSONPath 表达式（如 $.data.list[0]）"), error=False)
            return
        if self._value is None:
            # 输入框内容还没解析过就先解析一次
            self.run(mode="check")
            if self._value is None:
                self._set_status(
                    self.tr("输入不是合法 JSON，先修好上面的错误再提取"), error=True
                )
                return
        matches, note = jsonpath_find(expr, self._value)
        if note and not matches:
            self._set_status(note, error=True)
            return
        self._matches = matches
        self._fill_path_table(matches)
        self.view_combo.setCurrentIndex(self.view_combo.findData(VIEW_PATH))
        if not matches:
            self._set_status(self.tr("没有匹配到任何内容"), error=False)
            return
        label = self.tr('共 {0} 处匹配').format(len(matches))
        if note:
            label += f" {note}"
        self._set_status(label, error=False, ok=True)

    def copy_result(self) -> bool:
        text = self.text_view.toPlainText()
        if not text:
            self._set_status(self.tr("结果为空，无可复制内容"), error=False)
            return False
        QApplication.clipboard().setText(text)
        self._set_status(self.tr('已复制 {0} 字符到剪贴板').format(len(text)), error=False)
        return True

    def copy_path_result(self) -> bool:
        if not self._matches:
            self._set_status(self.tr("没有可复制的提取结果"), error=False)
            return False
        ok, text = dumps_json([m.value for m in self._matches], indent=2)
        if not ok:
            self._set_status(text, error=True)
            return False
        QApplication.clipboard().setText(text)
        self._set_status(
            self.tr('已复制 {0} 个匹配值（JSON 数组）到剪贴板').format(len(self._matches)),
            error=False,
        )
        return True

    # ------------------------------------------------------------ 内部

    def _schedule(self) -> None:
        self._update_counts()
        if len(self.input_edit.toPlainText().encode("utf-8")) > LIVE_LIMIT:
            self._timer.stop()
            self._set_status(
                self.tr('内容超过 {0}KB，已暂停自动格式化——点「格式化」执行').format(LIVE_LIMIT // 1024),
                error=False,
            )
            return
        self._timer.start()

    def _auto_format(self) -> None:
        self.run(mode="pretty")

    def _show_text(self, text: str, *, colored: bool) -> str:
        """渲染文本，返回换行闸门的说明（没有就给空串）。

        返回而不是直接写状态区：调用方还要往状态里拼别的说明，
        这里写了会被随后的一次 `_set_status` 整段覆盖掉。
        """
        shown = text
        if len(shown) > RENDER_TEXT_LIMIT:
            shown = shown[:RENDER_TEXT_LIMIT] + truncation_note(
                len(text), limit=RENDER_TEXT_LIMIT
            )
        self.text_view.setPlainText(shown)
        # 着色是渲染侧最贵的一环（2 万行 ≈ 260ms），超阈值就关掉
        use_color = colored and len(shown) <= HIGHLIGHT_LIMIT
        self._highlighter.set_enabled(use_color, dark=is_dark(self.text_view))
        return self._apply_wrap()

    def _apply_wrap(self) -> str:
        want = self.wrap_cb.isChecked()
        longest = longest_line(self.text_view.toPlainText())
        wrap = want and longest <= WRAP_MAX_LINE_CHARS
        self.text_view.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if wrap else QPlainTextEdit.LineWrapMode.NoWrap
        )
        if want and not wrap:
            return (
                self.tr('单行最长 {0}KB 超过 {1}KB，已临时关闭换行').format(longest // 1024, WRAP_MAX_LINE_CHARS // 1024)
            )
        return ""

    def _on_wrap_toggled(self, _on: bool) -> None:
        note = self._apply_wrap()
        if note:
            self._append_note(note)
        else:
            # 重新换行了就把之前那条「已临时关闭换行」撤掉
            self._set_status(
                self.status_label.text().split(self.tr(" · 单行最长"))[0], error=False
            )

    def _render_tree_if_needed(self) -> str:
        if self.current_view != VIEW_TREE:
            return ""
        return self._render_tree()

    def _render_tree(self) -> str:
        """建树（懒加载：只建根节点，子节点在展开时填充）。

        返回而不是直接写状态区：调用方后面还要拼别的说明，这里写了会被
        随后的 `_set_status` 整段覆盖掉（踩过一次）。
        """
        self.tree_view.clear()
        self._tree_nodes_built = 0
        self._tree_truncated = False
        value = self._value
        if value is None:
            # 还没解析过（比如刚切过来、或自动格式化还没触发）就先解析一次
            if not self.input_edit.toPlainText().strip():
                return ""
            self.run(mode="check")
            value = self._value
            if value is None:
                return ""
        self._build_tree(self.tree_view, value, "$")
        self.tree_view.expandToDepth(2)
        return ""

    def _build_tree(self, tree: QTreeWidget, value: object, path: str) -> None:
        """只建根节点：容器挂上 (值, 路径) 待展开时填充，标量直接显示。"""
        root_item = QTreeWidgetItem(tree, ["$", "", _type_name(value)])
        root_item.setData(0, Qt.ItemDataRole.ToolTipRole, "$")
        if isinstance(value, (dict, list)):
            root_item.setText(1, self.tr('{0} 项').format(len(value)))
            root_item.setData(0, Qt.ItemDataRole.UserRole, (value, path))
            if value:
                root_item.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
                )
        else:
            root_item.setText(1, _scalar_text(value))

    def _on_tree_expanded(self, item: QTreeWidgetItem) -> None:
        """首次展开容器节点时才构建它的子节点（懒加载核心）。"""
        if item.childCount():
            return  # 已填充过（折叠再展开不重复建）
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if payload is None:
            return
        node, base = payload
        self._fill_children(item, node, base)

    def _fill_children(self, parent: QTreeWidgetItem, node: object, base: str) -> None:
        """构建 parent 的子节点；带上限（全局节点数 + 单层子项数）。"""
        if self._tree_truncated:
            return
        if isinstance(node, dict):
            children = [(str(k), v) for k, v in node.items()]
        elif isinstance(node, list):
            children = [(f"[{i}]", v) for i, v in enumerate(node)]
        else:
            return
        total = len(children)
        show = children[:TREE_CHILD_LIMIT] if total > TREE_CHILD_LIMIT else children
        for name, item in show:
            if self._tree_nodes_built >= TREE_NODE_LIMIT:
                self._tree_truncated = True
                self._append_note(
                    self.tr('树节点超过 {0}，更深处未展开（用 JSONPath 缩小范围）').format(TREE_NODE_LIMIT)
                )
                return
            self._tree_nodes_built += 1
            child_path = (
                f"{base}.{name}" if not name.startswith("[") else f"{base}{name}"
            )
            child = QTreeWidgetItem(parent, [name, "", _type_name(item)])
            child.setData(0, Qt.ItemDataRole.ToolTipRole, child_path)
            if isinstance(item, (dict, list)):
                child.setText(1, self.tr('{0} 项').format(len(item)))
                child.setData(0, Qt.ItemDataRole.UserRole, (item, child_path))
                if item:
                    child.setChildIndicatorPolicy(
                        QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
                    )
            else:
                child.setText(1, _scalar_text(item))
        if total > len(show):
            note = QTreeWidgetItem(
                parent,
                [self.tr('…（其余 {0} 项未显示）').format(total - len(show)), "", ""],
            )
            note.setDisabled(True)

    def _fill_path_table(self, matches: list) -> None:
        self.path_table.setRowCount(0)
        for index, match in enumerate(matches):
            row = self.path_table.rowCount()
            self.path_table.insertRow(row)
            self.path_table.setItem(row, 0, QTableWidgetItem(str(index)))
            path_item = QTableWidgetItem(match.path)
            path_item.setToolTip(match.path)
            self.path_table.setItem(row, 1, path_item)
            value_item = QTableWidgetItem(_scalar_text(match.value))
            value_item.setToolTip(_scalar_text(match.value, limit=4000))
            self.path_table.setItem(row, 2, value_item)

    def _on_view_changed(self, *_args) -> None:
        view = self.current_view
        self.out_stack.setCurrentWidget(
            {
                VIEW_TEXT: self.text_view,
                VIEW_TREE: self.tree_view,
                VIEW_PATH: self.path_table,
            }[view]
        )
        tree_mode = view == VIEW_TREE
        self.expand_btn.setEnabled(tree_mode)
        self.collapse_btn.setEnabled(tree_mode)
        if tree_mode:
            note = self._render_tree()
            if note:
                self._append_note(note)

    def _expand_all(self) -> None:
        self.tree_view.expandAll()

    def _collapse_all(self) -> None:
        self.tree_view.collapseAll()

    def _on_clear(self) -> None:
        self.input_edit.clear()
        self.path_edit.clear()
        self.text_view.clear()
        self.tree_view.clear()
        self.path_table.setRowCount(0)
        self._matches = []
        self._set_status("", error=False)
        self._update_counts()

    def _goto_error(self) -> None:
        error = getattr(self, "_last_error", None)
        if error is None:
            return
        cursor = self.input_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        for _ in range(max(error.lineno - 1, 0)):
            cursor.movePosition(cursor.MoveOperation.Down)
        for _ in range(max(error.colno - 1, 0)):
            cursor.movePosition(cursor.MoveOperation.Right)
        self.input_edit.setTextCursor(cursor)
        self.input_edit.setFocus()

    def _set_status(self, text: str, *, error: bool,
                    ok: bool = False, goto=None) -> None:
        self.status_label.setText(text)
        kind = "error" if error else ("ok" if ok else "hint")
        self._status_kind = kind
        self.status_label.setStyleSheet(f"color: {theme.css(kind)};")
        self._last_error = goto
        self.goto_btn.setVisible(goto is not None)

    def _retheme(self) -> None:
        """主题切换：字符计数与状态区重新染色，结果着色器按新主题重刷。"""
        self.input_count.setStyleSheet(f"color: {theme.css('hint')};")
        self.output_count.setStyleSheet(f"color: {theme.css('hint')};")
        self.status_label.setStyleSheet(f"color: {theme.css(self._status_kind)};")
        self._highlighter.set_enabled(
            self._highlighter.enabled, dark=is_dark(self.text_view)
        )

    def _append_note(self, note: str) -> None:
        """追加一条说明——**不叠加**：以状态区当前文本为基准重画一次。"""
        current = self.status_label.text()
        if note in current:
            return
        self.status_label.setText(f"{current} · {note}" if current else note)

    def _update_counts(self) -> None:
        def describe(text: str) -> str:
            if not text:
                return QCoreApplication.translate("JsonPanel", "0 字符")
            return QCoreApplication.translate("JsonPanel", "{0} 字符 / {1} 字节").format(len(text), len(text.encode("utf-8")))

        self.input_count.setText(describe(self.input_edit.toPlainText()))
        self.output_count.setText(describe(self.text_view.toPlainText()))


def _type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def _scalar_text(value: object, limit: int = 200) -> str:
    if isinstance(value, str):
        text = value
    elif isinstance(value, (dict, list)):
        ok, text = dumps_json(value)
        if not ok:
            text = str(value)
    elif value is None:
        text = "null"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value)
    text = text.replace("\n", "\\n").replace("\t", "\\t")
    return text if len(text) <= limit else text[:limit] + "…"
