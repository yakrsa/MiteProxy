"""合作方 FIX 字典（app/fixprofile）测试：导入解析 / 合并 / 存取。

不碰真实配置目录：所有落盘用例都用 monkeypatch 把 fixprofile.CONFIG_DIR
指到 tmp_path。
"""

from __future__ import annotations

import json

import pytest

from app import fixprofile
from app.fix import parse_fix


# ----------------------------------------------------------------  helpers

CSV_WITH_HEADER = """tag,英文名,中文名,类型,枚举,组成员
10001,LocalOrderID,本地订单号,String,,
10002,LegSide,腿方向,char,1=买;2=卖,
10010,NoSubOrders,子订单数,NumInGroup,,10011 10012
10011,SubOrderID,子订单号,String,,
"""

JSON_OBJECT = {
    "name": "XX 期货",
    "fix_version": "FIX.4.4",
    "note": "2026-10 版",
    "fields": {
        "10001": {"en": "LocalOrderID", "cn": "本地订单号", "type": "String"},
        "10002": {"en": "LegSide", "cn": "腿方向", "enum": "1=买;2=卖"},
    },
    "msg_types": {"U": "TradeCaptureReport 成交确认"},
    "groups": {"10010": {"en": "NoSubOrders", "cn": "子订单",
                         "members": [10011, 10012]}},
    "data_pairs": {"10020": 10021},
}


def make_fix(body_fields) -> str:
    body = "".join("{0}={1}\x01".format(t, v) for t, v in body_fields)
    head = "8=FIX.4.4\x019={0}\x01".format(len(body.encode())) + body
    return head + "10={0:03d}\x01".format(sum(head.encode()) % 256)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """隔离配置目录（fixprofile.profile_dir 依赖模块级 CONFIG_DIR）。"""
    monkeypatch.setattr(fixprofile, "CONFIG_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------- 导入格式

class TestImportCsv:
    def test_header_aliases_and_enums(self):
        prof, warnings = fixprofile.parse_profile_text(CSV_WITH_HEADER)
        assert warnings == []
        assert prof.fields[10001] == ("LocalOrderID", "本地订单号", "String", {})
        assert prof.fields[10002][3] == {"1": "买", "2": "卖"}
        # 组成员列 → 重复组定义
        assert prof.groups[10010] == ("NoSubOrders", "子订单数", (10011, 10012))

    def test_without_header_reads_positional(self):
        prof, _ = fixprofile.parse_profile_text(
            "10001,LocalOrderID,本地订单号,String\n"
            "10002,LegSide,腿方向,char,1=买;2=卖\n")
        assert prof is not None
        assert prof.fields[10001][1] == "本地订单号"
        assert prof.fields[10002][3] == {"1": "买", "2": "卖"}

    def test_tsv_accepted(self):
        prof, _ = fixprofile.parse_profile_text(
            "tag\t英文名\t中文名\n10001\tLocalOrderID\t本地订单号\n")
        assert prof.fields[10001][:2] == ("LocalOrderID", "本地订单号")

    def test_comment_and_blank_lines_skipped(self):
        prof, warnings = fixprofile.parse_profile_text(
            "# 这是注释\n\ntag,中文名\n10001,本地订单号\n")
        assert warnings == []
        assert list(prof.fields) == [10001]

    def test_bad_rows_reported_not_fatal(self):
        prof, warnings = fixprofile.parse_profile_text(
            "tag,中文名\nabc,坏行\n10001,本地订单号\n")
        assert prof is not None and list(prof.fields) == [10001]
        # 报文件里的真实行号（= Excel 里看到的行号），用户能直接回去改
        assert warnings and "第 2 行" in warnings[0]

    def test_no_field_returns_none(self):
        prof, warnings = fixprofile.parse_profile_text("这不是字段表\n随便一段话\n")
        assert prof is None
        assert warnings


class TestImportFromDocs:
    """「PDF / Word 的字段表整段贴进 Excel，另存 CSV 就能导」的容错。"""

    def test_title_rows_before_header_are_noise(self):
        prof, warnings = fixprofile.parse_profile_text(
            "XX 期货 FIX 接口字段说明\n"
            "\n"
            "Tag（必填）,字段名称,数据类型,取值说明\n"
            "10001,LocalOrderID,String,-\n"
            "10002,腿方向,char,1=买;2=卖\n")
        assert warnings == []
        # 「（必填）」不影响认表头；`-` 当空枚举
        assert prof.fields[10001] == ("LocalOrderID", "", "String", {})
        # 只有一列中文名时归到中文名列，不占英文名列
        assert prof.fields[10002][:3] == ("", "腿方向", "char")
        assert prof.fields[10002][3] == {"1": "买", "2": "卖"}

    def test_serial_column_not_mistaken_for_tag(self):
        prof, _ = fixprofile.parse_profile_text(
            "序号,Tag,字段名称,说明\n"
            "1,10001,LocalOrderID,本地订单号\n"
            "2,10002,LegSide,腿方向\n")
        assert sorted(prof.fields) == [10001, 10002]
        assert prof.fields[10001] == ("LocalOrderID", "本地订单号", "", {})

    def test_weak_tag_header_when_no_strong_one(self):
        prof, _ = fixprofile.parse_profile_text(
            "编号,英文名,中文名\n10001,LocalOrderID,本地订单号\n")
        assert list(prof.fields) == [10001]

    def test_fullwidth_digits_and_dash_placeholder(self):
        prof, _ = fixprofile.parse_profile_text(
            "tag,英文名,中文名,类型,枚举\n"
            "１０００１,LocalOrderID,本地订单号,String,－\n")
        assert prof.fields[10001] == ("LocalOrderID", "本地订单号", "String", {})

    def test_whitespace_aligned_text(self):
        # 从 PDF 直接复制（没过 Excel）：列之间是多个空格
        prof, _ = fixprofile.parse_profile_text(
            "Tag          英文名              中文名        类型\n"
            "10001        LocalOrderID        本地订单号    String\n")
        assert prof.fields[10001][:3] == ("LocalOrderID", "本地订单号", "String")

    def test_excel_sep_hint_line_skipped(self):
        prof, _ = fixprofile.parse_profile_text(
            "sep=,\nTag,中文名\n10001,本地订单号\n")
        assert list(prof.fields) == [10001]

    def test_metadata_comments_become_name_and_version(self):
        prof, _ = fixprofile.parse_profile_text(
            "# 合作方: XX 期货\n"
            "# 版本: FIX.4.4\n"
            "# 备注: 2026Q4 版\n"
            "tag,中文名\n10001,本地订单号\n")
        assert prof.name == "XX 期货"
        assert prof.fix_version == "FIX.4.4"
        assert prof.note == "2026Q4 版"

    def test_comment_without_metadata_still_ignored(self):
        prof, _ = fixprofile.parse_profile_text(
            "# 这是说明，没有冒号\n# TODO 回头补 10002\ntag,中文名\n10001,本地订单号\n")
        assert list(prof.fields) == [10001]

    def test_enum_values_with_commas(self):
        prof, _ = fixprofile.parse_profile_text(
            "tag,英文名,枚举\n"
            "10003,LegSide,1=部分成交，剩余 200;2=Filled\n")
        assert prof.fields[10003][3] == {"1": "部分成交，剩余 200", "2": "Filled"}

    def test_gbk_csv_read_from_disk(self, tmp_path):
        # 中文 Windows 上 Excel 另存的 CSV 是 GB18030，没有 BOM
        path = tmp_path / "xx.csv"
        path.write_bytes(
            "Tag,英文名,中文名\n10001,LocalOrderID,本地订单号\n".encode("gb18030"))
        text = fixprofile.read_profile_file(path)
        prof, _ = fixprofile.parse_profile_text(text)
        assert prof.fields[10001][1] == "本地订单号"

    def test_utf16_csv_read_from_disk(self, tmp_path):
        path = tmp_path / "xx.csv"
        path.write_bytes(
            "Tag,中文名\n10001,本地订单号\n".encode("utf-16"))
        prof, _ = fixprofile.parse_profile_text(
            fixprofile.read_profile_file(path))
        assert prof.fields[10001][1] == "本地订单号"


class TestImportJson:
    def test_object_schema(self):
        prof, warnings = fixprofile.parse_profile_text(json.dumps(JSON_OBJECT))
        assert warnings == []
        assert prof.name == "XX 期货"
        assert prof.fix_version == "FIX.4.4"
        assert prof.fields[10002][3] == {"1": "买", "2": "卖"}
        assert prof.msg_types == {"U": "TradeCaptureReport 成交确认"}
        assert prof.groups[10010] == ("NoSubOrders", "子订单", (10011, 10012))
        assert prof.data_pairs == {10020: 10021}

    def test_flat_list_schema(self):
        prof, _ = fixprofile.parse_profile_text(json.dumps([
            {"tag": 10001, "en": "LocalOrderID", "cn": "本地订单号"},
            {"tag": "10002", "cn": "策略编号", "enums": {"A": "算法"}},
            {"tag": "bad", "cn": "坏行"},
        ]))
        assert sorted(prof.fields) == [10001, 10002]
        assert prof.fields[10002][3] == {"A": "算法"}

    def test_invalid_json_returns_reason(self):
        prof, warnings = fixprofile.parse_profile_text("{oops}")
        assert prof is None and "JSON" in warnings[0]

    def test_template_is_valid(self):
        prof, warnings = fixprofile.parse_profile_text(fixprofile.TEMPLATE_JSON)
        assert warnings == [] and prof.fields
        csv_prof, _ = fixprofile.parse_profile_text(fixprofile.TEMPLATE_CSV)
        assert csv_prof.groups


# ---------------------------------------------------------------- 合并

class TestMerge:
    def test_private_tag_resolves_and_group_expands(self):
        prof, _ = fixprofile.parse_profile_text(CSV_WITH_HEADER)
        msg = parse_fix(make_fix([
            (35, "8"), (49, "S"), (56, "T"),
            (10001, "LOC-9"), (10002, "2"),
            (10010, "2"), (10011, "A"), (10011, "B"),
        ]), fixprofile.merge(prof))[0]
        names = {f.tag: f.name_cn for f in msg.fields}
        assert names[10001] == "本地订单号"
        assert [f.enum_note for f in msg.fields if f.tag == 10002] == ["卖"]
        groups = [i for i in msg.items if hasattr(i, "instances")]
        assert groups and groups[0].tag == 10010
        assert [len(g.fields) for g in groups[0].instances] == [1, 1]

    def test_builtin_fields_still_available(self):
        prof, _ = fixprofile.parse_profile_text("tag,中文名\n10001,本地订单号\n")
        d = fixprofile.merge(prof)
        assert d.lookup(55) is not None      # 内置 Symbol 还在
        assert d.lookup(10001) is not None   # 合作方字段也在

    def test_profile_overrides_builtin_tag(self):
        # 对方把 58 重新定义成「业务提示」时按对方文档走
        prof, _ = fixprofile.parse_profile_text("tag,英文名,中文名\n58,BizHint,业务提示\n")
        assert fixprofile.merge(prof).lookup(58)[1] == "业务提示"
        assert fixprofile.BUILTIN.lookup(58)[1] == "文本"

    def test_msg_types_merge(self):
        prof, _ = fixprofile.parse_profile_text(json.dumps(JSON_OBJECT))
        d = fixprofile.merge(prof)
        assert d.lookup(35)[3]["U"].startswith("TradeCaptureReport")
        assert d.lookup(35)[3]["8"].startswith("ExecutionReport")  # 内置仍在

    def test_without_profile_behaves_as_builtin(self):
        assert fixprofile.merge(None) is fixprofile.BUILTIN
        msg = parse_fix(make_fix([(35, "D"), (10001, "x")]))[0]
        assert [f.known for f in msg.fields if f.tag == 10001] == [False]


# ---------------------------------------------------------------- 存取 / 当前字典

class TestStorage:
    def test_save_load_list_roundtrip(self, home):
        prof, _ = fixprofile.parse_profile_text(CSV_WITH_HEADER, slug="xx")
        prof.name = "XX 期货"
        path = fixprofile.save_profile(prof)
        assert path.exists()
        loaded = fixprofile.list_profiles()
        assert [p.slug for p in loaded] == ["xx"]
        assert loaded[0].name == "XX 期货"
        assert loaded[0].fields[10001][1] == "本地订单号"

    def test_active_slug_persisted_and_validated(self, home):
        assert fixprofile.get_active_slug() == ""
        prof, _ = fixprofile.parse_profile_text(CSV_WITH_HEADER, slug="xx")
        fixprofile.save_profile(prof)
        fixprofile.set_active_slug("xx")
        assert fixprofile.get_active_slug() == "xx"
        assert fixprofile.current()[1].slug == "xx"
        # 文件被删掉后不能继续指向它（否则每次解析都要读空文件）
        fixprofile.delete_profile("xx")
        assert fixprofile.get_active_slug() == ""

    def test_delete_removes_file(self, home):
        prof, _ = fixprofile.parse_profile_text(CSV_WITH_HEADER, slug="xx")
        fixprofile.save_profile(prof)
        assert fixprofile.delete_profile("xx") is True
        assert fixprofile.list_profiles() == []

    def test_broken_file_skipped_in_list(self, home):
        (home / fixprofile.PROFILE_DIR_NAME).mkdir(parents=True, exist_ok=True)
        (home / fixprofile.PROFILE_DIR_NAME / "bad.json").write_text(
            "{oops", encoding="utf-8")
        prof, _ = fixprofile.parse_profile_text(CSV_WITH_HEADER, slug="good")
        fixprofile.save_profile(prof)
        assert [p.slug for p in fixprofile.list_profiles()] == ["good"]

    def test_roundtrip_through_disk_keeps_groups(self, home):
        prof, _ = fixprofile.parse_profile_text(json.dumps(JSON_OBJECT), slug="xx")
        fixprofile.save_profile(prof)
        again = fixprofile.list_profiles()[0]
        assert again.groups[10010][2] == (10011, 10012)
        assert again.data_pairs == {10020: 10021}
        assert again.msg_types


class TestReimport:
    """「同一家改版了就再导一次同名字典」——覆盖，而不是多出一份。"""

    def test_same_name_from_renamed_file_updates_in_place(self, home):
        old, _ = fixprofile.parse_profile_text(
            "# 合作方: XX 期货\ntag,中文名\n10001,旧含义\n", slug="xx-2026q3")
        slug, replaced = fixprofile.resolve_slug(old.name, old.slug)
        assert (slug, replaced) == ("xx-2026q3", None)
        old.slug = slug
        fixprofile.save_profile(old)

        # 对方发了新版文档，文件名也换了（2026Q3 → 2026Q4）
        new, _ = fixprofile.parse_profile_text(
            "# 合作方: xx期货\ntag,中文名\n10001,新含义\n10002,新增字段\n",
            slug="xx-2026q4")
        slug, replaced = fixprofile.resolve_slug(new.name, new.slug)
        assert slug == "xx-2026q3"            # 沿用旧 slug：同一家就覆盖
        assert replaced is not None and len(replaced.fields) == 1
        new.slug = slug
        fixprofile.save_profile(new)

        profiles = fixprofile.list_profiles()
        assert len(profiles) == 1             # 没有多出 -2 副本
        assert profiles[0].fields[10001][1] == "新含义"
        assert 10002 in profiles[0].fields    # 新字段进来了，旧内容被替换

    def test_same_filename_different_partner_gets_suffix(self, home):
        a, _ = fixprofile.parse_profile_text("tag,中文名\n10001,A 家字段\n",
                                             slug="dict")
        a.name = "A 券商"
        fixprofile.save_profile(a)
        b, _ = fixprofile.parse_profile_text("tag,中文名\n10001,B 家字段\n",
                                             slug="dict")
        b.name = "B 券商"
        slug, replaced = fixprofile.resolve_slug(b.name, b.slug)
        assert slug == "dict-2" and replaced is None

    def test_brand_new_profile_uses_slug(self, home):
        assert fixprofile.resolve_slug("新合作方", "newpartner") == (
            "newpartner", None)

    def test_updated_at_and_source_survive_roundtrip(self, home):
        prof, _ = fixprofile.parse_profile_text(
            "tag,中文名\n10001,本地订单号\n", slug="xx", source="/tmp/xx.csv")
        fixprofile.save_profile(prof)
        again = fixprofile.list_profiles()[0]
        assert again.updated_at               # 落盘时打的时间戳
        assert again.source.endswith("xx.csv")


if __name__ == "__main__":     # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
