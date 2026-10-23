"""API 调试页的请求集合持久化：~/.miteproxy/api_collections.json。

与 rules.py 同款约定：纯数据 + 纯函数，不碰 Qt，UI 层（api_panel /
集合对话框）只负责展示与调用。测试用 MITEPROXY_HOME 环境变量隔离。
"""

from __future__ import annotations

import json
import time
import uuid

from app.rules import CONFIG_DIR

COLLECTIONS_PATH = CONFIG_DIR / "api_collections.json"

#: 单条集合的字段白名单（读盘时过滤，旧版多余字段直接丢弃）
_FIELDS = ("id", "name", "method", "url", "headers", "body", "graphql", "variables", "created_at")


def load_collections() -> list[dict]:
    """读出全部集合项；文件不存在/损坏时返回空列表（不抛）。"""
    try:
        data = json.loads(COLLECTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    items = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        item = {k: raw.get(k) for k in _FIELDS}
        # headers 规整为 [[k, v], ...]；兼容旧版 dict 形态
        headers = item.get("headers")
        if isinstance(headers, dict):
            item["headers"] = [[str(k), str(v)] for k, v in headers.items() if k]
        elif isinstance(headers, list):
            item["headers"] = [
                [str(h[0]), str(h[1])] for h in headers
                if isinstance(h, (list, tuple)) and len(h) >= 2 and h[0]
            ]
        else:
            item["headers"] = []
        items.append(item)
    return items


def save_collections(items: list[dict]) -> None:
    """整体写盘（集合数量很小，百条以内，全量写无压力）。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    clean = [{k: it.get(k) for k in _FIELDS} for it in items]
    tmp = COLLECTIONS_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(COLLECTIONS_PATH)


def add_collection(
    name: str,
    method: str = "GET",
    url: str = "",
    headers: list | None = None,
    body: str = "",
    graphql: bool = False,
    variables: str = "",
) -> dict:
    """新增一条集合并返回它（调用方拿到 id 可用于后续改名/删除）。

    存储层不放展示文案：name 为空时存空串，由 UI 层展示时本地化兜底。
    """
    items = load_collections()
    item = {
        "id": uuid.uuid4().hex[:8],
        "name": (name or "").strip(),
        "method": (method or "GET").upper(),
        "url": url or "",
        "headers": [[str(k), str(v)] for k, v in (headers or []) if k],
        "body": body or "",
        "graphql": bool(graphql),
        "variables": variables or "",
        "created_at": int(time.time()),
    }
    items.append(item)
    save_collections(items)
    return item


def delete_collection(item_id: str) -> bool:
    """按 id 删除；删掉了返回 True，没找到返回 False。"""
    items = load_collections()
    left = [it for it in items if it.get("id") != item_id]
    if len(left) == len(items):
        return False
    save_collections(left)
    return True


def rename_collection(item_id: str, new_name: str) -> bool:
    items = load_collections()
    hit = False
    for it in items:
        if it.get("id") == item_id:
            it["name"] = (new_name or "").strip()
            hit = True
    if hit:
        save_collections(items)
    return hit


def find_collection(item_id: str) -> dict | None:
    for it in load_collections():
        if it.get("id") == item_id:
            return it
    return None
