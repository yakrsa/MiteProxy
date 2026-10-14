"""JSON 结构化 diff（纯函数，不依赖 Qt）。

「重放并对比」与「JSON 比对」共用：把两棵 JSON 树的差异拆成
`路径 + 类型 + 旧值/新值` 的条目列表，比 difflib 行级 diff 更准——
行级 diff 遇到「整个 JSON 重排」会全行飘红，键级 diff 只会标出真正
变化的字段。

设计约束（踩过的坑）：
1. **迭代不递归**：`[[[[…]]]]` 深嵌套会 RecursionError（见 jsonutil 注释），
   这里用显式栈；
2. **双上限**：节点数超限或差异条目超限即停，`truncated=True`，
   调用方应回退到文本 diff——结构化 diff 是增强，不能成为卡顿源；
3. **key 顺序不算差异**：按 key 集合比较，服务端调整字段顺序不报噪音；
4. **bool 与数字严格区分**：Python 里 `True == 1`，JSON 语义却不是
   一回事（`true` != `1`），标量相等判断必须先把 bool 摘出来；
5. **列表按下标对齐**：中间插入元素会让后续元素整体偏移（已知限制），
   这类场景文本 diff 更能看出版本变化。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

#: 节点数上限（两棵树合计）：超出即停，防超大 JSON 卡死界面
MAX_DIFF_NODES = 200_000
#: 差异条目上限：防「整个数组全变」时报告爆炸
MAX_DIFF_ENTRIES = 2000

#: 「只在一边存在」的哨兵：与任何 JSON 值（含 None）都不会相等
MISSING = object()


@dataclass(frozen=True)
class DiffEntry:
    """一处差异。

    path: JSONPath 风格（`$.a.b[0]`，根为 `$`）
    kind: added（仅新树有）/ removed（仅旧树有）/ changed（两边都有但不同）
    """

    path: str
    kind: str
    old: object = None
    new: object = None

    def render(self, value_limit: int = 120) -> str:
        old_text = render_value(self.old, value_limit)
        new_text = render_value(self.new, value_limit)
        if self.kind == "added":
            return f"+ {self.path} = {new_text}"
        if self.kind == "removed":
            return f"- {self.path} = {old_text}"
        return f"~ {self.path}: {old_text} → {new_text}"


@dataclass
class DiffResult:
    entries: list[DiffEntry] = field(default_factory=list)
    #: True = 因超限提前停止，entries 不完整
    truncated: bool = False
    old_nodes: int = 0
    new_nodes: int = 0

    @property
    def identical(self) -> bool:
        return not self.entries and not self.truncated

    @property
    def count(self) -> int:
        return len(self.entries)


# ---------------------------------------------------------------- 标量渲染


def render_value(value: object, limit: int = 120) -> str:
    """单行紧凑渲染。容器用紧凑 JSON，长值截断——报告是给人扫的。"""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        text = json.dumps(value, ensure_ascii=False)
    elif isinstance(value, (int, float)):
        text = str(value)
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            text = repr(value)
    if len(text) > limit:
        text = text[:limit] + f"…（共 {len(text)} 字符）"
    return text


def _scalars_equal(a: object, b: object) -> bool:
    """标量相等。bool 只与同 bool 相等（True != 1，JSON 语义）。"""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return a == b


# ---------------------------------------------------------------- 路径


def _child_path(path: str, key: str) -> str:
    safe = key if all(ch not in key for ch in ".[]*'\" ") else json.dumps(key, ensure_ascii=False)
    return f"{path}.{safe}" if path != "$" else f"$.{safe}"


# ---------------------------------------------------------------- 核心 diff


def diff_json(old: object, new: object) -> DiffResult:
    """结构化 diff 两棵 JSON 树。迭代实现，深嵌套不会爆栈。"""
    entries: list[DiffEntry] = []
    truncated = False
    seen = 0
    # 栈元素：`(路径, 旧值, 新值)`；MISSING 表示该侧不存在
    stack: list[tuple[str, object, object]] = [("$", old, new)]
    while stack:
        if len(entries) >= MAX_DIFF_ENTRIES:
            truncated = True
            break
        path, a, b = stack.pop()
        seen += 2
        if seen > MAX_DIFF_NODES:
            truncated = True
            break

        if a is MISSING:
            entries.append(DiffEntry(path, "added", None, b))
            continue
        if b is MISSING:
            entries.append(DiffEntry(path, "removed", a, None))
            continue

        if isinstance(a, dict) and isinstance(b, dict):
            children: list[tuple[str, object, object]] = []
            for key, value in b.items():
                if key not in a:
                    children.append((_child_path(path, key), MISSING, value))
            for key, value in a.items():
                if key not in b:
                    children.append((_child_path(path, key), value, MISSING))
                else:
                    children.append((_child_path(path, key), value, b[key]))
            # 逆序入栈 → 弹出顺序 = 文档自然顺序（报告读起来顺）
            for item in reversed(children):
                stack.append(item)
        elif isinstance(a, list) and isinstance(b, list):
            children = []
            for i in range(max(len(a), len(b))):
                if i >= len(a):
                    children.append((f"{path}[{i}]", MISSING, b[i]))
                elif i >= len(b):
                    children.append((f"{path}[{i}]", a[i], MISSING))
                else:
                    children.append((f"{path}[{i}]", a[i], b[i]))
            for item in reversed(children):
                stack.append(item)
        elif isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
            # 一边是容器一边不是（dict↔list、容器↔标量都走这）
            entries.append(DiffEntry(path, "changed", a, b))
        elif not _scalars_equal(a, b):
            entries.append(DiffEntry(path, "changed", a, b))

    return DiffResult(
        entries=entries,
        truncated=truncated,
        old_nodes=count_json_nodes(old),
        new_nodes=count_json_nodes(new),
    )


def count_json_nodes(value: object, limit: int = MAX_DIFF_NODES) -> int:
    """节点总数（迭代实现）。只用于概要展示，失败不影响 diff 本身。"""
    total = 0
    stack = [value]
    while stack:
        if total >= limit:
            return total
        item = stack.pop()
        total += 1
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return total


# ---------------------------------------------------------------- 报告


def format_diff_report(result: DiffResult, max_entries: int = 200) -> str:
    """给人看的差异报告（UI 显示与「复制差异」共用）。"""
    if result.identical:
        return "两个 JSON 完全一致"
    lines: list[str] = []
    shown = result.entries[:max_entries]
    head = f"共 {result.count} 处差异"
    if len(shown) < result.count:
        head += f"（显示前 {len(shown)} 条）"
    lines.append(head + ":")
    lines.extend(entry.render() for entry in shown)
    if result.truncated:
        lines.append("……（差异过多或内容过大，已停止；请改用文本 diff 查看）")
    return "\n".join(lines)
