"""主题：深浅色语义色 token + 跟随系统 / 手动切换（v1.14）。

设计要点：
- **基础控件**（底色、文字、按钮）Qt 原生跟随系统深浅模式，这里不管；
- **语义色**（成功 / 错误 / 提示 / mock 命中底色……）原本散落各文件硬编码，
  浅色底配深字，深色模式下看不清——现在统一收拢到这里，每个 token 带
  浅色、深色两套值，按当前调色板明暗取用；
- **手动切换**走 `QStyleHints.setColorScheme`（Qt 6.8+，macOS/Windows 原生
  深浅色），不支持的平台回落 Fusion 调色板；默认 `system` 完全跟系统。

两种接入方式：
1. `dynamic(key)`：模块级 QColor 常量（如 mock 命中行底色）——返回的 QColor
   会在主题切换时**就地更新**，持有它的代码不用任何改动（模型 data() 每次重绘
   都会重新拿，天然生效）；
2. `add_listener(self._retheme)`：标签样式等静态着色——传**绑定方法**（用
   WeakMethod 持有，控件销毁自动清理），在 `_retheme` 里重设样式表；
   MainWindow 监听 `PaletteChange` 事件后调 `notify()` 统一广播。
"""

from __future__ import annotations

import weakref

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

#: 手动切换档位：跟随系统 / 强制浅色 / 强制深色
THEME_MODES = ("system", "light", "dark")

#: 语义色 token：(浅色值, 深色值)。深色列保证在深底上有足够对比度。
COLORS: dict[str, tuple[str, str]] = {
    "hint":        ("#6b6b6b", "#9ea7b3"),   # 次要说明文字
    "ok":          ("#1a7f37", "#3fb950"),   # 成功 / 2xx / 接收方
    "error":       ("#cf222e", "#f85149"),   # 错误 / 5xx
    "warn":        ("#bf8700", "#d29922"),   # 警告 / 4xx
    "info":        ("#0969da", "#4493f8"),   # 信息 / 3xx / 发送方
    "mock_row_bg": ("#fff4d6", "#4b3a10"),   # mock 命中行底色（琥珀）
    "mock_row_fg": ("#412402", "#ffd97a"),   # mock 命中行文字
    "hit_bg":      ("#fff3bf", "#5d5420"),   # 搜索命中底色（body / 表单表格）
    "invalid_bg":  ("#fff1f0", "#4d1414"),   # 无效配置行底色
    "invalid_fg":  ("#8a1f1f", "#ff9b95"),   # 无效配置行文字
    # -- 表格质感（对齐 Fiddler：斑马纹 + 扁平表头 + 细分隔线）
    "alt_row":     ("#f6f8fa", "#2d333b"),   # 交替行底色（斑马纹）
    "header_bg":   ("#eff2f5", "#2d333b"),   # 表头底色（扁平）
    "grid_line":   ("#e1e4e8", "#444c56"),   # 表格分隔线
    # -- 选中行：显式蓝底白字。不能用 palette(highlight)——macOS 原生样式
    #    下它与 palette(highlighted-text) 可能不同步（浅底配白字 → 选中行
    #    整行看不见的 bug），token 显式取色 + apply() 重建样式表才稳
    "sel_bg":      ("#0969da", "#4493f8"),   # 选中行底色
    "sel_fg":      ("#ffffff", "#ffffff"),   # 选中行文字
    # -- URL 关键字高亮行（顶部「高亮」框实时命中，v1.15）：青蓝底，
    #    与 mock 琥珀、搜索黄、选中蓝区分开
    "hl_row_bg":   ("#d9eef7", "#12384f"),   # 高亮行底色
}

#: 当前档位（apply() 后与 settings.theme 一致）
_mode = "system"

#: 就地更新的动态 QColor：[(QColor, token key), ...]
_dynamic: list[tuple[QColor, str]] = []

#: 主题切换监听者（WeakMethod：控件销毁自动失效）
_listeners: list[weakref.WeakMethod] = []


def _app_palette() -> QPalette | None:
    app = QGuiApplication.instance()
    return app.palette() if app is not None else None


def is_dark_app() -> bool:
    """当前应用调色板是否深色（以 Base 底色明暗判断）。"""
    palette = _app_palette()
    if palette is None:
        return False
    return palette.color(QPalette.ColorRole.Base).lightness() < 128


def _dark() -> bool:
    """token 取色用：手动指定了 light/dark 就听手动的，否则看调色板。"""
    if _mode == "light":
        return False
    if _mode == "dark":
        return True
    return is_dark_app()


def color(key: str) -> QColor:
    """取语义色当前变体。未知 key 回落 hint。"""
    light, dark = COLORS.get(key, COLORS["hint"])
    return QColor(dark if _dark() else light)


def css(key: str) -> str:
    """取语义色当前变体的 hex（拼样式表用）。"""
    return color(key).name()


def dynamic(key: str) -> QColor:
    """建一个随主题就地更新的 QColor 常量（模块级着色用）。

    返回值可直接当原来的 `QColor("#xxx")` 用；主题切换时值自动更新，
    所有引用无需改动。
    """
    light, _ = COLORS.get(key, COLORS["hint"])
    qc = QColor(light)
    _dynamic.append((qc, key))
    return qc


def add_listener(callback) -> None:
    """注册切换回调。**必须传绑定方法**（如 `self._retheme`）——
    用 WeakMethod 持有，控件销毁后自动失效，不阻止回收。"""
    _listeners.append(weakref.WeakMethod(callback))


def notify() -> None:
    """广播主题变化：先就地更新动态色，再逐个回调。"""
    for qc, key in _dynamic:
        light, dark = COLORS.get(key, COLORS["hint"])
        qc.setRgb(QColor(dark if _dark() else light).rgb())
    alive = []
    for ref in _listeners:
        cb = ref()
        if cb is None:
            continue           # 控件已销毁，顺手清理
        alive.append(ref)
        try:
            cb()
        except RuntimeError:
            pass               # C++ 对象已删，下轮清理
    _listeners[:] = alive


def stylesheet() -> str:
    """全局表格质感样式表：扁平表头、斑马纹、细网格、紧凑内边距。

    基色用 palette() 引用（跟随深浅模式实时变化），斑马纹/表头/网格线
    用本模块 token（切换主题时由 apply() 重新生成整份样式表）。
    """
    alt = css("alt_row")
    header = css("header_bg")
    grid = css("grid_line")
    sel_bg = css("sel_bg")
    sel_fg = css("sel_fg")
    return f"""
QTableView, QTableWidget {{
    background-color: palette(base);
    alternate-background-color: {alt};
    gridline-color: {grid};
    selection-background-color: {sel_bg};
    selection-color: {sel_fg};
    border: none;
}}
QTableView::item, QTableWidget::item {{
    padding: 1px 4px;
    border: none;
}}
QHeaderView::section {{
    background-color: {header};
    color: palette(window-text);
    padding: 2px 6px;
    border: none;
    border-right: 1px solid {grid};
    border-bottom: 1px solid {grid};
}}
QHeaderView::section:checked {{
    background-color: {header};
    font-weight: normal;
}}
QTableCornerButton::section {{
    background-color: {header};
    border: none;
}}
"""


def current_mode() -> str:
    return _mode


def apply(mode: str) -> None:
    """应用主题档位。`system` 恢复跟随系统；light/dark 强制切换。

    优先走 `QStyleHints.setColorScheme`（原生深浅色，保真度最高）；
    平台/Qt 版本不支持时回落 Fusion + 手工调色板。
    """
    global _mode
    if mode not in THEME_MODES:
        mode = "system"
    _mode = mode
    scheme = {
        "system": Qt.ColorScheme.Unknown,
        "light": Qt.ColorScheme.Light,
        "dark": Qt.ColorScheme.Dark,
    }[mode]
    try:
        QGuiApplication.styleHints().setColorScheme(scheme)
    except (AttributeError, RuntimeError):
        _apply_fusion_palette(mode)
    app = QGuiApplication.instance()
    if app is not None:
        app.setStyleSheet(stylesheet())
    notify()


def _apply_fusion_palette(mode: str) -> None:
    """Fusion 回落：setColorScheme 不可用时手工搭调色板。"""
    app = QGuiApplication.instance()
    if app is None:
        return
    if mode == "system":
        app.setStyle(app.property("_original_style") or "Fusion")
        app.setPalette(app.style().standardPalette())
        return
    app.setStyle("Fusion")
    palette = QPalette()
    if mode == "light":
        palette.setColor(QPalette.ColorRole.Window, QColor("#f3f3f3"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#1f2328"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#1f2328"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#f3f3f3"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1f2328"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#0969da"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#6b6b6b"))
    else:
        palette.setColor(QPalette.ColorRole.Window, QColor("#1c2128"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#e6edf3"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#22272e"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e6edf3"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#2d333b"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e6edf3"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#4493f8"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9ea7b3"))
    app.setPalette(palette)
