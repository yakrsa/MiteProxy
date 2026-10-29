"""JSON → 树形视图的数据层（纯逻辑，不依赖 Qt）。

为什么不复用 ``bodyview.format_json_body()``：那条路产出的是**一段文本**，
树视图需要保留每个节点的父子关系与类型。两条诉求不同，各写一份反而更简单：

* 文本视图负责「和原文一字不差」——原文/JSON 页签的立身之本；
* 树视图负责「能折叠、能看结构」——本模块的职责。

两者互补，谁也替代不了谁（这也是树视图没有做成默认的原因）。

三个容易忽略的点：

1. **子节点懒加载**：``rows()`` 首次调用才展开并缓存。QTreeView 只对**可见
   层级**调 ``rowCount``，所以 20 万节点的文档打开瞬间只产生几十个 Node，
   而不是几十万个——这是树视图能撑住大响应的关键。
2. **重复键会丢**：``json.loads`` 遇到重复键时后者覆盖前者，和信息就在构建
   阶段没了，本模块无法恢复。所以树视图只能当只读辅助视图，界面必须标注。
3. **节点值可能被 ``json.loads`` 改写**（浮点表示形态、超大整数以 Python int
   精确保留）。故判断浮点相等、看原文 digits 这类需求请用原文视图。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

#: 树视图体量上限。超过就不建树（回落文本视图并说明原因）。
#: 依据实测（M4）：1.8MB / 18 万节点建树 208ms + 107MB 常驻内存，
#: 再往上点一下就要卡两秒——比「这太大了，请用原文视图」糟糕得多。
TREE_MAX_BYTES = 2 * 1024 * 1024

#: 超过这个体量就在提示栏里说一句会慢，但依旧让建（默认收起，用户自己点开）
TREE_WARN_BYTES = 256 * 1024

#: 叶子值在「值」列最长显示多少字符。再长（base64、SVG、压缩指标）会拖慢滚动，
#: 完整值放在 tooltip 与「复制值」里，一字符不少。
VALUE_PREVIEW_LIMIT = 200

#: 路径里的 dict key 若形如标识符，写成 ``$.a.b``；否则写成 ``$["a-b"]``
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class JsonTreeError(ValueError):
    """无法构建树（不是合法 JSON / 体量超上限）。

    继承 ValueError 是为了让调用方能一次性接住 ``json.JSONDecodeError``
    （它本身也是 ValueError 子类）与本错误。
    """


@dataclass(eq=False)
class JsonNode:
    """树里的一个节点。

    ``value`` 直接持有解析后的 Python 对象（dict / list / str / int / float /
    bool / None），不再做一层拷贝——拷贝的钱（时间 + 内存）白花。
    """

    key: str                        # dict 的键；数组元素为空串（下标用 [i] 显示）
    value: Any
    parent: JsonNode | None = None
    index: int | None = None        # 在数组里的下标；dict 子节点为 None
    row: int = 0                    # 在兄弟里的序号（父 → 子路径的一部分）
    depth: int = 0
    _children: list[JsonNode] | None = field(default=None, repr=False)

    # ---------------------------------------------------------------- 结构

    @property
    def is_container(self) -> bool:
        return isinstance(self.value, (dict, list))

    @property
    def child_count(self) -> int:
        """子节点数量（不展开也能算：容器长度是已知的）。"""
        try:
            return len(self.value)
        except TypeError:
            return 0

    def rows(self) -> list[JsonNode]:
        """子节点列表，**首次调用时才实例化**，之后缓存复用。

        缓存还有一个副作用：Node 身份稳定，搜索命中的落在同一个对象上，
        模型才能用 ``id(node)`` 记录底色。
        """
        if self._children is None:
            self._children = _build_children(self)
        return self._children

    @property
    def expanded_children(self) -> bool:
        """子节点是否已被实例化（给测试用，顺带反应「有没有真的展开过」）。"""
        return self._children is not None

    # ---------------------------------------------------------------- 展示

    @property
    def type_name(self) -> str:
        v = self.value
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "boolean"
        if isinstance(v, (int, float)):
            return "number"
        if isinstance(v, str):
            return "string"
        if isinstance(v, list):
            return "array"
        if isinstance(v, dict):
            return "object"
        return "unknown"

    @property
    def label(self) -> str:
        """第 1 列显示的文本：dict 键 / 数组下标 / 根节点的 ``$``。"""
        if self.index is not None:
            return f"[{self.index}]"
        if self.parent is None:
            return "$"
        return self.key

    @property
    def value_text(self) -> str:
        """第 2 列显示的文本（可能截断；完整值见 ``full_text``）。

        容器节点（对象 / 数组）折叠时也内联预览前几项内容（Fiddler / Charles
        风格），而不是只显示一个干瘪的数量数字 ``{3}`` / ``[10]`` —— 那样折叠时
        根本看不出里面是什么。预览不递归实例化子树（嵌套容器只标 ``{…}`` /
        ``[…]``），保住大文档的懒加载性能。
        """
        if self.is_container:
            text = self.preview_text()
        else:
            text = self._leaf_text()
        if len(text) > VALUE_PREVIEW_LIMIT:
            return text[:VALUE_PREVIEW_LIMIT] + "…"
        return text

    def preview_text(self, limit: int = 3) -> str:
        """折叠态下的值预览（Fiddler / Charles 风格）。

        只取顶层前 ``limit`` 项内联展示；嵌套容器只标 ``{…}`` / ``[…]`` 不递归，
        避免为「预览一个折叠行」就把整棵子树实例化出来。
        """
        if not self.is_container:
            return self._leaf_text()
        if isinstance(self.value, dict):
            parts = []
            for i, (k, v) in enumerate(self.value.items()):
                if i >= limit:
                    break
                parts.append(f"{k}: {self._preview_leaf(v)}")
            if len(self.value) > limit:
                parts.append("…")
            return "{" + ", ".join(parts) + "}"
        items = list(self.value)
        parts = [self._preview_leaf(v) for v in items[:limit]]
        if len(items) > limit:
            parts.append("…")
        return "[" + ", ".join(parts) + "]"

    @staticmethod
    def _preview_leaf(v) -> str:
        if isinstance(v, (dict, list)):
            return "{…}" if isinstance(v, dict) else "[…]"
        return json.dumps(v, ensure_ascii=False)

    @property
    def full_text(self) -> str:
        """完整叶子值（截断前），tooltip / 复制值用。"""
        return "" if self.is_container else self._leaf_text()

    def _leaf_text(self) -> str:
        v = self.value
        if isinstance(v, (dict, list)):
            return ""
        # 统一走 json.dumps：字符串的引号/转义、None→null、True→true 都对了，
        # 而 str(v) 会把 None 变成 "None"——看着像字段值真的叫 None
        return json.dumps(v, ensure_ascii=False)

    @property
    def truncated(self) -> bool:
        return not self.is_container and len(self._leaf_text()) > VALUE_PREVIEW_LIMIT

    @property
    def path(self) -> str:
        """JSONPath 风格路径（``$.data[0].name``），复制路径用。"""
        parts: list[str] = []
        node = self
        while node is not None and node.parent is not None:
            if node.index is not None:
                parts.append(f"[{node.index}]")
            elif _IDENT_RE.match(node.key):
                parts.append(f".{node.key}")
            else:
                parts.append(f'["{node.key}"]')
            node = node.parent
        if not parts:
            return "$"
        return "$" + "".join(reversed(parts))

    def subtree_json(self, indent: int = 2) -> str:
        """子树序列化（复制整个节点用），与常见编辑器观感一致。"""
        return json.dumps(self.value, ensure_ascii=False, indent=indent)


def _build_children(node: JsonNode) -> list[JsonNode]:
    """实例化子节点（dict 保序、list 带下标）。"""
    value = node.value
    out: list[JsonNode] = []
    if isinstance(value, dict):
        items: list[tuple[str, Any, int | None]] = [
            (str(k), v, None) for k, v in value.items()
        ]
    elif isinstance(value, list):
        items = [("", v, i) for i, v in enumerate(value)]
    else:
        return out
    for row, (key, val, index) in enumerate(items):
        out.append(JsonNode(key=key, value=val, parent=node, index=index,
                            row=row, depth=node.depth + 1))
    return out


# ====================================================================== 入口

def parse_tree(body: bytes, max_bytes: int = TREE_MAX_BYTES) -> JsonNode:
    """把 body 解析成树根；失败抛 :class:`JsonTreeError`。

    `max_bytes` 只对**这条 body** 生效（不像 ``JSON_PARSE_LIMIT`` 那样还要先把
    字节解码成文本），json.loads 直接吃 bytes，省一次大字符串物化。
    """
    if not body:
        raise JsonTreeError("empty body")
    if len(body) > max_bytes:
        raise JsonTreeError(
            "too large: %d bytes > %d" % (len(body), max_bytes)
        )
    try:
        value = json.loads(body)
    except (ValueError, RecursionError) as exc:
        raise JsonTreeError(str(exc)) from exc
    return JsonNode(key="$", value=value, parent=None, index=None, row=0, depth=0)


def walk(root: JsonNode) -> Iterator[JsonNode]:
    """深度优先遍历全部节点（**会实例化所有子节点**，搜索时才用）。

    调用方负责控制规模——这也是为什么 UI 侧搜索前先看体量。
    """
    yield root
    if not root.is_container:
        return
    stack: list[JsonNode] = list(reversed(root.rows()))
    while stack:
        node = stack.pop()
        yield node
        if node.is_container:
            stack.extend(reversed(node.rows()))
