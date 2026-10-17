"""国际化（i18n）加载器。

设计要点（与「渐进式 + 重启生效」方案对齐）：

- 源码里的文案本身就是**中文（源语言）**。因此 zh_CN 不需要任何 .qm 文件——
  不装翻译器时 Qt 直接显示源码里的原文，即中文。
- 只有「英文」需要一份 MiteProxy_en.qm 来覆盖原文。新增其它语言同理：
  放一份 MiteProxy_<lang>.qm 并在 SUPPORTED 登记即可。
- 采用标准 Qt i18n：界面文案统一用 ``self.tr("...")``（QObject 子类内）
  或 ``QCoreApplication.translate("Ctx", "...")``（模块级 / 非 QObject）。
  用 ``pyside6-lupdate`` 抽取、``pyside6-lrelease`` 编译。
- 切换语言**重启生效**：入口 app/main.py 在创建 MainWindow 之前就装好翻译器，
  所以下次启动时读取 settings.language 即可，无需运行时 retranslate。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTranslator

# 包内目录（开发态就是 app/i18n/）。
_I18N_DIR = Path(__file__).resolve().parent


def _candidate_dirs() -> list[Path]:
    """.qm 可能出现的目录（打包后 __file__ 在 PYZ 压缩包里不指向真实路径）。

    与 app/main.py 的 _app_icon() 同一套路：依次找包内目录、_MEIPASS、
    可执行文件同级及其 Resources / Frameworks（macOS bundle 的三种落点）。
    """
    dirs = [_I18N_DIR]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        dirs.append(Path(meipass) / "app" / "i18n")
    exe_dir = Path(sys.executable).resolve().parent  # …/Contents/MacOS
    dirs += [
        exe_dir / "app" / "i18n",
        exe_dir.parent / "Resources" / "app" / "i18n",
        exe_dir.parent / "Frameworks" / "app" / "i18n",
    ]
    return [d for d in dirs if d]

# 支持的语言：key 用于 settings.language 与 .qm 文件名，value 为下拉显示名。
SUPPORTED: dict[str, str] = {
    "zh_CN": "中文",
    "en": "English",
}

DEFAULT_LANG = "zh_CN"

# 当前进程已安装的翻译器（进程内只装一个，切换时先卸再装）。
_current: QTranslator | None = None
#: 实际生效的语言码。不能用 ``_current.language()`` 反推——.qm 里写的是
#: ``en_US`` 而 SUPPORTED 的 key 是 ``en``，normalize 会把 en_US 回落成中文。
_current_lang: str = DEFAULT_LANG


def available_languages() -> dict[str, str]:
    """返回 {code: 显示名}，供语言切换下拉框使用。"""
    return dict(SUPPORTED)


def is_supported(lang: str) -> bool:
    return lang in SUPPORTED


def normalize(lang: str | None) -> str:
    """把任意输入收敛到受支持的语言码；非法值回落默认中文。"""
    if lang and lang in SUPPORTED:
        return lang
    return DEFAULT_LANG


def load_language(app: QCoreApplication, lang: str) -> str:
    """把 ``lang`` 对应的翻译器装到 ``app`` 上，返回实际生效的语言码。

    zh_CN 是源语言，不装任何翻译器（显示原文即中文）。
    其它语言加载同名 .qm；若 .qm 缺失则回落源语言（中文）。
    """
    global _current, _current_lang

    # 先卸掉上一次装的，避免叠加
    if _current is not None:
        app.removeTranslator(_current)
        _current = None

    lang = normalize(lang)
    if lang == DEFAULT_LANG:
        _current_lang = DEFAULT_LANG
        return lang  # 源语言：无需 .qm

    qm = next(
        (d / f"MiteProxy_{lang}.qm" for d in _candidate_dirs()
         if (d / f"MiteProxy_{lang}.qm").exists()),
        None,
    )
    if qm is None:
        _current_lang = DEFAULT_LANG
        return DEFAULT_LANG  # 缺翻译文件，回落中文

    translator = QTranslator()
    if not translator.load(str(qm)):
        _current_lang = DEFAULT_LANG
        return DEFAULT_LANG
    app.installTranslator(translator)
    _current = translator
    _current_lang = lang
    return lang


def current_language() -> str:
    return _current_lang
