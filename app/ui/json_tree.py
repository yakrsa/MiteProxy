"""JSON 树形视图控件（详情面板「树」页签 / WebSocket 消息共用）。

为什么自己写 ``QAbstractItemModel`` 而不用 ``QTreeWidget``：后者必须在建树时
一次性 new 出全部 QTreeWidgetItem（实测 18 万节点 208ms + 107MB 常驻），而代理抓
到的响应可以任意大。自己写模型可以让**没展开的容器不产生行**——QTreeView 只对
可见层级调 ``rowCount``，于是 20 万节点的文档打开瞬间只实例化几十个 Node。

两条硬约束：

1. **只读**：树是解析后的视图，重复键已被 ``json.loads`` 覆盖、浮点形态也已改写，
   所以这里不能编辑，更不能替代原文视图。
2. **搜索必须落到行上**：BodyPane.highlight() 对文本走 QTextDocument.find，对表格
   遍历 item，这里得自己实现一套（``highlight()``）。漏了就是「树视图里搜不到东西」。
"""

from __future__ import annotations

from collections import deque
from typing import Iterable

from PySide6.QtCore import (
    QAbstractItemModel,
    QCoreApplication,
    QModelIndex,
    QPoint,
    Qt,
)
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QHeaderView, QMenu, QTreeView, QWidget

from app.jsontree import (
    VALUE_PREVIEW_LIMIT,
    JsonNode,
    JsonTreeError,
    parse_tree,
    walk,
)
from app.ui import theme
from app.ui.highlight import JSON_COLORS_DARK, JSON_COLORS_LIGHT, is_dark

#: 第 1 列默认宽度。不用 Stretch——键列跟随内容会把整棵树挤变形；值列才拉伸。
KEY_COLUMN_WIDTH = 220

#: 搜索只保留这么多命中：再多既没有展示价值，展开祖先也会变慢
SEARCH_HIT_LIMIT = 500

#: 超过这么多命中就不逐个定位（只报告数量），避免 setExpanded 刷爆
SEARCH_EXPAND_LIMIT = 200

#: 自动展开的第 2 层子节点数上限（见 _default_expand）
AUTO_EXPAND_CHILDREN = 100


def _palette(widget: QWidget | None) -> dict[str, str]:
    """取当前深浅配套的 JSON 配色（与文本视图 JsonHighlighter 同一套）。

    刻意**不走 ``self.parent()``**：模型类重写了 ``parent(index)``（QAbstractItemModel
    协议），把 QObject.parent() 遮蔽了——调用它会拿到一个 QModelIndex，再交给
    需要 QWidget 的取色函数就是段错误（排查过一轮，症状伪装成 GC 内存损坏）。
    所以深浅判断需要显式持有控件引用，见 JsonTreeModel._widget。
    """
    dark = is_dark(widget) if widget is not None else theme.is_dark_app()
    return JSON_COLORS_DARK if dark else JSON_COLORS_LIGHT


def _type_color(node: JsonNode, widget: QWidget | None) -> QColor:
    """按 JSON 类型取前景色。"""
    kind = node.type_name
    if kind == "string":
        return QColor(_palette(widget)["string"])
    if kind == "number":
        return QColor(_palette(widget)["number"])
    if kind == "boolean":
        return QColor(_palette(widget)["keyword"])
    # array / object / null / unknown 统一用次要色：容器没有"值"可染色，
    # null 染成别的色反而让人以为有内容
    return theme.color("hint")


class JsonTreeModel(QAbstractItemModel):
    """三列（键 / 类型 / 值）的树模型，子节点懒加载。

    「类型」列是 Fiddler 风格的补强：每个节点直接显示 object / array /
    string / number / boolean / null，结构一眼看清，不用把鼠标悬到 tooltip 上
    才看得出类型。类型紧挨着键、值列吃满剩余宽度——否则窗口一拉宽，类型列会被
    挤到最右边，看键和类型要横跨半个屏幕。
    """

    KEY_COL = 0
    TYPE_COL = 1
    VALUE_COL = 2

    def __init__(self, root: JsonNode, widget: QWidget | None = None, parent=None):
        super().__init__(parent)
        self._root = root
        #: 持有取色用的控件引用——不能用 self.parent()（被 parent(index) 遮蔽）
        self._widget = widget
        self._hits: set[int] = set()
        # internalPointer 是**裸指针**：直接塞 Python 对象的话，节点又是循环引用
        # （parent ↔ children），GC 一轮就可能回收它，之后 Qt 再来取值就是段错误
        # （实测：禁用 GC 不崩、开启必崩）。所以这里用 int id 当指针值，
        # 并用注册表持有对象本体——节点在有生之年不会被回收，指针永不悬空。
        self._registry: dict[int, JsonNode] = {}
        self._mono = QFont("ui-monospace, SF Mono, Menlo, Consolas, monospace")
        self._mono.setStyleHint(QFont.StyleHint.Monospace)

    # ------------------------------------------------------------ 节点 ↔ 指针

    def _pointer(self, node: JsonNode) -> int:
        key = id(node)
        self._registry[key] = node          # 顺带钉住对象本体
        return key

    def _node_of(self, index: QModelIndex) -> JsonNode | None:
        if not index.isValid():
            return None
        return self._registry.get(index.internalId())

    # ------------------------------------------------------------ Qt 模型协议

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if parent.isValid():
            node = self._node_of(parent)
            if node is None:
                return QModelIndex()
            rows = node.rows()
        else:
            rows = [self._root]                        # 顶层只有根节点一行
        if row >= len(rows):
            return QModelIndex()
        return self.createIndex(row, column, self._pointer(rows[row]))

    def parent(self, index: QModelIndex = QModelIndex()) -> QModelIndex:
        node = self._node_of(index)
        if node is None or node.parent is None:        # 顶层根节点 → 无父
            return QModelIndex()
        return self.createIndex(node.parent.row, 0, self._pointer(node.parent))

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            return 1                                   # 只有根节点
        node = self._node_of(parent)
        if node is None:
            return 0
        return len(node.rows()) if node.is_container else 0

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 3

    def hasChildren(self, parent: QModelIndex = QModelIndex()) -> bool:
        if not parent.isValid():
            return True
        node = self._node_of(parent)
        if node is None:
            return False
        # 只看长度不实例化子节点——这正是「大文档打开不卡」的关键
        return node.is_container and node.child_count > 0

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        node = self._node_of(index)
        if node is None:
            return None
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == self.KEY_COL:
                return node.label
            if column == self.VALUE_COL:
                return node.value_text
            return node.type_name
        if role == Qt.ItemDataRole.ForegroundRole:
            if column == self.KEY_COL:
                # 只有真正的「键」才染色；数组下标 [0] 走次要色
                if node.index is None:
                    return QBrush(QColor(_palette(self._widget)["key"]))
                return QBrush(theme.color("hint"))
            # 值列与类型列都按 JSON 类型染色（类型列一眼看出 object/array…）
            return QBrush(_type_color(node, self._widget))
        if role == Qt.ItemDataRole.FontRole and column == self.VALUE_COL:
            return self._mono
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(node)
        if role == Qt.ItemDataRole.BackgroundRole and id(node) in self._hits:
            return QBrush(theme.color("hit_bg"))
        if role == Qt.ItemDataRole.UserRole:
            return node.path
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation != Qt.Orientation.Horizontal:
            return None
        if section == self.KEY_COL:
            return QCoreApplication.translate("JsonTreeModel", "键")
        if section == self.VALUE_COL:
            return QCoreApplication.translate("JsonTreeModel", "值")
        return QCoreApplication.translate("JsonTreeModel", "类型")

    # ------------------------------------------------------------ 工具

    def _tooltip(self, node: JsonNode) -> str:
        path = QCoreApplication.translate("JsonTreeModel", "路径：{0}").format(node.path)
        if node.is_container:
            kind = QCoreApplication.translate("JsonTreeModel", "对象（{0} 个键）") \
                if isinstance(node.value, dict) else \
                QCoreApplication.translate("JsonTreeModel", "数组（{0} 项）")
            return f"{path}\n{kind.format(node.child_count)}"
        text = node.full_text
        if len(text) > VALUE_PREVIEW_LIMIT:
            tail = QCoreApplication.translate(
                "JsonTreeModel", "\n（共 {0} 字符，双击或右键复制完整值）"
            ).format(len(text))
            return f"{path}\n{text[:VALUE_PREVIEW_LIMIT * 4]}…{tail}"
        return f"{path}\n{text}"

    def node_at(self, index: QModelIndex) -> JsonNode | None:
        return self._node_of(index)

    def index_for_node(self, node: JsonNode) -> QModelIndex:
        """把节点变回 QModelIndex（沿 parent 链往下走；已展开过才拿得到）。"""
        chain: list[JsonNode] = []
        cur: JsonNode | None = node
        while cur is not None:
            chain.append(cur)
            cur = cur.parent
        idx = QModelIndex()
        for n in reversed(chain):                      # 从根往下
            idx = self.index(n.row, self.KEY_COL, idx)
        return idx

    def find_nodes(self, term: str, case_sensitive: bool = False,
                   limit: int = SEARCH_HIT_LIMIT) -> list[JsonNode]:
        """遍历全部节点找命中（键或值包含 term）。**这一步会实例化所有子节点**。"""
        if not term:
            return []
        needle = term if case_sensitive else term.lower()
        hits: list[JsonNode] = []
        for node in walk(self._root):
            hay = node.key if case_sensitive else node.key.lower()
            if needle in hay:
                hits.append(node)
            elif not node.is_container:
                val = node.full_text if case_sensitive else node.full_text.lower()
                if needle in val:
                    hits.append(node)
            if len(hits) >= limit:
                break
        return hits

    def set_hits(self, nodes: Iterable[JsonNode]) -> None:
        self._hits = {id(n) for n in nodes}


class JsonTreeView(QTreeView):
    """展示 + 交互：展开收起、搜索联动、右键复制。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model: JsonTreeModel | None = None
        self.setAlternatingRowColors(False)
        self.setUniformRowHeights(True)               # 行高固定 → 滚动性能显著更好
        self.setRootIsDecorated(True)
        self.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_menu)

    # ------------------------------------------------------------ 数据

    def set_root(self, root: JsonNode | None) -> None:
        """换数据源。``None`` = 清空（切换会话时释放上一棵树）。"""
        if root is None:
            # 换会话 / 清空：模型是 Qt 子对象（构造传了 self），置空即可回收
            self._model = None
            self.setModel(None)
            return
        self._model = JsonTreeModel(root, widget=self, parent=self)
        self.setModel(self._model)
        header = self.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setColumnWidth(self._model.KEY_COL, KEY_COLUMN_WIDTH)
        header.setSectionResizeMode(self._model.VALUE_COL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self._model.TYPE_COL, QHeaderView.ResizeMode.ResizeToContents)
        self._default_expand()

    def clear(self) -> None:
        self.set_root(None)

    def _default_expand(self) -> None:
        """默认展开：根节点必展开，第 2 层只在子节点不多时展开。

        不整体展开是为了大数组（比如 2000 条 item）——全展开既慢又没人看得完。
        """
        model = self._model
        if model is None:
            return
        root_index = model.index(0, model.KEY_COL, QModelIndex())
        if not root_index.isValid():
            return
        self.expand(root_index)
        if model.rowCount(root_index) > 20:
            return
        for row in range(model.rowCount(root_index)):
            child = model.index(row, model.KEY_COL, root_index)
            node = model.node_at(child)
            if node is not None and 0 < node.child_count <= AUTO_EXPAND_CHILDREN:
                self.expand(child)

    def expand_to_level(self, level: int) -> None:
        """展开到第 level 层（根为第 0 层，即 nodes at depth==level 可见）。

        用于大 JSON 快速钻取：比「全部展开」温和——只逐层展开到指定深度。
        护栏与 ``_default_expand`` 一致：某节点自身子节点超过
        ``AUTO_EXPAND_CHILDREN`` 就不再展开它（一展开就是几千行，
        实例化与滚动都白花），它的子分支保持折叠但可见。
        """
        model = self._model
        if model is None or level < 0:
            return
        self.collapseAll()
        root_index = model.index(0, model.KEY_COL, QModelIndex())
        if not root_index.isValid():
            return
        self.expand(root_index)
        if level == 0:
            return
        # 广度优先逐层展开：要看到 depth==level 的节点，必须展开所有 depth<level
        queue: deque[tuple[QModelIndex, int]] = deque([(root_index, 0)])
        while queue:
            idx, depth = queue.popleft()
            if depth >= level:
                continue
            node = model.node_at(idx)
            if node is None or node.child_count > AUTO_EXPAND_CHILDREN:
                continue
            self.expand(idx)
            for row in range(model.rowCount(idx)):
                child = model.index(row, model.KEY_COL, idx)
                if child.isValid():
                    queue.append((child, depth + 1))

    # ------------------------------------------------------------ 搜索

    def highlight(self, term: str, case_sensitive: bool = False) -> int:
        """高亮命中并计数（返回命中数），语义对齐 BodyPane.highlight()。"""
        model = self._model
        if model is None:
            return 0
        model.set_hits([])
        self.clearSelection()
        if not term:
            self.viewport().update()
            return 0
        hits = model.find_nodes(term, case_sensitive)
        model.set_hits(hits)
        if len(hits) <= SEARCH_EXPAND_LIMIT:
            # 逐命中地展开祖先：不然「搜到了 3 处」但一条都看不见
            for node in hits:
                idx = model.index_for_node(node)
                ancestor = idx.parent()
                while ancestor.isValid():
                    self.expand(ancestor)
                    ancestor = ancestor.parent()
            if hits:
                first = model.index_for_node(hits[0])
                if first.isValid():
                    self.setCurrentIndex(first)
                    self.scrollTo(first)
        self.viewport().update()
        return len(hits)

    # ------------------------------------------------------------ 复制 / 菜单

    def current_node(self) -> JsonNode | None:
        model = self._model
        if model is None:
            return None
        idx = self.currentIndex()
        return model.node_at(idx) if idx.isValid() else None

    def _copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    def copy_value(self) -> None:
        node = self.current_node()
        if node is None:
            return
        self._copy(node.subtree_json() if node.is_container else node.full_text)

    def copy_key(self) -> None:
        node = self.current_node()
        if node is not None:
            self._copy(node.key)

    def copy_path(self) -> None:
        node = self.current_node()
        if node is not None:
            self._copy(node.path)

    def copy_subtree(self) -> None:
        node = self.current_node()
        if node is not None:
            try:
                self._copy(node.subtree_json())
            except (TypeError, ValueError):
                # NaN/循环引用之类：json.dumps 会拒 —退化成 str()，总比什么都不给好
                self._copy(str(node.value))

    def keyPressEvent(self, event):  # noqa: N802
        """Cmd/Ctrl+C 复制当前行（树默认不处理，用户一定会尝试）。"""
        if event.matches(QKeySequence.StandardKey.Copy):
            node = self.current_node()
            if node is not None:
                self._copy(node.full_text if not node.is_container
                           else node.subtree_json())
                event.accept()
                return
        super().keyPressEvent(event)

    def _on_menu(self, pos: QPoint) -> None:
        node = self.current_node()
        if node is None:
            return
        menu = QMenu(self)
        act_value = QAction(self.tr("复制值"), self)
        act_key = QAction(self.tr("复制键"), self)
        act_path = QAction(self.tr("复制路径"), self)
        act_json = QAction(self.tr("复制整个节点（JSON）"), self)
        act_expand = QAction(self.tr("全部展开"), self)
        act_collapse = QAction(self.tr("全部收起"), self)
        for act, slot in ((act_value, self.copy_value), (act_key, self.copy_key),
                          (act_path, self.copy_path), (act_json, self.copy_subtree),
                          (act_expand, self.expandAll), (act_collapse, self.collapseAll)):
            act.triggered.connect(slot)
            menu.addAction(act)
        menu.exec(self.viewport().mapToGlobal(pos))


def build_tree(body: bytes) -> JsonNode:
    """便捷入口：bytes → 树根（失败抛 JsonTreeError，由调用方决定怎么提示）。"""
    return parse_tree(body)


__all__ = ["JsonTreeModel", "JsonTreeView", "JsonTreeError", "build_tree", "parse_tree"]
