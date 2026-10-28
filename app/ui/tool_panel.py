"""工具页：编码转换 + JSON + JSON 比对 + API 调试 + FIX 解析五个子页。

合在一个标签页里是因为它们的使用场景是连着的——抓到一段 base64 先解码、
解出来是 JSON 再格式化、再用 JSONPath 抠出要看的字段、再把两段 JSON 比一比、
最后照着抓到的请求改一个自己发出去（API 调试）。分成多个顶层标签页就得
来回切，还容易忘了另一半功能在哪。FIX 解析同属「把一段文本看懂」的家族，
且报文常以 JSON/base64 封装传输（解码后正好粘过来），放同一页最顺。

五个子页都可**拖出成独立浮窗**：把 body 粘过去格式化、或一边改请求一边盯
主窗口的流量列表，是这一页最常见的用法。拖出后原位留占位页，`current_key`
与 `show_page` 都按业务键反查，索引不会错位。
"""

from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from app.ui.api_panel import ApiPanel
from app.ui.codec_panel import CodecPanel
from app.ui.detachable import TabDetacher
from app.ui.fix_panel import FixPanel
from app.ui.json_compare_panel import JsonComparePanel
from app.ui.json_panel import JsonPanel


class ToolPanel(QWidget):
    """内部五个子页：编码转换 / JSON / JSON 比对 / API 调试 / FIX 解析。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.codec_panel = CodecPanel()
        self.json_panel = JsonPanel()
        self.compare_panel = JsonComparePanel()
        self.api_panel = ApiPanel()
        self.fix_panel = FixPanel()
        self.tabs.addTab(self.codec_panel, self.tr("编码转换"))
        self.tabs.addTab(self.json_panel, "JSON")
        self.tabs.addTab(self.compare_panel, self.tr("JSON 比对"))
        self.tabs.addTab(self.api_panel, self.tr("API 调试"))
        self.tabs.addTab(self.fix_panel, "FIX")
        layout.addWidget(self.tabs)

        # 五个子页全部允许拖出（工具页里的东西都是「拿来对着看的」，不存在
        # 拖走就找不到的问题；与详情面板按页白名单收窄的做法不同）。
        self._detacher = TabDetacher(self.tabs, self, tag_of=self._key_of)
        self._detacher.enable_drag()

    # ------------------------------------------------------------ 拖出浮窗

    def _key_of(self, widget, index: int = -1):
        """页面 → 业务键（codec / json / compare / api / fix）。"""
        for key, pane in self._pages():
            if widget is pane:
                return key
        return None

    def _pages(self):
        return (
            ("codec", self.codec_panel),
            ("json", self.json_panel),
            ("compare", self.compare_panel),
            ("api", self.api_panel),
            ("fix", self.fix_panel),
        )

    def _pane_by_key(self, key: str):
        for name, pane in self._pages():
            if name == key:
                return pane
        return None

    @property
    def detacher(self) -> TabDetacher:
        return self._detacher

    def detach_page(self, key: str) -> bool:
        """把某个子页拖成独立浮窗；key 不存在返回 False。"""
        pane = self._pane_by_key(key)
        if pane is None:
            return False
        return self._detacher.detach(pane, tag=key) is not None

    def page_window(self, key: str):
        """取某子页的浮窗（没拖出则为 None）。"""
        return self._detacher.window_for_tag(key)

    def reattach_pages(self) -> None:
        """把所有被拖出的子页收回原位。"""
        self._detacher.reattach_all()

    def has_detached(self) -> bool:
        """是否有子页正被拖在浮窗外。"""
        return self._detacher.any_detached()

    def detached_keys(self) -> list:
        """当前被拖出去的子页业务键（codec / json / compare / api / fix）。"""
        return [k for k in self._detacher.detached_tags() if k]

    def close_floats(self) -> None:
        """退出路径：只关浮窗不收回（页面即将随主窗口销毁）。"""
        self._detacher.close_all(reattach=False)

    # ------------------------------------------------------------ 对外

    @property
    def current_key(self) -> str:
        """当前子页名：codec / json / compare / api / fix。

        拖出后原位站的是占位页，`currentWidget()` 拿到的不再是面板对象，
        所以统一按业务键反查（占位页也能还原成它代表的那个 key）。
        """
        tag = self._detacher.tag_at(self.tabs.currentIndex())
        return tag if isinstance(tag, str) else "codec"

    def show_page(self, key: str) -> None:
        """切到某子页；该页已被拖出就把它的浮窗提到前面。"""
        win = self._detacher.window_for_tag(key)
        if win is not None:
            win.show()
            win.raise_()
            win.activateWindow()
            return
        self.tabs.setCurrentWidget(self._pane_by_key(key) or self.codec_panel)

    def set_body_text(self, text: str, page: str | None = None) -> None:
        """把一段 body 送进来；不指定 page 就送到当前子页。"""
        target = page or self.current_key
        self.show_page(target)
        if target == "json":
            self.json_panel.set_text(text)
            self.json_panel.input_edit.setFocus()
        elif target == "compare":
            self.compare_panel.set_texts(text)
            self.compare_panel.left_edit.setFocus()
        elif target == "fix":
            self.fix_panel.set_text(text)
            self.fix_panel.input_edit.setFocus()
        elif target == "api":
            self.api_panel.set_body_text(text)
            self.api_panel.url_edit.setFocus()
        else:
            self.codec_panel.set_input(text)
            self.codec_panel.input_edit.setFocus()
