"""合作方 FIX 字典：私有 tag 的导入 / 存储 / 与内置字典合并（纯逻辑，无 Qt）。

为什么需要：FIX 规范把 **tag 5000 起**划给用户自定义，每家券商 / 交易所
网关的私有字段含义、甚至同一个 tag 的解释都可能不同（比如 A 家的 10001
是「本地订单号」，B 家是「策略编号」）。内置字典 `app/fixdict.py` 只收
通用字段，合作方字段必须由用户按对方的协议说明导入。

数据流：

    合作方协议说明（Excel / Word / PDF 的字段表）
        ↓ 整理成 CSV/TSV 粘贴或存成 .csv，或直接写 JSON
    parse_profile_text()  →  Profile（字段 / 重复组 / 长度配对 / 消息类型）
        ↓ save_profile()
    <配置目录>/fix_dicts/<slug>.json
        ↓ merge()（当前选中的那份）
    Dictionary  = 内置字典 ⊕ 合作方字典（同 tag 合作方优先）
        ↓ parse_fix(text, dictionary=...)
    界面上私有 tag 就有名字、枚举释义，重复组也能展开

文件格式（两种都支持，按内容自动识别）：

1. **JSON**（推荐，能表达重复组 / 长度配对）：

```json
{
  "name": "XX 期货",
  "fix_version": "FIX.4.4",
  "note": "2026-10 版接口文档",
  "fields": {
    "10001": {"en": "LocalOrderID", "cn": "本地订单号", "type": "String"},
    "10002": {"en": "StrategyID", "cn": "策略编号", "type": "String"},
    "10003": {"en": "LegQty", "cn": "腿数量", "type": "Qty",
              "enums": {"1": "买", "2": "卖"}}
  },
  "msg_types": {"U": "TradeCaptureReport 成交确认"},
  "groups": {"10010": {"en": "NoSubOrders", "cn": "子订单",
                       "members": [10011, 10012]}},
  "data_pairs": {"10020": 10021}
}
```

也接受平铺列表（免去手写对象键）：

```json
[{"tag": 10001, "en": "LocalOrderID", "cn": "本地订单号"},
 {"tag": 10002, "cn": "策略编号"}]
```

2. **CSV / TSV**（直接从文档的字段表复制过来，制表符或逗号分隔）：

```
tag,英文名,中文名,类型,枚举,组成员
10001,LocalOrderID,本地订单号,String,,
10003,LegSide,腿方向,char,1=买;2=卖,
10010,NoSubOrders,子订单数,NumInGroup,,10011 10012
10011,SubOrderID,子订单号,String,,
```

列名认别名（tag/标签/字段号、en/英文名/name、cn/中文名/含义、type/类型、
enum/枚举/取值、members/组成员）；没有表头时按前五列位置读。`组成员`
只对 NumInGroup 类型的行有意义，用来把重复组展开成树。`#` 开头是注释行。

语义约定：

- **叠加而非替换**：合作方字典只覆盖同名 tag，内置字段照常可用；
  所以同一份字典可以只写对方的私有字段。
- **同 tag 以合作方为准**：对方把内置 tag 重新定义了（例如 58 有自己的
  子类型），按对方文档走。
- **不认识的行不丢输入**：解析时收集 warning 返回，界面把 warning 计数
  和第一条原因显示出来，用户自己判断要不要改文件。
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app import fixdict
from app.rules import CONFIG_DIR

#: 字典目录（测试可用 MITEPROXY_HOME 覆盖，CONFIG_DIR 已处理）
PROFILE_DIR_NAME = "fix_dicts"
#: 当前生效的合作方字典 slug（空 = 只用内置字典）
ACTIVE_FILE_NAME = "active.json"

#: 单字段元组，与 fixdict.FIELDS 的值同构：英文名 / 中文名 / 类型 / 枚举
FieldDef = tuple[str, str, str, dict[str, str]]


# ====================================================================== 字典视图

class Dictionary:
    """解析器眼中的字典：lookup / group_of / data_partner。

    `app/fixdict` 模块本身也满足这个协议（三个同名函数），所以 fix.py 的
    默认字典可以直接用模块；这里只负责「内置 + 合作方」的合并结果。
    """

    __slots__ = ("fields", "groups", "data_pairs")

    def __init__(self, fields: dict[int, FieldDef],
                 groups: dict[int, tuple[str, str, tuple[int, ...]]] | None = None,
                 data_pairs: dict[int, int] | None = None) -> None:
        self.fields = fields
        self.groups = groups or {}
        self.data_pairs = data_pairs or {}

    def lookup(self, tag: int) -> FieldDef | None:
        return self.fields.get(tag)

    def group_of(self, tag: int) -> tuple[str, str, tuple[int, ...]] | None:
        return self.groups.get(tag)

    def data_partner(self, tag: int) -> int | None:
        return self.data_pairs.get(tag)

    #: 界面展示用：这版字典能解释多少个 tag
    def __len__(self) -> int:
        return len(self.fields)


#: 只用内置字典（与 fix.py 默认行为完全一致）
BUILTIN = Dictionary(fixdict.FIELDS, fixdict.GROUPS, fixdict.DATA_LENGTH_PAIRS)


# ====================================================================== 数据模型

@dataclass
class Profile:
    """一个合作方的字典（落盘成 fix_dicts/<slug>.json）。"""

    slug: str
    name: str
    fix_version: str = ""
    note: str = ""
    #: tag → (英文名, 中文名, 类型, 枚举)
    fields: dict[int, FieldDef] = field(default_factory=dict)
    #: 引导 tag → (英文名, 中文名, 成员 tag)
    groups: dict[int, tuple[str, str, tuple[int, ...]]] = field(default_factory=dict)
    #: 长度 tag → 数据 tag
    data_pairs: dict[int, int] = field(default_factory=dict)
    #: 35 的消息类型补充（合并进内置 MSG_TYPES）
    msg_types: dict[str, str] = field(default_factory=dict)
    #: 导入时的来源文件（只做展示，不参与解析）
    source: str = ""
    #: 解析该文件时收集的问题（不阻断导入）
    warnings: list[str] = field(default_factory=list)

    # ---------------------------------------------------------- 序列化

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "name": self.name,
            "fix_version": self.fix_version,
            "note": self.note,
            "fields": {
                str(tag): {
                    "en": d[0], "cn": d[1], "type": d[2],
                    **({"enums": dict(d[3])} if d[3] else {}),
                }
                for tag, d in sorted(self.fields.items())
            },
            **({"msg_types": dict(self.msg_types)} if self.msg_types else {}),
            **({"groups": {
                str(tag): {"en": g[0], "cn": g[1], "members": list(g[2])}
                for tag, g in sorted(self.groups.items())
            }} if self.groups else {}),
            **({"data_pairs": {
                str(k): v for k, v in sorted(self.data_pairs.items())
            }} if self.data_pairs else {}),
        }

    @classmethod
    def from_dict(cls, data: dict, *, slug: str = "", source: str = "") -> "Profile":
        fields: dict[int, FieldDef] = {}
        for key, val in (data.get("fields") or {}).items():
            tag = _as_tag(key)
            if tag is None:
                continue
            fields[tag] = _field_def(val)
        groups: dict[int, tuple[str, str, tuple[int, ...]]] = {}
        for key, val in (data.get("groups") or {}).items():
            tag = _as_tag(key)
            if tag is None or not isinstance(val, dict):
                continue
            members = tuple(
                m for m in (_as_tag(x) for x in (val.get("members") or []))
                if m is not None)
            if members:
                groups[tag] = (
                    str(val.get("en") or ""), str(val.get("cn") or ""), members)
        pairs: dict[int, int] = {}
        for key, val in (data.get("data_pairs") or {}).items():
            tag, partner = _as_tag(key), _as_tag(val)
            if tag is not None and partner is not None:
                pairs[tag] = partner
        msg_types = {
            str(k): str(v) for k, v in (data.get("msg_types") or {}).items()
            if str(k).strip()
        }
        name = str(data.get("name") or "").strip()
        return cls(
            slug=slug or slugify(name) or "profile",
            name=name or slug or "profile",
            fix_version=str(data.get("fix_version") or "").strip(),
            note=str(data.get("note") or "").strip(),
            fields=fields, groups=groups, data_pairs=pairs,
            msg_types=msg_types, source=source,
        )

    #: 界面里 combo 的显示文案
    def label(self) -> str:
        bits = [self.name or self.slug]
        if self.fix_version:
            bits.append(self.fix_version)
        if self.note:
            bits.append(self.note)
        return " · ".join(bits)


# ====================================================================== 目录 / 存取

def profile_dir() -> Path:
    """字典目录（不存在就建）。独立成函数，测试可 monkeypatch。"""
    d = CONFIG_DIR / PROFILE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _active_path() -> Path:
    return profile_dir() / ACTIVE_FILE_NAME


def slugify(text: str) -> str:
    """名字 → 文件名安全 slug（保留中文，去掉路径分隔符与空白）。"""
    s = re.sub(r"[\s/\\:*?\"<>|]+", "-", (text or "").strip())
    s = s.strip("-.")
    return s[:60]


def get_active_slug() -> str:
    """当前生效的合作方字典；没选 / 文件没了就回落空串（= 只用内置）。"""
    path = _active_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    slug = str(data.get("active") or "") if isinstance(data, dict) else ""
    return slug if slug and (profile_dir() / "{0}.json".format(slug)).exists() else ""


def set_active_slug(slug: str) -> None:
    """记住当前生效的字典（空串 = 内置）。写盘失败不影响解析，静默降级。"""
    path = _active_path()
    try:
        path.write_text(json.dumps({"active": slug}, ensure_ascii=False),
                        encoding="utf-8")
    except OSError:
        pass


def list_profiles() -> list[Profile]:
    """读全部字典文件（坏文件跳过，别让一个手写错的 JSON 挡住整个列表）。"""
    out: list[Profile] = []
    for path in sorted(profile_dir().glob("*.json")):
        if path.name == ACTIVE_FILE_NAME:
            continue
        prof = load_profile(path)
        if prof is not None:
            out.append(prof)
    out.sort(key=lambda p: p.name)
    return out


def load_profile(path: Path) -> Profile | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    prof, _warnings = parse_profile_text(text, slug=path.stem, source=str(path))
    if prof is None:
        return None
    prof.slug = prof.slug or path.stem
    return prof


def save_profile(prof: Profile) -> Path:
    """落盘（文件名冲突时按内容覆盖同名 slug——同名字典即视为更新）。"""
    path = profile_dir() / "{0}.json".format(prof.slug)
    path.write_text(
        json.dumps(prof.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return path


def delete_profile(slug: str) -> bool:
    path = profile_dir() / "{0}.json".format(slug)
    try:
        path.unlink()
    except OSError:
        return False
    if get_active_slug() == slug:
        set_active_slug("")
    return True


# ====================================================================== 解析导入文件

#: CSV 表头别名（小写比较）。表头认不出时按位置读（tag, en, cn, type, enums）
_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "tag": ("tag", "标签", "tag号", "tag 号", "字段号", "序号", "编号", "field"),
    "en": ("en", "english", "英文", "英文名", "英文名称", "name", "字段英文名"),
    "cn": ("cn", "chinese", "中文", "中文名", "中文名称", "名称", "含义",
           "说明", "描述", "desc", "description", "字段中文名"),
    "type": ("type", "类型", "数据类型", "字段类型"),
    "enums": ("enum", "enums", "枚举", "取值", "值", "值说明", "枚举值", "values"),
    #: 重复组：NumInGroup 那一行填成员 tag（`10011,10012` 或 `10011 10012`）
    "members": ("members", "组成员", "成员", "子字段", "组内字段", "子tag"),
}


def parse_profile_text(text: str, *, slug: str = "",
                       source: str = "") -> tuple[Profile | None, list[str]]:
    """把一份导入内容解析成 Profile（JSON 优先，否则按 CSV/TSV 表读）。

    返回 (profile, warnings)；完全不认识的内容返回 (None, [原因])。
    """
    raw = (text or "").lstrip("\ufeff").strip()
    if not raw:
        return None, ["内容为空"]
    if raw[0] in "[{":
        return _parse_json(raw, slug=slug, source=source)
    return _parse_table(raw, slug=slug, source=source)


def _parse_json(raw: str, *, slug: str,
                source: str) -> tuple[Profile | None, list[str]]:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return None, ["JSON 解析失败：{0}".format(exc)]
    warnings: list[str] = []
    if isinstance(data, list):
        # 平铺列表：每条一个字段
        prof = Profile(slug=slug or "profile", name=slug or "profile")
        for i, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                warnings.append("第 {0} 项不是对象，已跳过".format(i))
                continue
            tag = _as_tag(item.get("tag") or item.get("tag号") or item.get("id"))
            if tag is None:
                warnings.append("第 {0} 项没有可用的 tag，已跳过".format(i))
                continue
            en = str(item.get("en") or item.get("name_en") or item.get("英文名") or "")
            cn = str(item.get("cn") or item.get("name_cn") or item.get("中文名") or "")
            ftype = str(item.get("type") or item.get("类型") or "")
            enums = _parse_enums(item.get("enums") or item.get("枚举"))
            prof.fields[tag] = (en, cn, ftype, enums)
        if not prof.fields:
            return None, warnings + ["没有解析出任何字段"]
        return prof, warnings
    if not isinstance(data, dict):
        return None, ["JSON 顶层必须是对象或数组"]
    prof = Profile.from_dict(data, slug=slug or slugify(str(data.get("name") or "")),
                            source=source)
    if not (prof.fields or prof.groups or prof.msg_types or prof.data_pairs):
        return None, ["字典里没有任何字段（fields 为空）"]
    prof.warnings = warnings
    return prof, warnings


def _parse_table(raw: str, *, slug: str,
                 source: str) -> tuple[Profile | None, list[str]]:
    """按 CSV/TSV 读字段表（分隔符自动识别，表头可选）。"""
    lines = [ln for ln in raw.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return None, ["内容为空"]
    delim = "\t" if "\t" in lines[0] else (";" if ";" in lines[0] and "," not in lines[0] else ",")
    rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delim))
    warnings: list[str] = []

    header = _map_header(rows[0])
    if header:
        body = rows[1:]
    else:
        # 没表头：按 tag, 英文名, 中文名, 类型, 枚举 的位置读
        header = {"tag": 0, "en": 1, "cn": 2, "type": 3, "enums": 4}
        body = rows

    prof = Profile(slug=slug or "profile", name=slug or "profile", source=source)
    for lineno, row in enumerate(body, start=1):
        if not row or not any(c.strip() for c in row):
            continue
        tag = _as_tag(_cell(row, header["tag"]))
        if tag is None:
            warnings.append("第 {0} 行 tag 不是数字，已跳过".format(lineno))
            continue
        en = _cell(row, header.get("en"))
        cn = _cell(row, header.get("cn"))
        prof.fields[tag] = (
            en, cn, _cell(row, header.get("type")),
            _parse_enums(_cell(row, header.get("enums"))),
        )
        # 可选「组成员」列：NumInGroup 引导 tag 后面跟的成员，用来展开重复组
        members = tuple(
            m for m in (_as_tag(x) for x in
                        re.split(r"[,，;；\s]+", _cell(row, header.get("members"))))
            if m is not None)
        if members:
            prof.groups[tag] = (en, cn, members)
    if not prof.fields:
        return None, warnings + ["没有解析出任何字段（tag 列是第一列吗？）"]
    prof.warnings = warnings
    return prof, warnings


def _map_header(row: list[str]) -> dict[str, int] | None:
    """认表头；认不出 tag 列就当没有表头。"""
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(row):
        key = (cell or "").strip().lower().replace(" ", "")
        for name, aliases in _HEADER_ALIASES.items():
            if name in mapping:
                continue
            if key in {a.replace(" ", "") for a in aliases}:
                mapping[name] = idx
                break
    return mapping if "tag" in mapping else None


def _cell(row: list[str], idx) -> str:
    if idx is None or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def _parse_enums(value) -> dict[str, str]:
    """枚举：dict 直接用；字符串支持 `1=买;2=卖` / `1:买|2:卖`。"""
    if isinstance(value, dict):
        return {str(k).strip(): str(v).strip() for k, v in value.items()
                if str(k).strip()}
    text = str(value or "").strip()
    if not text:
        return {}
    out: dict[str, str] = {}
    for item in re.split(r"[;|；\n]+", text):
        item = item.strip()
        if not item:
            continue
        m = re.match(r"^\s*([^=:：\s]+)\s*[=:：]\s*(.+)$", item)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def _field_def(val) -> FieldDef:
    """JSON 里一个字段可以是对象、字符串（只给中文名）或数组。"""
    if isinstance(val, dict):
        en = str(val.get("en") or val.get("name_en") or val.get("english") or "")
        cn = str(val.get("cn") or val.get("name_cn") or val.get("chinese") or "")
        ftype = str(val.get("type") or "")
        return (en, cn, ftype, _parse_enums(val.get("enums") or val.get("enum")))
    if isinstance(val, (list, tuple)):
        parts = [str(x) for x in val]
        parts += [""] * (4 - len(parts))
        enums = _parse_enums(parts[3]) if len(parts) > 3 else {}
        return (parts[0], parts[1], parts[2], enums)
    return ("", str(val or ""), "", {})


def _as_tag(value) -> int | None:
    """tag 规范化：允许 '10001' / ' 10001 ' / 10001，非法返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1 <= value <= 999999 else None
    text = str(value or "").strip().lstrip("#")
    if not text.isdigit():
        return None
    tag = int(text)
    return tag if 1 <= tag <= 999999 else None


# ====================================================================== 合并

def merge(profile: Profile | None) -> Dictionary:
    """内置字典 ⊕ 合作方字典（同 tag 以合作方为准，其余保持内置）。"""
    if profile is None:
        return BUILTIN
    fields = dict(fixdict.FIELDS)
    fields.update(profile.fields)
    if profile.msg_types:
        base = fields.get(35)
        enums = dict(base[3]) if base else {}
        enums.update(profile.msg_types)
        fields[35] = (base[0], base[1], base[2], enums) if base else (
            "MsgType", "消息类型", "char", enums)
    groups = dict(fixdict.GROUPS)
    groups.update(profile.groups)
    pairs = dict(fixdict.DATA_LENGTH_PAIRS)
    pairs.update(profile.data_pairs)
    return Dictionary(fields, groups, pairs)


def current() -> tuple[Dictionary, Profile | None]:
    """按「当前生效的字典」返回 (解析用字典, profile 或 None)。"""
    slug = get_active_slug()
    if not slug:
        return BUILTIN, None
    path = profile_dir() / "{0}.json".format(slug)
    prof = load_profile(path) if path.exists() else None
    return (merge(prof), prof) if prof else (BUILTIN, None)


# ====================================================================== 模板

TEMPLATE_JSON = """{
  "name": "合作方名称",
  "fix_version": "FIX.4.4",
  "note": "按对方接口文档整理",
  "fields": {
    "10001": {"en": "LocalOrderID", "cn": "本地订单号", "type": "String"},
    "10002": {"en": "LegSide", "cn": "腿方向", "type": "char",
              "enums": {"1": "买", "2": "卖"}}
  },
  "groups": {
    "10010": {"en": "NoSubOrders", "cn": "子订单", "members": [10011, 10012]}
  },
  "data_pairs": {"10020": 10021}
}
"""

TEMPLATE_CSV = """tag,英文名,中文名,类型,枚举,组成员
10001,LocalOrderID,本地订单号,String,,
10002,LegSide,腿方向,char,1=买;2=卖,
10010,NoSubOrders,子订单数,NumInGroup,,10011 10012
10011,SubOrderID,子订单号,String,,
"""
