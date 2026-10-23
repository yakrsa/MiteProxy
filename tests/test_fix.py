"""FIX 解析器测试（纯逻辑，不需要 QApplication）。

覆盖：检测正反例、BodyLength/CheckSum 校验、DataLength 裸值、重复组切实例、
`|` 分隔兼容、多消息切分、畸形输入不抛、上限截断。
"""

from __future__ import annotations

import pytest

from app.fix import (
    MAX_TOTAL_CHARS,
    MAX_VALUE_CHARS,
    FixField,
    FixGroup,
    human_time,
    is_fix_text,
    parse_fix,
)


# ----------------------------------------------------------------  helpers

def make_fix(body_fields, begin: str = "FIX.4.4",
             with_length: bool = True, with_sum: bool = True) -> str:
    """拼一条合法 FIX 报文（BodyLength / CheckSum 都按**字节**算，对齐协议）。"""
    body = "".join("{0}={1}\x01".format(t, v) for t, v in body_fields)
    head = "8={0}\x01".format(begin)
    if with_length:
        head += "9={0}\x01".format(len(body.encode()))
    head += body
    if with_sum:
        head += "10={0:03d}\x01".format(sum(head.encode()) % 256)
    return head


ORDER_BODY = [
    (35, "D"), (49, "SENDER"), (56, "TARGET"), (34, "42"),
    (52, "20261023-14:30:00.000"), (11, "CLORD-1"), (55, "000001"),
    (54, "1"), (38, "100"), (40, "2"), (44, "10.50"), (59, "0"),
]


# ================================================================ 检测

class TestIsFixText:
    def test_valid_message(self):
        assert is_fix_text(make_fix(ORDER_BODY)) is True

    def test_pipe_separated(self):
        assert is_fix_text(make_fix(ORDER_BODY).replace("\x01", "|")) is True

    def test_bom_and_whitespace(self):
        assert is_fix_text("\ufeff  \n" + make_fix(ORDER_BODY)) is True

    def test_fragment_without_fields(self):
        # 8/9/35 齐全才算（| 分隔的最小报文也算）；日志片段没有 9/35，不算
        assert is_fix_text("8=FIX.4.4|9=65|35=D") is True
        assert is_fix_text("8=FIX.4.4 连接建立") is False
        assert is_fix_text("8=FIX.4.4|9=65") is False

    def test_not_fix_at_all(self):
        assert is_fix_text('{"a": 1}') is False
        assert is_fix_text("") is False
        assert is_fix_text("GET / HTTP/1.1") is False

    def test_no_separator(self):
        assert is_fix_text("8=FIX.4.4 9=65 35=D") is False


# ================================================================ 基础解析

class TestParseBasic:
    def test_header_and_counts(self):
        msgs = parse_fix(make_fix(ORDER_BODY))
        assert len(msgs) == 1
        m = msgs[0]
        assert m.begin_string == "FIX.4.4"
        assert m.msg_type == "D"
        assert "新单" in m.msg_type_note
        assert m.seq_num == "42"
        assert m.sender == "SENDER"
        assert m.target == "TARGET"
        assert m.field_count == len(ORDER_BODY) + 3      # 头 8/9 + 尾 10

    def test_validations_pass(self):
        m = parse_fix(make_fix(ORDER_BODY))[0]
        assert m.errors == []
        assert m.body_length_ok is True
        assert m.checksum_ok is True
        assert m.checksum_skipped is False

    def test_first_field_tag_eight(self):
        m = parse_fix(make_fix(ORDER_BODY))[0]
        assert isinstance(m.items[0], FixField)
        assert m.items[0].tag == 8

    def test_field_comments_from_dict(self):
        m = parse_fix(make_fix(ORDER_BODY))[0]
        by_tag = {f.tag: f for f in m.fields}
        assert by_tag[54].name_cn == "买卖方向"
        assert "买入" in by_tag[54].enum_note
        assert by_tag[40].enum_note.startswith("Limit")
        assert by_tag[35].enum_note.startswith("NewOrderSingle")

    def test_unknown_tag_kept(self):
        m = parse_fix(make_fix(ORDER_BODY + [(9001, "x")]))[0]
        f = [x for x in m.fields if x.tag == 9001][0]
        assert f.known is False
        assert f.value == "x"
        assert f.name_cn == ""

    def test_human_time_helper(self):
        assert human_time("20261023-14:30:00.000") == "2026-10-23 14:30:00.000"
        assert human_time("20261023") == "2026-10-23"
        assert human_time("14:30:00") == "14:30:00"
        assert human_time("garbage") is None
        assert human_time("") is None

    def test_empty_input(self):
        assert parse_fix("") == []
        assert parse_fix("   ") == []


# ================================================================ 校验

class TestValidation:
    def test_body_length_mismatch(self):
        # 声明一个错误的 BodyLength（其余字节照实拼，CheckSum 也算对）
        body = "".join("{0}={1}\x01".format(t, v) for t, v in ORDER_BODY)
        head = "8=FIX.4.4\x019=999\x01" + body
        text = head + "10={0:03d}\x01".format(sum(ord(c) for c in head) % 256)
        m = parse_fix(text)[0]
        assert m.body_length_ok is False
        assert "body_length_mismatch" in m.errors

    def test_checksum_mismatch(self):
        text = make_fix(ORDER_BODY)
        text = text.rsplit("\x0110=", 1)[0] + "\x0110=001\x01"
        m = parse_fix(text)[0]
        assert m.checksum_ok is False
        assert "checksum_mismatch" in m.errors

    def test_missing_checksum_field(self):
        # 没有 10 字段：CheckSum 无从校验（None），BodyLength 也失去参照点
        m = parse_fix(make_fix(ORDER_BODY, with_sum=False))[0]
        assert "missing_checksum" in m.errors
        assert m.checksum_ok is None
        assert m.body_length_ok is None

    def test_non_ascii_values_validate_by_bytes(self):
        # FIX 的长度/校验和按**字节**算：Text 里带中文时按字符算会误报不符
        # （UTF-8 下 1 个汉字 = 3 字节）。make_fix 的 len(body.encode()) 就是
        # 字节语义，解析器必须跟上。
        body = [(35, "8"), (49, "S"), (56, "T"), (58, "全部成交，详见附件"),
                (11, "CL-1")]
        m = parse_fix(make_fix(body))[0]
        assert m.errors == []
        assert m.body_length_ok is True
        assert m.checksum_ok is True

    def test_not_starting_with_eight(self):
        body = "".join("{0}={1}\x01".format(t, v) for t, v in ORDER_BODY)
        text = "35=D\x01" + body
        m = parse_fix(text)[0]
        assert "missing_begin_string" in m.errors

    def test_missing_msg_type(self):
        body = [(49, "S"), (56, "T")]
        m = parse_fix(make_fix(body))[0]
        assert "missing_msg_type" in m.errors


# ================================================================ DataLength

class TestDataLength:
    def test_raw_data_with_soh_inside(self):
        # 96 的值里含 SOH：必须按长度取，不能按分隔符切
        raw = "AB\x01CD"                      # 5 字节，内含一个 SOH
        text = make_fix([(35, "d"), (55, "X"), (95, str(len(raw))), (96, raw)])
        m = parse_fix(text)[0]
        by_tag = {f.tag: f for f in m.fields}
        assert by_tag[96].value == raw
        # 后续字段（尾部的 10）没有被数据里的 SOH 打乱
        assert m.checksum_ok is True
        assert m.errors == []

    def test_length_without_partner_parses_normally(self):
        # 95 的值不是数字 / 下一字段不是 96 → 按普通字段走，不吞数据
        text = make_fix([(35, "d"), (95, "abc"), (96, "plain")])
        m = parse_fix(text)[0]
        by_tag = {f.tag: f for f in m.fields}
        assert by_tag[95].value == "abc"
        assert by_tag[96].value == "plain"


# ================================================================ 重复组

class TestRepeatingGroups:
    def _md_message(self, count: int = 2):
        body = [(35, "W"), (49, "S"), (56, "T"), (262, "REQ-1"),
                (268, str(count))]
        for i in range(count):
            body += [(279, "0"), (269, "0" if i == 0 else "1"),
                     (278, "E{0}".format(i)), (270, "10.5{0}".format(i)),
                     (271, str(100 * (i + 1)))]
        return make_fix(body)

    def test_group_structure(self):
        m = parse_fix(self._md_message(2))[0]
        groups = [it for it in m.items if isinstance(it, FixGroup)]
        assert len(groups) == 1
        g = groups[0]
        assert g.tag == 268
        assert g.count == 2
        assert len(g.instances) == 2
        assert len(g.instances[0].fields) == 5
        assert g.instances[1].fields[1].tag == 269
        assert g.instances[1].fields[1].value == "1"
        # 组内字段仍留在平铺列表里（保序）：15 个 body 字段 + 头 8/9 + 尾 10
        assert m.field_count == 18

    def test_group_fields_marked(self):
        m = parse_fix(self._md_message(2))[0]
        g = [it for it in m.items if isinstance(it, FixGroup)][0]
        assert all(f.in_group == 268 for f in g.instances[0].fields)

    def test_group_count_mismatch(self):
        # 声明 3 个但只给 2 个实例（改声明值会破坏 BodyLength/CheckSum，
        # 这里只验证结构错误码）
        text = self._md_message(2).replace("268=2", "268=3")
        m2 = parse_fix(text)[0]
        assert "group_count_mismatch" in m2.errors

    def test_unstructured_count_field_is_plain(self):
        # 124 NoExecs 是 NumInGroup 但 GROUPS 未收录 → 平铺字段
        m = parse_fix(make_fix([(35, "8"), (124, "1"), (17, "EX1")]))[0]
        assert not any(isinstance(it, FixGroup) for it in m.items)
        by_tag = {f.tag: f for f in m.fields}
        assert by_tag[124].ftype == "NumInGroup"

    def test_group_overflow_kept_flat(self):
        # 声明 1 个实例但流里有 2 份成员字段：第 2 份平铺不丢
        body = [(35, "W"), (49, "S"), (56, "T"), (268, "1"),
                (279, "0"), (269, "0"), (279, "0"), (269, "1")]
        m = parse_fix(make_fix(body))[0]
        groups = [it for it in m.items if isinstance(it, FixGroup)]
        assert len(groups) == 1
        assert len(groups[0].instances) == 1
        # 组节点之后：多出的两个成员字段平铺（再往后才是尾部 10）
        flat_after = [it for it in m.items[m.items.index(groups[0]) + 1:]]
        assert [it.tag for it in flat_after[:2]] == [279, 269]
        assert all(isinstance(it, FixField) for it in flat_after[:2])
        assert flat_after[-1].tag == 10


# ================================================================ 分隔符 / 多消息 / 兜底

class TestSeparatorAndRobustness:
    def test_pipe_separated(self):
        text = make_fix(ORDER_BODY).replace("\x01", "|")
        m = parse_fix(text)[0]
        assert m.field_count == len(ORDER_BODY) + 3
        assert m.msg_type == "D"
        # | 输入的 BodyLength 仍可校验（都是 1 字节），CheckSum 不能
        assert m.body_length_ok is True
        assert m.checksum_skipped is True
        assert m.checksum_ok is None
        assert "checksum_mismatch" not in m.errors

    def test_multiple_messages(self):
        text = make_fix(ORDER_BODY) + make_fix([(35, "8"), (49, "S"), (56, "T")])
        msgs = parse_fix(text)
        assert len(msgs) == 2
        assert msgs[0].msg_type == "D"
        assert msgs[1].msg_type == "8"
        # 第二条的 CheckSum 按全文字节算，依然对
        assert msgs[1].checksum_ok is True

    def test_multiple_pipe_messages_with_newlines(self):
        # 日志 dump 形态：| 分隔 + 消息之间带换行——两条都要解析出来
        text = (make_fix(ORDER_BODY).replace("\x01", "|") + "\n"
                + make_fix([(35, "D"), (49, "S"), (56, "T"), (11, "X2")]).replace("\x01", "|"))
        msgs = parse_fix(text)
        assert len(msgs) == 2
        assert msgs[0].msg_type == "D"
        assert msgs[1].msg_type == "D"
        assert msgs[0].field_count == len(ORDER_BODY) + 3
        assert msgs[1].field_count == 4 + 3
        assert msgs[0].body_length_ok is True

    def test_garbage_does_not_raise(self):
        for bad in ("8=FIX.4.4\x01", "8=FIX\x01\x01\x01", "8=FIX.4.4\x01abc=1\x01",
                    "8=FIX.4.4\x019=x\x0135=D", "=\x018=", "8=FIX.4.4\x019=1\x0135=D\x01junk"):
            msgs = parse_fix(bad)
            assert isinstance(msgs, list)

    def test_trailing_garbage_flagged(self):
        m = parse_fix(make_fix(ORDER_BODY) + "not-a-field")[0]
        assert "trailing_garbage" in m.errors

    def test_value_truncated_at_limit(self):
        big = "x" * (MAX_VALUE_CHARS + 100)
        m = parse_fix(make_fix([(35, "B"), (58, big)]))[0]
        f = [x for x in m.fields if x.tag == 58][0]
        assert len(f.value) <= MAX_VALUE_CHARS + 1
        assert m.truncated is True

    def test_total_truncated_at_limit(self):
        big = "8=FIX.4.4\x01" + "58=" + "x" * (MAX_TOTAL_CHARS + 10)
        msgs = parse_fix(big)
        assert msgs and msgs[0].truncated is True

    def test_bad_tag_recovers(self):
        text = make_fix([(35, "D"), (49, "S"), (56, "T")])
        text = text.replace("49=", "ab=", 1)
        m = parse_fix(text)[0]
        assert "bad_field" in m.errors
        assert m.msg_type == "D"      # 坏字段之后的 56 还能解析出来


if __name__ == "__main__":     # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
