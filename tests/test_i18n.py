"""国际化（i18n）冒烟测试。

锁定两条最关键的行为：
1. 中文是源语言——不装翻译器时显示的必须是源码原文（不能是空串、不能是英文）。
2. 装了英文 .qm 后，界面文案（菜单 / 规则面板 / 列头）必须变成英文。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from app.i18n import (
    DEFAULT_LANG,
    SUPPORTED,
    available_languages,
    load_language,
    normalize,
)


@pytest.fixture()
def qapp():
    """QApplication 实例（各测试文件自带，本项目没有全局 conftest 提供）。"""
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def _restore_language(qapp):
    """无论用例怎么切语言，结束后都还原成中文（避免污染后续用例）。"""
    yield
    load_language(qapp, DEFAULT_LANG)


class TestLanguageRegistry:
    def test_zh_and_en_registered(self):
        assert set(SUPPORTED) == {"zh_CN", "en"}
        assert available_languages()["zh_CN"] == "中文"
        assert available_languages()["en"] == "English"

    def test_normalize_falls_back_to_zh(self):
        assert normalize("en") == "en"
        assert normalize("zh_CN") == "zh_CN"
        # 手改 settings.json 写成不支持的值 → 回落中文，不能崩
        assert normalize("jp") == DEFAULT_LANG
        assert normalize("") == DEFAULT_LANG
        assert normalize(None) == DEFAULT_LANG
        assert normalize("EN") == DEFAULT_LANG


class TestSourceLanguageIsChinese:
    @pytest.mark.usefixtures("_restore_language")
    def test_no_translator_shows_original(self, qapp):
        """不装翻译器 → 显示源码原文（中文）。"""
        assert load_language(qapp, DEFAULT_LANG) == DEFAULT_LANG
        assert QCoreApplication.translate("MainWindow", "文件") == "文件"
        assert QCoreApplication.translate("RulesPanel", "新增") == "新增"


class TestEnglishOverlay:
    @pytest.mark.usefixtures("_restore_language")
    def test_menu_and_panel_translated(self, qapp):
        """装上英文 .qm → 菜单 / 规则面板文案变英文。"""
        assert load_language(qapp, "en") == "en"

        # 菜单栏
        assert QCoreApplication.translate("MainWindow", "文件") == "File"
        assert QCoreApplication.translate("MainWindow", "工具") == "Tools"
        assert QCoreApplication.translate("MainWindow", "语言") == "Language"
        # 规则面板
        assert QCoreApplication.translate("RulesPanel", "新增") == "New"
        assert QCoreApplication.translate("RulesPanel", "启用") == "Enable"
        # 带占位符的批量按钮文案
        assert QCoreApplication.translate("RulesPanel", "启用({0})") == "Enable ({0})"

    @pytest.mark.usefixtures("_restore_language")
    def test_untranslated_string_falls_back_to_source(self, qapp):
        """尚未包裹/未翻译的文案必须回落中文，不能显示空串。"""
        load_language(qapp, "en")
        assert QCoreApplication.translate("MainWindow", "这段文案没有英文译文") == (
            "这段文案没有英文译文"
        )

    @pytest.mark.usefixtures("_restore_language")
    def test_switch_back_to_chinese(self, qapp):
        """切回中文后必须恢复原文（不能残留英文）。"""
        load_language(qapp, "en")
        assert QCoreApplication.translate("MainWindow", "文件") == "File"
        load_language(qapp, "zh_CN")
        assert QCoreApplication.translate("MainWindow", "文件") == "文件"


class TestSettingsLanguagePersistence:
    def test_roundtrip_and_default(self):
        from app.settings import Settings

        s = Settings()
        assert s.language == DEFAULT_LANG

        s.language = "en"
        d = s.to_dict()
        assert d["language"] == "en"

        back = Settings.from_dict(d)
        assert back.language == "en"

    def test_unknown_value_falls_back(self):
        from app.settings import Settings

        back = Settings.from_dict({"language": "klingon"})
        assert back.language == DEFAULT_LANG


class TestTranslationCoverage:
    """覆盖度守卫：所有用户可见文案都必须包 tr()/translate() 且 .qm 有译文。

    做法：AST 扫 app/ 下全部 .py，找出「含中文且不在 tr/translate/NOOP 调用里、
    不在 docstring/注释、不在 logging 参数里」的字面量——这些就是漏网的展示文案。
    已知豁免（合理的不翻译项）放在 _EXEMPT 里，新增漏网会直接让本用例红。
    """

    #: (文件后缀, 行号) 或文件名的豁免清单——有意不翻译的：
    #: - dialogs.py 的 _CN 表：仅中文模式使用的按钮文案
    #: - flow_store COLUMNS / rule_editor MATCH_LABELS、METHOD_LABELS：
    #:   分别走 column_labels() 懒翻译 / 死代码
    #: - certserver.py：手机端证书下载网页（HTML，另有一套文案）
    #: - rules.py 默认规则名：会落盘的数据，不该随语言变
    #: - feedback.py issue 正文 / theme.py QSS：分别面向开发者、是代码
    _EXEMPT_FILES = {"app/ui/dialogs.py", "app/certserver.py", "app/ui/rule_editor.py"}
    _EXEMPT_LINES = {
        ("app/ui/flow_store.py", n) for n in range(10, 21)
    } | {
        ("app/rules.py", n) for n in (209, 219, 448, 463)
    } | {
        # feedback.py：GitHub issue 正文/诊断信息（面向开发者的纯文本）
        ("app/feedback.py", n) for n in (73, 74, 77, 93, 96)
    } | {
        # theme.py：QSS 样式表里的注释（代码，不是界面文案）
        ("app/ui/theme.py", 149)
    }

    @staticmethod
    def _scan():
        import ast
        import re
        from pathlib import Path

        cjk = re.compile(r"[\u4e00-\u9fff]")
        log_calls = ("debug", "info", "warning", "error", "exception", "critical")
        leftover = []
        for path in sorted(Path("app").rglob("*.py")):
            rel = str(path)
            if "i18n" in rel or rel in TestTranslationCoverage._EXEMPT_FILES:
                continue
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    child._parent = node
            docs = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                    d = node.body[0] if node.body else None
                    if (isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant)
                            and isinstance(d.value.value, str)):
                        for ln in range(d.lineno, (d.end_lineno or d.lineno) + 1):
                            docs.add(ln)

            def ancestors(t):
                out, cur = [], getattr(t, "_parent", None)
                while cur is not None:
                    out.append(cur)
                    cur = getattr(cur, "_parent", None)
                return out

            def wrapped(node):
                for a in ancestors(node):
                    if (isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute)
                            and a.func.attr in ("tr", "translate")):
                        return True
                    if (isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute)
                            and a.func.attr in log_calls):
                        return True
                    if (isinstance(a, ast.Call) and isinstance(a.func, ast.Name)
                            and a.func.id == "QT_TRANSLATE_NOOP"):
                        return True
                    if isinstance(a, ast.JoinedStr):
                        return True
                return False

            for node in ast.walk(tree):
                targets = []
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and cjk.search(node.value)):
                    targets.append(node)
                elif isinstance(node, ast.JoinedStr):
                    if any(isinstance(v, ast.Constant) and isinstance(v.value, str)
                           and cjk.search(v.value) for v in node.values):
                        targets.append(node)
                for t in targets:
                    if t.lineno in docs:
                        continue
                    if (rel, t.lineno) in TestTranslationCoverage._EXEMPT_LINES:
                        continue
                    if not wrapped(t):
                        leftover.append(f"{rel}:{t.lineno}")
        return leftover

    def test_no_unwrapped_chinese_literals(self):
        leftover = self._scan()
        assert not leftover, "未包裹 tr() 的中文文案：\n" + "\n".join(leftover)

    def test_qm_has_no_unfinished(self):
        """.ts 里不能有未完成条目（lrelease 会静默丢未完成翻译）。"""
        import re
        from pathlib import Path

        ts = Path("app/i18n/MiteProxy_en.ts")
        if not ts.exists():
            pytest.skip("无 .ts")
        s = ts.read_text(encoding="utf-8")
        unfinished = re.findall(r'<translation[^>]*type="unfinished"[^>]*>', s)
        assert not unfinished, f".ts 有 {len(unfinished)} 条未完成翻译"


class TestNoImportTimeTranslation:
    """求值时机守卫：translate()/tr() 绝不能在模块/类体（import 期）调用。

    背景：app/main.py 顶部 `from app.ui.main_window import MainWindow` 在
    main() 的 load_language() **之前**执行，整条导入链在翻译器装载前就跑完。
    模块级 translate() 永远拿到中文原文，.qm 里有译文也没用——v2.2.0 的
    bodyview 视图按钮（自动/原文/表单/图片/十六进制）、export 格式名、
    jsonutil 错误提示三处都栽在这。正确做法是 QT_TRANSLATE_NOOP 打标 +
    运行时（函数里）translate，由本用例强制。
    """

    @staticmethod
    def _scan():
        import ast
        from pathlib import Path

        bad = []
        for path in sorted(Path("app").rglob("*.py")):
            if "i18n" in str(path) or "__pycache__" in str(path):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            parent = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parent[child] = node
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                name = getattr(f, "attr", None) or getattr(f, "id", None)
                # QT_TRANSLATE_NOOP 是打标宏（返回原字符串），模块级调用正是正确姿势
                if name not in ("translate", "tr"):
                    continue
                lazy = False
                cur = node
                while cur in parent:
                    cur = parent[cur]
                    if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef,
                                        ast.Lambda)):
                        lazy = True
                        break
                if not lazy:
                    bad.append(f"{path}:{node.lineno}: {ast.unparse(node)[:80]}")
        return bad

    def test_no_module_level_translate_calls(self):
        bad = self._scan()
        assert not bad, (
            "import 期求值的 translate()（翻译器还没装，只会拿到中文）：\n"
            + "\n".join(bad)
        )


class TestLazyTablesTranslateAtRuntime:
    """三张曾经栽过的常量表：必须在运行时才翻译（TestNoImportTimeTranslation
    管住全类问题，这里逐字锁定具体行为，双保险）。"""

    @pytest.mark.usefixtures("_restore_language")
    def test_bodyview_mode_buttons_english(self, qapp):
        from app import bodyview

        load_language(qapp, "en")
        labels = dict(bodyview.view_mode_items())
        assert labels["auto"] == "Auto"
        assert labels["raw"] == "Raw"
        assert labels["form"] == "Form"
        assert labels["image"] == "Image"
        assert labels["hex"] == "Hex"
        assert bodyview.view_mode_label("hex") == "Hex"
        assert bodyview.view_mode_label("nope") == "Raw"   # 未知 → 原文

    @pytest.mark.usefixtures("_restore_language")
    def test_export_format_labels_english(self, qapp):
        from app import export

        load_language(qapp, "en")
        assert export.format_label("har") == "HAR archive (*.har)"
        filters, mapping = export.name_filters()
        assert "HAR archive (*.har)" in filters
        assert mapping["HAR archive (*.har)"] == "har"

    @pytest.mark.usefixtures("_restore_language")
    def test_jsonutil_hints_english(self, qapp):
        from app import jsonutil

        load_language(qapp, "en")
        hint = jsonutil.hint_for("Expecting ',' delimiter: line 1 column 2 (char 1)")
        assert hint and "comma" in hint.lower()

    @pytest.mark.usefixtures("_restore_language")
    def test_chinese_source_without_translator(self, qapp):
        """不装翻译器（中文源语言）→ 常量表展示中文原文。"""
        from app import bodyview, export, jsonutil

        load_language(qapp, "zh_CN")
        assert dict(bodyview.view_mode_items())["auto"] == "自动"
        assert export.format_label("har") == "HAR 归档 (*.har)"
        assert jsonutil.hint_for("Expecting ',' delimiter") == (
            "两个值之间少了逗号，或者多了个尾逗号"
        )
