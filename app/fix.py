"""FIX 协议报文解析（FIX 4.0–4.4，对齐 sse.py 的纯函数模式）。

FIX 报文是 SOH（\\x01）分隔的 tag=value 序列：

    8=FIX.4.4\\x019=112\\x0135=D\\x0149=SENDER\\x0156=TARGET\\x01...\\x0110=123\\x01

设计约束（与 sse.py / bodyview.py 一脉相承）：

1. **纯逻辑、零 Qt 依赖**：解析与界面分离，单测不需要 QApplication；
2. **畸形输入不抛异常**：这是抓包/调试工具的兜底职责，任何输入都要给出
   一个能显示的结果，最差也是原文；
3. **上限防失控**：总量 / 字段数 / 单值长度三道闸门，超过即截断并标注；
4. **可自校验**：BodyLength(9) 与 CheckSum(10) 是协议内置校验点，解析结果
   必须带上校验状态，让用户一眼看出报文是否完整、有没有被改过；
5. **错误码而不是中文文案**：本模块不产中文（界面文案归 UI 层翻译），
   结构性问题以错误码上报，UI 层用 ERROR_NOTES 映射成提示。

两个解析难点（专业 FIX 解析器与玩具的分界线）：

- **DataLength 字段**：95/96、93/89 这类「长度 + 裸数据」对，数据值里
  可能含 SOH，必须按声明的长度原样读取，不能按分隔符切；
- **重复组**：如 NoRelatedSym(146)，流式 tag=value 里没有显式边界，
  按「成员 tag 在单个实例内不重复」的启发式切实例（成员定义见 fixdict.GROUPS）。

分隔符：标准是 SOH，但日志导出常把 SOH 写成 `|`，粘贴板也会丢控制符——
两种都吃。`|` 输入的 CheckSum 无法校验（分隔符字节值不同），如实标注
checksum_skipped，不硬报校验失败。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app import fixdict

#: 字段分隔符（FIX 标准 SOH）与日志导出常用的替代符
SOH = "\x01"
PIPE = "|"

#: 单次解析的字符总量上限（对齐 bodyview.BODY_PREVIEW_LIMIT）
MAX_TOTAL_CHARS = 512 * 1024
#: 单消息字段数上限：正常消息几十个字段，5000 足够覆盖畸形/恶意输入
MAX_FIELDS = 5000
#: 单个字段值的字符上限（RawData / EncodedText 可能很大）
MAX_VALUE_CHARS = 64 * 1024

#: 错误码（UI 层翻译，见 fix_panel.ERROR_NOTES）：
#:   missing_begin_string   首字段不是 8=FIX
#:   missing_body_length    没有 9=
#:   missing_msg_type       没有 35=
#:   missing_checksum       没有 10=
#:   body_length_mismatch   BodyLength 与实际字节数不符
#:   checksum_mismatch      CheckSum 与计算值不符
#:   group_count_mismatch   重复组声明个数与解析出的实例数不符
#:   group_overflow         组实例数已达声明值仍有成员字段（已平铺展示）
#:   bad_field             有形如「tag 不是数字」的残字段
#:   trailing_garbage      尾部有不成字段的内容
#:   too_many_fields       字段数超上限，后续内容未解析

_TS_RE = re.compile(
    r"^(?P<y>\d{4})(?P<mo>\d{2})(?P<d>\d{2})"
    r"(?:-(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})(?:\.(?P<frac>\d+))?)?"
)
_TIME_RE = re.compile(r"^(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})(?:\.(?P<frac>\d+))?")

#: SOH 的转义形式（日志导出 / JSON / caret notation 常把控制符写成字面量）：
#: `\u0001`（JSON）、`\U00000001`、`\x01` / `\x1`（repr / 日志）、
#: `^A`（caret notation，FIX 日志查看器常用）、`<SOH>`、`&#01;` / `&#x01;`。
#: 长的放前面，避免 `\x01` 被 `\x1` 抢先匹配一半。
_ESCAPED_SOH_RE = re.compile(
    r"\\u0001|\\U00000001|\\x01|\\x1|\^A|<SOH>|&#x?0*1;")

#: 消息头前的日志垃圾（tag 段形如 `[09:30:01.123] 8`）：末尾数字是被污染的
#: BeginString tag，前面是时间戳 / 行号 / 日志级别。见 _scan 的恢复分支。
#: 必须 DOTALL——日志里每条报文各自占一行，残段形如 `\n[09:30:02.456] 8`，
#: 默认模式下 `.` 不匹配 `\n`，整条判据会静默失效（多条被并成一条）。
_JUNK_HEAD_RE = re.compile(r"^.*?(?P<tag>\d+)$", re.DOTALL)


# ====================================================================== 数据模型

@dataclass
class FixField:
    """一个 tag=value 字段（含字典注释）。"""

    tag: int
    value: str
    #: 字典收录时的注释；known=False 时下面四项为空
    name_en: str = ""
    name_cn: str = ""
    ftype: str = ""
    #: 值命中字典 enum 时的释义（如 54=1 → "Buy 买入"）
    enum_note: str = ""
    known: bool = True
    #: 所属重复组引导 tag（0 = 顶层字段）
    in_group: int = 0


@dataclass
class FixGroupInstance:
    """重复组的一个实例（如一条 NoRelatedSym）。"""

    index: int                      # 从 1 开始
    fields: list[FixField] = field(default_factory=list)


@dataclass
class FixGroup:
    """重复组节点（树视图里可折叠）。"""

    tag: int                        # 引导 tag（如 146）
    name_en: str
    name_cn: str
    count: int                      # 声明的实例数
    instances: list[FixGroupInstance] = field(default_factory=list)


@dataclass
class FixMessage:
    """一条完整 FIX 消息。

    `items` 是保序的展示序列：FixField（顶层字段）与 FixGroup（重复组节点）
    交替出现；`fields` 是全部字段的平铺列表（含组内字段）。
    """

    items: list = field(default_factory=list)      # FixField | FixGroup
    fields: list[FixField] = field(default_factory=list)
    begin_string: str = ""
    msg_type: str = ""
    msg_type_note: str = ""
    seq_num: str = ""
    sender: str = ""
    target: str = ""
    sending_time: str = ""
    #: 声明的 BodyLength(9) / 实际值（None = 报文里没有该字段）
    declared_body_length: int | None = None
    actual_body_length: int | None = None
    body_length_ok: bool | None = None
    #: 声明的 CheckSum(10) / 计算值
    declared_checksum: int | None = None
    actual_checksum: int | None = None
    checksum_ok: bool | None = None
    #: `|` 分隔输入：分隔符字节与 SOH 不同，CheckSum 无从校验
    checksum_skipped: bool = False
    #: 输入被截断（总量超限）
    truncated: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def field_count(self) -> int:
        return len(self.fields)


# ====================================================================== 检测

def _strip_stream_junk(text: str) -> str:
    """剥离流开头的非字段垃圾（日志复制常带时间戳 / 行号 / 日志级别）。

    判据是「`8=FIX` 之前没有真实字段」：正常字段一定以分隔符结尾，所以
    前缀里既没有 `=`、也没有 SOH / `|` 时即可剥离。两种形态都要吃：

    - `[09:30:01.123] 8=FIX.4.2…`（纯时间戳，不含 `=`）
    - `level=INFO 8=FIX.4.2…`（日志级别自带 `=`，但整段无分隔符）

    含分隔符就不动——那说明前面确实有字段，误切代价更大。干净输入原样返回。
    """
    if text.startswith("8=FIX"):
        return text
    pos = text.find("8=FIX")
    if pos > 0:
        head = text[:pos]
        if "=" not in head or (SOH not in head and PIPE not in head):
            return text[pos:]
    return text


def _unescape_separators(text: str) -> str:
    """把 SOH 的转义形式还原成真 SOH。

    从日志 / JSON / 工单系统复制的 FIX 文本，控制符常被转义成字面量
    （`\\u0001`、`\\x01`、`^A` 等），粘贴进来就没有任何分隔符可用。
    本函数在这些形式出现时逐个替换回 SOH——替换是 1:1 的，正好恢复
    线上字节形态，因此 BodyLength / CheckSum 照常可校验（不像 `|`
    归一化那样必须标「未校验」）。

    两道保险防止误伤：文本已含真 SOH 时原样返回；只有以 `8=FIX` 开头
    （容忍 BOM / 前导空白 / 日志垃圾前缀）才替换——普通代码片段里的
    `\\x01` 字面量不会被碰。
    """
    if not text or SOH in text:
        return text
    head = _strip_stream_junk(text.lstrip().lstrip("\ufeff").lstrip())
    if not head.startswith("8=FIX"):
        return text
    return _ESCAPED_SOH_RE.sub(SOH, text)


def is_fix_text(text: str) -> bool:
    """一段文本像不像 FIX 报文。

    判定三条件（缺一不可）：
    1. 以 `8=FIX` 开头（容忍 BOM / 空白 / 日志垃圾前缀）；
    2. 含 SOH 或 `|` 分隔符——SOH 的转义形式（`\\u0001` / `\\x01` /
       `^A` 等）会先被还原成真 SOH 再判定；
    3. 前若干字段里能同时找到 8 / 9 / 35——这是任意合法 FIX 消息的最小集，
       也足够把 `8=FIX.4.4` 这种日志片段排除掉。
    """
    t = (text or "").strip().lstrip("\ufeff").strip()
    # 粘贴来的可能是转义形式（\u0001 / \x01 / ^A…），先还原成真 SOH
    t = _unescape_separators(t)
    # 日志复制常带行首垃圾（时间戳 / 行号 / 日志级别）：虚拟剥离后再判定，
    # 真正剥离发生在 parse_fix（这里只影响「像不像」的结论）
    t = _strip_stream_junk(t)
    if not t.startswith("8=FIX"):
        return False
    if SOH in t:
        parts = t.split(SOH, 12)[:12]
    elif PIPE in t:
        parts = t.split(PIPE, 12)[:12]
    else:
        return False
    tags = set()
    for part in parts:
        eq = part.find("=")
        if eq > 0 and part[:eq].isdigit():
            tags.add(int(part[:eq]))
    return {8, 9, 35} <= tags


def human_time(value: str) -> str | None:
    """FIX 时间字段转人话。

    `20261023-18:00:00.123` → `2026-10-23 18:00:00.123`；
    `20261023` → `2026-10-23`；`18:00:00.123` → `18:00:00.123`。
    认不出的格式返回 None（调用方回落到显示原值）。
    """
    v = (value or "").strip()
    if not v:
        return None
    m = _TS_RE.match(v)
    if m:
        g = m.groupdict()
        if g["hh"] is None:
            return "{0}-{1}-{2}".format(g["y"], g["mo"], g["d"])
        out = "{0}-{1}-{2} {3}:{4}:{5}".format(
            g["y"], g["mo"], g["d"], g["hh"], g["mm"], g["ss"])
        if g["frac"]:
            out += "." + g["frac"]
        return out
    m = _TIME_RE.match(v)
    if m:
        g = m.groupdict()
        out = "{0}:{1}:{2}".format(g["hh"], g["mm"], g["ss"])
        if g["frac"]:
            out += "." + g["frac"]
        return out
    return None


# ====================================================================== 扫描

def _scan(text: str) -> tuple[list[tuple], list[str]]:
    """把文本切成 [(tag, value, 字段起始位, SOH 位)]，并处理 DataLength 对。

    返回的位置是**全文绝对偏移**：多消息文本里第 2 条的 CheckSum 也要按
    全文字节算，所以不能按消息重置坐标系。畸形段不抛异常，记错误码后尽量
    恢复到下一个分隔符继续。
    """
    out: list[tuple] = []
    errors: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        eq = text.find("=", i)
        if eq < 0:
            if text[i:].strip():
                errors.append("trailing_garbage")
            break
        tag_str = text[i:eq]
        if not tag_str.isdigit():
            # 容忍字段之间的空白（日志 dump 常在分隔符后带换行/缩进）：
            # 跳过前导空白再认一次 tag，认不出才算残字段
            j = i
            while j < eq and text[j] in " \t\r\n":
                j += 1
            if j < eq and text[j:eq].isdigit():
                i = j
                tag_str = text[i:eq]
            else:
                # 消息边界前的日志垃圾（`...10=100\x01[09:30:02.456] 8=FIX.4.2`）：
                # tag_str 形如 `[09:30:02.456] 8`。末尾 tag 是 8、值以 FIX 开头、
                # junk 段不含 = → 被污染的消息头，剥离 junk 恢复干净边界
                # （_split_messages 依赖 8=FIX 边界切分多消息）。
                m = _JUNK_HEAD_RE.match(tag_str)
                if (m and m.group("tag") == "8"
                        and text.startswith("FIX", eq + 1)
                        and "=" not in tag_str[:m.start("tag")]):
                    tag_str = "8"
                    i = eq - 1
                else:
                    # 兜底：残段里若还藏着一个完整消息头，直接跳过去重扫。
                    # 上面那条判据要求 junk 段不含 `=`，而真实日志前缀常带
                    # `level=INFO` / `tid=12`，此时 eq 落在前缀的 `=` 上，判据
                    # 直接失效 → 整条消息头被当残字段吃掉。这里只认「下一个
                    # 分隔符之前出现的 8=FIX」，不会误伤正常字段值。
                    nxt_fix = text.find("8=FIX", i)
                    soh = text.find(SOH, i)
                    if 0 <= nxt_fix and (soh < 0 or nxt_fix < soh):
                        i = nxt_fix
                        continue
                    errors.append("bad_field")
                    nxt = text.find(SOH, i)
                    if nxt < 0:
                        break
                    i = nxt + 1
                    continue
        tag = int(tag_str)
        end = text.find(SOH, eq + 1)          # 本字段值的结束 SOH（或 -1）

        # DataLength 特例：当前字段是长度字段、值是数字、且下一字段正是
        # 配对的数据 tag → 按长度原样取数据值（里面可能含 SOH）
        partner = fixdict.data_partner(tag)
        if partner is not None and end >= 0:
            value = text[eq + 1:end]
            prefix = "{0}=".format(partner)
            if value.isdigit() and text.startswith(prefix, end + 1):
                length = int(value)
                data_start = end + 1 + len(prefix)
                raw = text[data_start:data_start + length]
                soh_after = text.find(SOH, data_start + length)
                out.append((tag, value, i, end))
                out.append((partner, raw, end + 1,
                            soh_after if soh_after >= 0 else n))
                i = (soh_after + 1) if soh_after >= 0 else n
                if len(out) >= MAX_FIELDS:
                    errors.append("too_many_fields")
                    break
                continue

        fstart = i
        value = text[eq + 1:end] if end >= 0 else text[eq + 1:]
        soh_pos = end if end >= 0 else n
        # 上一条末尾的 SOH 丢失时（`…10=123\n8=FIX.4.2\x01…`），本字段的值会
        # 把下一条的消息头一起吞掉，8 就不在字段边界上，_split_messages
        # 切不开 → 多条并成一条。值里出现「空白 + 8=FIX」且前半是纯数字
        # （典型就是 CheckSum）时在此截断，让 8 回到边界重新参与切分。
        cut = value.find("8=FIX")
        if cut > 0 and value[cut - 1] in " \t\r\n":
            head_part = value[:cut]
            first = head_part.strip().split()[0] if head_part.strip() else ""
            # 前半是纯数字（CheckSum / 长度）且不含 `=` → 是上一条的尾巴，
            # 结尾那段 8=FIX 属于下一条；前半只是普通文本（Text 字段里提到
            # 「see 8=FIX.4.2 doc」）则不动
            if first.isdigit() and "=" not in head_part:
                value = first
                soh_pos = eq + 1 + cut - 1
                i = eq + 1 + cut
            else:
                i = (end + 1) if end >= 0 else n
        elif tag == 10 and len(value) > 3 and value[:3].isdigit() \
                and value[3:8] == "8=FIX":
            # 连空白都没有（`10=1238=FIX.4.2`）：CheckSum 固定 3 位，其余是下一条
            value = value[:3]
            soh_pos = eq + 4 - 1
            i = eq + 4
        else:
            i = (end + 1) if end >= 0 else n
        out.append((tag, value, fstart, soh_pos))
        if len(out) >= MAX_FIELDS:
            errors.append("too_many_fields")
            break
    return out, errors


def _split_messages(raw: list[tuple]) -> list[list[tuple]]:
    """按 8=FIX 边界切分多条消息（日志 dump 常是一次粘贴多条）。

    只有「位于字段边界、值以 FIX 开头」的 8 才算新消息起点——数据字段里
    恰好出现 `8=FIX` 字样不会误切（那种内容在扫描阶段已按长度/分隔符归位）。
    """
    messages: list[list[tuple]] = []
    current: list[tuple] = []
    for item in raw:
        tag, value = item[0], item[1]
        if tag == 8 and value.startswith("FIX") and current:
            messages.append(current)
            current = []
        current.append(item)
    if current:
        messages.append(current)
    return messages


# ====================================================================== 结构

def _structure(fields: list[FixField]) -> tuple[list, list[str]]:
    """把平铺字段组织成展示序列（顶层字段 + 重复组节点）。

    重复组切实例的启发式：成员 tag 在单个实例内不重复——实例 2 的同一 tag
    出现即开启新实例。字典没收录成员的组不在这里展开（GROUPS 之外），
    由界面在注释列说明「未收录，后续字段平铺」。
    """
    items: list = []
    errors: list[str] = []
    i = 0
    n = len(fields)
    while i < n:
        f = fields[i]
        gdef = fixdict.group_of(f.tag) if f.ftype == "NumInGroup" else None
        if gdef is None:
            items.append(f)
            i += 1
            continue
        name_en, name_cn, members = gdef
        count = int(f.value) if f.value.isdigit() else 0
        group = FixGroup(tag=f.tag, name_en=name_en, name_cn=name_cn, count=count)
        items.append(group)
        i += 1
        if count <= 0:
            # 声明 0 个实例（或数值异常）：不收成员，后续字段平铺展示
            continue
        instances: list[FixGroupInstance] = []
        cur: list[FixField] = []
        seen: set[int] = set()
        while i < n and len(instances) < count:
            nxt = fields[i]
            if nxt.tag not in members:
                break
            if nxt.tag in seen and cur:
                instances.append(FixGroupInstance(len(instances) + 1, cur))
                cur, seen = [], set()
            cur.append(nxt)
            seen.add(nxt.tag)
            i += 1
        if cur and len(instances) < count:
            instances.append(FixGroupInstance(len(instances) + 1, cur))
            cur = []
        for inst in instances:
            for ff in inst.fields:
                ff.in_group = f.tag
        group.instances = instances
        if cur:
            # 实例数已达声明值仍有成员字段：不丢数据，平铺在组节点后面
            for ff in cur:
                items.append(ff)
            errors.append("group_overflow")
        if len(instances) != count:
            errors.append("group_count_mismatch")
    return items, errors


# ====================================================================== 解析

def _build_message(raw: list[tuple], text: str,
                   pipe_normalized: bool, msg_start: int) -> FixMessage:
    """把一个消息的原始字段列表构造成 FixMessage（含头信息与校验）。

    `msg_start` 是本消息在全文里的起始偏移：CheckSum 只从消息开头累加，
    多消息文本里第 2 条不能把第 1 条的字节算进去。
    """
    msg = FixMessage()
    fields: list[FixField] = []
    for tag, value, _fstart, _soh in raw:
        entry = fixdict.lookup(tag)
        if entry is not None:
            name_en, name_cn, ftype, enums = entry
            f = FixField(tag=tag, value=value, name_en=name_en,
                         name_cn=name_cn, ftype=ftype,
                         enum_note=enums.get(value, ""), known=True)
        else:
            f = FixField(tag=tag, value=value, known=False)
        if len(f.value) > MAX_VALUE_CHARS:
            f.value = f.value[:MAX_VALUE_CHARS] + "…"
            msg.truncated = True
        fields.append(f)
    msg.fields = fields

    # 头信息 + 校验所需的位置（9 的结束 SOH、10 的字段起点）
    soh_of_9: int | None = None
    start_of_10: int | None = None
    for f, item in zip(fields, raw):
        tag, value, fstart, soh = item
        if tag == 8 and not msg.begin_string:
            msg.begin_string = value
        elif tag == 9 and msg.declared_body_length is None:
            msg.declared_body_length = int(value) if value.isdigit() else None
            soh_of_9 = soh
        elif tag == 10 and msg.declared_checksum is None:
            msg.declared_checksum = int(value) if value.isdigit() else None
            start_of_10 = fstart
        elif tag == 35 and not msg.msg_type:
            msg.msg_type = value
            msg.msg_type_note = f.enum_note
        elif tag == 34 and not msg.seq_num:
            msg.seq_num = value
        elif tag == 49 and not msg.sender:
            msg.sender = value
        elif tag == 56 and not msg.target:
            msg.target = value
        elif tag == 52 and not msg.sending_time:
            msg.sending_time = value

    if not fields or fields[0].tag != 8:
        msg.errors.append("missing_begin_string")
    if msg.declared_body_length is None:
        msg.errors.append("missing_body_length")
    if not msg.msg_type:
        msg.errors.append("missing_msg_type")
    if msg.declared_checksum is None:
        msg.errors.append("missing_checksum")

    if soh_of_9 is not None and start_of_10 is not None:
        # BodyLength：从 9 字段结束 SOH 之后，到 10 字段前的 SOH（含）。
        # **按 UTF-8 字节计而不是字符数**——FIX 的长度单位是字节，报文里出现
        # 中文（Text/EncodedText 等）时按字符算会差出 2 字节/字，误报不符。
        msg.actual_body_length = len(
            text[soh_of_9 + 1:start_of_10].encode("utf-8"))
        msg.body_length_ok = (
            msg.declared_body_length is not None
            and msg.actual_body_length == msg.declared_body_length
        )
        if not msg.body_length_ok:
            msg.errors.append("body_length_mismatch")
        # CheckSum：10 字段之前全部字节（含那个 SOH）累加 mod 256。
        # 同样按 UTF-8 字节：线上传的是字节，不是字符。
        if pipe_normalized:
            msg.checksum_skipped = True
        elif msg.declared_checksum is not None:
            msg.actual_checksum = sum(
                text[msg_start:start_of_10].encode("utf-8")) % 256
            msg.checksum_ok = (msg.actual_checksum == msg.declared_checksum)
            if not msg.checksum_ok:
                msg.errors.append("checksum_mismatch")

    msg.items, struct_errors = _structure(fields)
    msg.errors.extend(struct_errors)
    return msg


def parse_fix(text: str) -> list[FixMessage]:
    """解析一段文本 → 消息列表（一段里可能有多条消息）。

    空输入 / 完全不像 FIX 的输入返回空列表——调用方应先用 is_fix_text
    判定，或对空结果走「原文 + 说明」的回落。任何畸形输入都不抛异常。
    """
    if not text or not text.strip():
        return []
    raw_text = text.strip().lstrip("\ufeff").strip()
    # 转义形式（\u0001 / \x01 / ^A…）先还原成真 SOH；`|` 归一在其后，
    # 二者互斥不冲突（还原后已有 SOH，| 分支不会触发）。
    # 日志复制的行首垃圾（时间戳 / 行号 / 日志级别）在还原后剥离——
    # is_fix_text 只做虚拟剥离判定，真正剥离在这里发生一次。
    raw_text = _strip_stream_junk(_unescape_separators(raw_text))
    truncated = False
    if len(raw_text) > MAX_TOTAL_CHARS:
        raw_text = raw_text[:MAX_TOTAL_CHARS]
        truncated = True

    pipe_normalized = False
    if SOH not in raw_text and PIPE in raw_text \
            and raw_text.startswith("8=FIX"):
        raw_text = raw_text.replace(PIPE, SOH)
        pipe_normalized = True

    raw, scan_errors = _scan(raw_text)
    if not raw:
        return []

    messages: list[FixMessage] = []
    for chunk in _split_messages(raw):
        msg = _build_message(chunk, raw_text, pipe_normalized,
                             chunk[0][2] if chunk else 0)
        if truncated:
            msg.truncated = True
        messages.append(msg)
    # 扫描级问题（残字段 / 尾部垃圾）挂在最后一条上：它们都出现在流的尾部
    if messages and scan_errors:
        for code in scan_errors:
            if code not in messages[-1].errors:
                messages[-1].errors.append(code)
    return messages
