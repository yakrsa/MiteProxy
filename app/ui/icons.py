"""内联 SVG 图标工厂（无外部资源依赖，跟随深浅主题色）。

设计要点：
- 所有图标都是 24x24 viewBox 的描边/填充路径，**不引入任何图片资源文件**，
  这样打包后无需处理 .qrc / 资源路径，也不会因缺图标文件而崩。
- SVG 里统一用 ``currentColor``，渲染前替换成当前主题的 ``fg`` 前景色，
  因此图标天然跟深浅主题走；主题切换时 ``invalidate()`` 清缓存后重新取色即可。
- 图标统一走 ``icon(name)``，用 ``functools.lru_cache`` 按 (name, color) 缓存，
  避免每个按钮都重渲染一遍 SVG。

用法：
    from app.ui import icons
    self.proxy_btn.setIcon(icons.icon("power"))
    # 切主题后：
    icons.invalidate(); self._refresh_icons()
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt

from app.ui import theme

#: 24x24 viewBox 的图标路径。``stroke`` 类用 currentColor 描边，
#: ``fill`` 类（如 pause 方块、breakpoint 内点）用 currentColor 填充。
_SVG: dict[str, str] = {
    # -- 侧栏导航（7 个 tab）--
    "traffic": ('<line x1="8" y1="6" x2="21" y2="6"/>'
                '<line x1="8" y1="12" x2="21" y2="12"/>'
                '<line x1="8" y1="18" x2="21" y2="18"/>'
                '<circle cx="3.5" cy="6" r="1.2"/>'
                '<circle cx="3.5" cy="12" r="1.2"/>'
                '<circle cx="3.5" cy="18" r="1.2"/>'),
    "mock": ('<polygon points="12 2 2 7 12 12 22 7 12 2"/>'
             '<polyline points="2 17 12 22 22 17"/>'
             '<polyline points="2 12 12 17 22 12"/>'),
    "network": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "tools": ('<path d="M14.7 6.3a4 4 0 0 0 5 5L11 20l-4-4 8.3-8.7z"/>'
              '<line x1="14.7" y1="6.3" x2="17.7" y2="9.3"/>'),
    "scripts": ('<polyline points="16 18 22 12 16 6"/>'
                '<polyline points="8 6 2 12 8 18"/>'),
    "log": ('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
            '<polyline points="16 2 16 8 22 8"/>'
            '<line x1="8" y1="13" x2="16" y2="13"/>'
            '<line x1="8" y1="17" x2="16" y2="17"/>'),
    "stats": ('<line x1="6" y1="20" x2="6" y2="16"/>'
              '<line x1="12" y1="20" x2="12" y2="10"/>'
              '<line x1="18" y1="20" x2="18" y2="4"/>'),
    # -- 工具栏高频动作 --
    "power": ('<path d="M12 3v9"/>'
              '<path d="M6.6 6.6a8 8 0 1 0 10.8 0"/>'),
    "breakpoint": ('<circle cx="12" cy="12" r="9"/>'
                   '<circle cx="12" cy="12" r="2.6" fill="currentColor" stroke="none"/>'),
    "search": ('<circle cx="11" cy="11" r="7"/>'
               '<line x1="21" y1="21" x2="16.65" y2="16.65"/>'),
    "trash": ('<polyline points="3 6 5 6 21 6"/>'
              '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>'
              '<line x1="10" y1="11" x2="10" y2="17"/>'
              '<line x1="14" y1="11" x2="14" y2="17"/>'),
    "mcp": ('<path d="M9 2v6"/><path d="M15 2v6"/>'
            '<path d="M7 8h10v3a5 5 0 0 1-10 0z"/>'
            '<path d="M12 16v6"/>'),
    # -- 命令面板 --
    "command": ('<path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/>'
                '<circle cx="9" cy="7" r="2" fill="currentColor" stroke="none"/>'
                '<circle cx="15" cy="17" r="2" fill="currentColor" stroke="none"/>'),
    # -- API 调试页 --
    "save": ('<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>'
             '<polyline points="17 21 17 13 7 13 7 21"/>'
             '<polyline points="7 3 7 8 15 8"/>'),
    "collection": ('<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>'),
}


def _wrap(inner: str) -> str:
    # 注意：fill / stroke 属性只能出现一次，重复属性会让 XML 解析直接失败
    # （QSvgRenderer.load 返回 False，渲染出全透明图标——之前踩过）
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
            f'viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" '
            f'fill="none" stroke-linecap="round" stroke-linejoin="round">{inner}</svg>')


@lru_cache(maxsize=256)
def _render(name: str, color: str, size: int) -> QPixmap:
    svg = _wrap(_SVG[name])
    svg = svg.replace("currentColor", color)
    renderer = QSvgRenderer()
    ok = renderer.load(bytearray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    if ok:
        painter = QPainter(pm)
        renderer.render(painter)
        painter.end()
    return pm


def icon(name: str, size: int = 18) -> QIcon:
    """取一个跟随当前主题前景色的图标。``name`` 必须是 ``_SVG`` 里的键。"""
    if name not in _SVG:
        return QIcon()
    color = theme.css("fg")
    if not color:
        color = "#374151"
    return QIcon(_render(name, color, size))


def invalidate() -> None:
    """主题切换后清缓存，下次 ``icon()`` 会用新颜色重渲染。"""
    _render.cache_clear()
