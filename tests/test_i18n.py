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
