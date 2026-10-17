"""工具页：编码转换 + JSON + JSON 比对 + API 调试四个子页。

合在一个标签页里是因为它们的使用场景是连着的——抓到一段 base64 先解码、
解出来是 JSON 再格式化、再用 JSONPath 抠出要看的字段、再把两段 JSON 比一比、
最后照着抓到的请求改一个自己发出去（API 调试）。分成多个顶层标签页就得
来回切，还容易忘了另一半功能在哪。
"""

from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from app.ui.api_panel import ApiPanel
from app.ui.codec_panel import CodecPanel
from app.ui.json_compare_panel import JsonComparePanel
from app.ui.json_panel import JsonPanel


class ToolPanel(QWidget):
    """内部四个子页：编码转换 / JSON / JSON 比对 / API 调试。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.codec_panel = CodecPanel()
        self.json_panel = JsonPanel()
        self.compare_panel = JsonComparePanel()
        self.api_panel = ApiPanel()
        self.tabs.addTab(self.codec_panel, self.tr("编码转换"))
        self.tabs.addTab(self.json_panel, "JSON")
        self.tabs.addTab(self.compare_panel, self.tr("JSON 比对"))
        self.tabs.addTab(self.api_panel, self.tr("API 调试"))
        layout.addWidget(self.tabs)

    # ------------------------------------------------------------ 对外

    @property
    def current_key(self) -> str:
        """当前子页名：codec / json / compare / api。"""
        current = self.tabs.currentWidget()
        if current is self.json_panel:
            return "json"
        if current is self.compare_panel:
            return "compare"
        if current is self.api_panel:
            return "api"
        return "codec"

    def show_page(self, key: str) -> None:
        page = {
            "json": self.json_panel,
            "compare": self.compare_panel,
            "api": self.api_panel,
        }.get(key, self.codec_panel)
        self.tabs.setCurrentWidget(page)

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
        elif target == "api":
            self.api_panel.set_body_text(text)
            self.api_panel.url_edit.setFocus()
        else:
            self.codec_panel.set_input(text)
            self.codec_panel.input_edit.setFocus()
