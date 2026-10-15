"""规则中心：模型、匹配算法、JSON 持久化（见 DESIGN.md 3.3 / 4.1）。

线程模型：RuleStore 可被 Qt 主线程（写）与 mitmproxy 代理线程（读）同时访问，
所有公开方法内部加 RLock；匹配是只读热路径，锁持有时间极短。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

# 配置目录（测试可用环境变量 MITEPROXY_HOME 覆盖）。
# 兼容迁移：改名前的旧目录 ~/.mitmproxy-fiddler 若存在且新目录还没有，
# 继续用旧目录——老用户的 rules.json / settings.json 无缝保留。
_NEW_HOME = Path.home() / ".miteproxy"
_LEGACY_HOME = Path.home() / ".mitmproxy-fiddler"
CONFIG_DIR = Path(
    os.environ.get("MITEPROXY_HOME")
    or (
        _LEGACY_HOME
        if _LEGACY_HOME.exists() and not _NEW_HOME.exists()
        else _NEW_HOME
    )
)
RULES_PATH = CONFIG_DIR / "rules.json"

# 匹配类型
EXACT = "exact"          # 完整 URL 全等
CONTAINS = "contains"    # URL 包含子串
WILDCARD = "wildcard"    # 通配符：* 匹配非 / 字符，** 匹配任意字符
REGEX = "regex"          # 正则（re.search 语义）

MATCH_TYPES = (EXACT, CONTAINS, WILDCARD, REGEX)

STATUS_MIN, STATUS_MAX = 100, 599
MAX_LATENCY_MS = 60_000


# ------------------------------------------------------------------ 数据模型


@dataclass
class Match:
    type: str = CONTAINS
    value: str = ""
    #: 请求方法过滤（"" = 任意方法；否则精确比较、大小写不敏感）。
    #: 比 Fiddler 好的一点：Fiddler AutoResponder 的条件要自己拼正则才能区分方法，
    #: 这里下拉一选就行。
    method: str = ""
    _compiled: Optional[re.Pattern] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        return {"type": self.type, "value": self.value, "method": self.method}

    @classmethod
    def from_dict(cls, data: dict) -> "Match":
        mtype = data.get("type", CONTAINS)
        if mtype not in MATCH_TYPES:
            log.warning("未知匹配类型 %r，降级为 contains", mtype)
            mtype = CONTAINS
        return cls(
            type=mtype,
            value=str(data.get("value", "")),
            method=str(data.get("method", "") or "").strip().upper(),
        )

    def matches_method(self, method: str) -> bool:
        """请求方法是否匹配（"" = 任意；比较大小写不敏感）。"""
        want = (self.method or "").strip().upper()
        if not want:
            return True
        return (method or "").upper() == want

    def compile(self) -> Optional[re.Pattern]:
        """预编译正则类匹配；非法正则返回 None（该规则永不命中）。"""
        if self._compiled is not None:
            return self._compiled
        pattern = None
        if self.type == WILDCARD:
            pattern = _wildcard_to_regex(self.value)
        elif self.type == REGEX:
            pattern = self.value
        if pattern is None:
            return None
        try:
            self._compiled = re.compile(pattern)
        except re.error as e:
            log.error("规则正则编译失败 %r: %s", self.value, e)
            return None
        return self._compiled

    def match_url(self, url: str) -> Optional[re.Match]:
        """命中返回 re.Match（供 $1 替换；非正则类返回 None），未命中返回 False。

        注意：统一用 False 表示未命中——不能用 None，因为 re.search
        无匹配时返回的就是 None，会让调用方误判为命中。
        """
        if self.type == EXACT:
            return None if url == self.value else False
        if self.type == CONTAINS:
            if not self.value:
                return False
            return None if self.value in url else False
        compiled = self.compile()
        if compiled is None:
            return False
        result = compiled.search(url)
        return result if result is not None else False


@dataclass
class Action:
    status: int = 200
    headers: dict = field(default_factory=dict)
    body_source: str = "inline"  # inline | file
    body: str = ""
    file_path: Optional[str] = None
    latency_ms: int = 0
    #: 非空 = 重定向模式：命中后把请求改发到这个 URL（支持 $1 替换），返回新上游的
    #: 真实响应（规则级 Map Remote，对客户端透明）。此时 status/headers/body 均不生效。
    redirect_url: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "headers": dict(self.headers),
            "body_source": self.body_source,
            "body": self.body,
            "file_path": self.file_path,
            "latency_ms": self.latency_ms,
            "redirect_url": self.redirect_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        status = data.get("status", 200)
        try:
            status = int(status)
        except (TypeError, ValueError):
            status = 200
        status = max(STATUS_MIN, min(STATUS_MAX, status))
        latency = data.get("latency_ms", 0)
        try:
            latency = max(0, min(MAX_LATENCY_MS, int(latency)))
        except (TypeError, ValueError):
            latency = 0
        body_source = data.get("body_source", "inline")
        if body_source not in ("inline", "file"):
            body_source = "inline"
        return cls(
            status=status,
            headers={str(k): str(v) for k, v in (data.get("headers") or {}).items()},
            body_source=body_source,
            body=str(data.get("body", "")),
            file_path=data.get("file_path"),
            latency_ms=latency,
            redirect_url=str(data.get("redirect_url", "") or ""),
        )


@dataclass
class Rule:
    id: str
    name: str
    enabled: bool
    match: Match
    action: Action
    source: str = "manual"  # manual | farx | js（来源标记，便于追溯）
    error: Optional[str] = None  # 运行时错误（如文件缺失），UI 标红用
    #: 命中计数（仅运行时，不持久化——每次命中都写盘会把热路径拖慢；
    #: 重启归零是可接受的：它回答的是"这次调试期间哪条规则在干活"）
    hits: int = 0
    #: 最近命中时间（time.time() 秒），0 = 从未命中
    last_hit: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "match": self.match.to_dict(),
            "action": self.action.to_dict(),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        return cls(
            id=str(data.get("id") or _new_id()),
            name=str(data.get("name", "未命名规则")),
            enabled=bool(data.get("enabled", True)),
            match=Match.from_dict(data.get("match") or {}),
            action=Action.from_dict(data.get("action") or {}),
            source=str(data.get("source", "manual")),
        )

    @classmethod
    def create(cls, name: str = "新规则") -> "Rule":
        return cls(
            id=_new_id(),
            name=name,
            enabled=True,
            match=Match(),
            action=Action(),
        )


def _new_id() -> str:
    return "r_" + uuid.uuid4().hex[:8]


def _wildcard_to_regex(pattern: str) -> str:
    """通配符转正则：* → [^/]*，** → .*，其余原样转义。"""
    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        out.append(re.escape(ch))
        i += 1
    return "^" + "".join(out) + "$"


# ------------------------------------------------------------------ 规则仓库


class RuleStore:
    """规则的内存 + 文件存储，线程安全。"""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else RULES_PATH
        self._rules: list[Rule] = []
        self._lock = threading.RLock()
        self._on_change: Optional[Callable[[], None]] = None
        self._on_rule_error: Optional[Callable[[str, Optional[str]], None]] = None
        self._on_rule_hit: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------- 回调注册

    def set_callbacks(
        self,
        on_change: Optional[Callable[[], None]] = None,
        on_rule_error: Optional[Callable[[str, Optional[str]], None]] = None,
        on_rule_hit: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_change = on_change
        self._on_rule_error = on_rule_error
        self._on_rule_hit = on_rule_hit

    # ------------------------------------------------------------- 持久化

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self._rules = []
                return
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                rules = [Rule.from_dict(r) for r in data.get("rules", [])]
            except (json.JSONDecodeError, OSError) as e:
                backup = self.path.with_suffix(".json.bak")
                log.error("规则文件损坏，备份到 %s: %s", backup, e)
                try:
                    self.path.replace(backup)
                except OSError:
                    pass
                self._rules = []
                return
            # 同名 id 去重（保留先出现者）
            seen = set()
            unique = []
            for r in rules:
                if r.id in seen:
                    r.id = _new_id()
                seen.add(r.id)
                unique.append(r)
            self._rules = unique
            log.info("已加载 %d 条规则", len(self._rules))

    def save(self) -> None:
        with self._lock:
            payload = {
                "version": 1,
                "rules": [r.to_dict() for r in self._rules],
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp, self.path)  # 原子替换，防崩溃写坏

    # ------------------------------------------------------------- CRUD

    def all(self) -> list[Rule]:
        with self._lock:
            return list(self._rules)

    def get(self, rule_id: str) -> Optional[Rule]:
        with self._lock:
            for r in self._rules:
                if r.id == rule_id:
                    return r
            return None

    def index_of(self, rule_id: str) -> int:
        """规则在当前列表中的序号（1 起，按优先级顺序；找不到返回 0）。

        供 mock 命中时在流量备注里显示「MOCK#序号」——跟随拖拽排序
        实时变化，不落盘（与 hits 同理，是运行时展示信息）。
        """
        with self._lock:
            for i, r in enumerate(self._rules, 1):
                if r.id == rule_id:
                    return i
        return 0

    def add(self, rule: Rule) -> Rule:
        with self._lock:
            self._rules.append(rule)
            self.save()
            self._notify_change()
            return rule

    def update(self, rule_id: str, **fields: Any) -> Optional[Rule]:
        """按字段更新；match/action 传 dict 时整体替换。"""
        with self._lock:
            rule = self.get(rule_id)
            if rule is None:
                return None
            for key, value in fields.items():
                if key == "match" and isinstance(value, dict):
                    rule.match = Match.from_dict(value)
                elif key == "action" and isinstance(value, dict):
                    rule.action = Action.from_dict(value)
                elif key in ("name", "enabled", "source"):
                    setattr(rule, key, value)
                else:
                    raise KeyError(f"不允许更新的字段: {key}")
            self.save()
            self._notify_change()
            return rule

    def delete(self, rule_id: str) -> bool:
        with self._lock:
            before = len(self._rules)
            self._rules = [r for r in self._rules if r.id != rule_id]
            changed = len(self._rules) != before
            if changed:
                self.save()
                self._notify_change()
            return changed

    def reorder(self, rule_ids: list[str]) -> None:
        """按给定 id 顺序重排（优先级 = 列表顺序）。"""
        with self._lock:
            by_id = {r.id: r for r in self._rules}
            ordered = [by_id[i] for i in rule_ids if i in by_id]
            rest = [r for r in self._rules if r.id not in set(rule_ids)]
            self._rules = ordered + rest
            self.save()
            self._notify_change()

    def merge(self, rules: list[Rule]) -> tuple[int, list[str]]:
        """合并导入的规则：重生成 id，同名自动加后缀。返回 (导入数, 新id列表)。"""
        with self._lock:
            existing_names = {r.name for r in self._rules}
            new_ids = []
            for rule in rules:
                rule.id = _new_id()
                base = rule.name
                n = 2
                while rule.name in existing_names:
                    rule.name = f"{base} ({n})"
                    n += 1
                existing_names.add(rule.name)
                self._rules.append(rule)
                new_ids.append(rule.id)
            self.save()
            self._notify_change()
            return len(rules), new_ids

    # ------------------------------------------------------------- 匹配

    def find_rule(
        self, url: str, method: str = ""
    ) -> tuple[Optional[Rule], Optional[re.Match]]:
        """按顺序找第一条命中的启用规则（URL + 请求方法都匹配才算命中）。

        规则 method 为空 = 任意方法。规则配置了方法而调用方传空串时
        不命中（"不知道方法"按不匹配处理，保守侧默认）。
        """
        with self._lock:
            for rule in self._rules:
                if not rule.enabled:
                    continue
                if not rule.match.matches_method(method):
                    continue
                m = rule.match.match_url(url)
                if m is not False:
                    return rule, m if isinstance(m, re.Match) else None
            return None, None

    # ------------------------------------------------------------- 错误标记

    def set_rule_error(self, rule_id: str, message: Optional[str]) -> None:
        with self._lock:
            rule = self.get(rule_id)
            if rule is None or rule.error == message:
                return
            rule.error = message
            callback = self._on_rule_error
        # 回调在锁外调（与 record_hit 同款约定）：回调可能反过来碰 store，
        # 锁内调用有死锁隐患
        if callback:
            try:
                callback(rule_id, message)
            except Exception:
                log.exception("on_rule_error 回调异常")

    # ------------------------------------------------------------- 命中计数

    def record_hit(self, rule_id: str) -> None:
        """规则命中一次（由 MockAddon 在代理线程调用，必须线程安全且极轻）。"""
        with self._lock:
            rule = self.get(rule_id)
            if rule is None:
                return
            rule.hits += 1
            rule.last_hit = time.time()
            callback = self._on_rule_hit
        if callback:
            try:
                callback(rule_id)
            except Exception:
                log.exception("on_rule_hit 回调异常")

    # ------------------------------------------------------------- 内部

    def _notify_change(self) -> None:
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                log.exception("on_change 回调异常")
