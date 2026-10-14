"""请求/响应详情面板（DESIGN.md 3.2）。

body 视图（3.2.5）：
- **自动 / 原文 / JSON / 表单 / 图片 / 十六进制**六种模式，默认「自动」按
  content-type 挑；用户手动切过就保持（对齐 Fiddler inspector 的粘性）。
- JSON = 缩进 2 空格 + 语法着色；表单 = key/value 表格（URL 已解码）；
  图片 = 预览（适应窗口 / 缩放）。
- **格式化失败一律回落原文并说明原因**，绝不吞掉 body。
- 搜索高亮（`Ctrl+F`）在结构化视图上照样生效：JSON/原文走 QTextDocument 查找，
  表单表格走单元格底色。

大内容的三道闸门（都是实测出来的，见 app/bodyview 注释）：
- 格式化用完整 body、只截断**渲染结果**（先截断再解析会让大 JSON 全部解析失败）；
- 渲染文本超过 `HIGHLIGHT_LIMIT` 就暂停语法着色；
- 单行超过 `WRAP_MAX_LINE_CHARS` 就临时关闭换行（超长单行换行是超线性开销）。

压缩内容：mitmproxy 的 `get_content()` 已按 content-encoding 解压，这里补上
「已解压 gzip：线上 x → y」提示，并在它解压失败时按魔数兜底再解一次。
"""

from __future__ import annotations

import re
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPalette,
    QPixmap,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:  # SVG 走矢量渲染；QtSvg 不可用时 SVG 会回落成文本提示
    from PySide6.QtSvg import QSvgRenderer
except ImportError:  # pragma: no cover
    QSvgRenderer = None

from app.bodyview import (
    VIEW_AUTO,
    VIEW_FORM,
    VIEW_HEX,
    VIEW_IMAGE,
    VIEW_JSON,
    VIEW_RAW,
    BODY_PREVIEW_LIMIT,
    HIGHLIGHT_LIMIT,
    WRAP_MAX_LINE_CHARS,
    content_encoding_of,
    decoded_note,
    detect_view_mode,
    format_json_body,
    hex_dump,
    is_image_content_type,
    parse_urlencoded,
    should_wrap,
    sniff_decompress,
    truncation_note,
    view_mode_items,
    view_mode_label,
)
from app.textutil import decode_body
from app.ui.highlight import JsonHighlighter, is_dark

_HIGHLIGHT_FORMAT = QTextCharFormat()
_HIGHLIGHT_FORMAT.setBackground(QColor("#fff3bf"))

#: 表单表格里命中的单元格底色（与 body 文本高亮同色系，视觉上是一回事）
_FORM_HIT_BG = QColor("#fff3bf")

#: WebSocket 消息表最多渲染的行数（再多的只记在内存里，别把表格撑爆）
WS_TABLE_LIMIT = 2000

BODY_VIEW_TIP = (
    "自动 = 按 content-type 挑最合适的视图（JSON / 表单 / 图片 / 原文 / 十六进制）。\n"
    "手动切换后会保持，换会话也不回弹。\n"
    "解析失败会退回原文并说明原因，不会丢内容。"
)

#: 图片缩放档位：适应窗口 + 固定比例
IMAGE_ZOOM_ITEMS = (
    ("fit", "适应窗口"),
    ("0.25", "25%"),
    ("0.5", "50%"),
    ("1", "100%"),
    ("2", "200%"),
)


def _image_format_label(content_type: str) -> str:
    """`image/jpeg` → `JPEG`（从 content-type 取，不碰 QImage.Format 枚举）。"""
    sub = (content_type or "").split(";")[0].strip().lower()
    sub = sub.split("/")[-1] if "/" in sub else sub
    return {
        "jpeg": "JPEG", "jpg": "JPEG", "png": "PNG", "gif": "GIF",
        "bmp": "BMP", "webp": "WEBP", "svg+xml": "SVG",
        "x-icon": "ICO", "vnd.microsoft.icon": "ICO",
    }.get(sub, sub.upper() or "图片")


class ImageView(QScrollArea):
    """图片预览：原始图存一份，按缩放档位渲染。

    SVG 走 QSvgRenderer 矢量渲染（可以按任意倍率清晰地缩放），
    没有 QtSvg 时明确报「无法渲染」，而不是显示一个空白框让人以为图是空的。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QImage()
        self._svg_data = b""
        self._is_svg = False
        self._svg_size = (300, 300)
        self._zoom = "fit"

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setBackgroundRole(QPalette.ColorRole.Base)
        self._label.setAutoFillBackground(True)
        self.setWidget(self._label)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # ------------------------------------------------------------ 数据

    def set_data(self, data: bytes, content_type: str) -> tuple[bool, str]:
        """载入图片；返回 `(是否成功, 描述)`。描述形如 `PNG · 800×600 · 12.3KB`。"""
        self._image = QImage()
        self._svg_data = b""
        self._is_svg = False
        ct = (content_type or "").split(";")[0].strip().lower()

        if ct == "image/svg+xml" or data[:5] in (b"<?xml", b"<svg "):
            if QSvgRenderer is None:
                return False, "SVG 渲染不可用（缺少 QtSvg）"
            renderer = QSvgRenderer(data)
            if not renderer.isValid():
                return False, "SVG 内容无法解析"
            size = renderer.defaultSize()
            self._is_svg = True
            self._svg_data = data
            # 没有 viewBox / 宽高的 SVG 会给不出尺寸，兜一个默认画布出来，
            # 否则用户看到的是「加载成功但一片空白」
            self._svg_size = (max(size.width(), 300), max(size.height(), 300))
            w, h = self._svg_size
            self._render()
            return True, f"SVG · {w}×{h} · {len(data) / 1024:.1f}KB"

        ok = self._image.loadFromData(data)
        if not ok:
            return False, "无法识别为图片（内容可能已损坏或非图片格式）"
        self._render()
        return True, (
            f"{_image_format_label(ct)} · {self._image.width()}×{self._image.height()}"
            f" · {len(data) / 1024:.1f}KB"
        )

    def clear(self) -> None:
        self._image = QImage()
        self._svg_data = b""
        self._is_svg = False
        self._label.setPixmap(QPixmap())

    # ------------------------------------------------------------ 缩放

    def set_zoom(self, key: str) -> None:
        self._zoom = key or "fit"
        self._render()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self._zoom == "fit":
            self._render()

    # ------------------------------------------------------------ 内部

    def _target_size(self):
        """按缩放档位算出目标尺寸（保持宽高比，不放大超出可视区的拟合）。"""
        if self._is_svg:
            w, h = self._svg_size
        elif not self._image.isNull():
            w, h = self._image.width(), self._image.height()
        else:
            return None
        if w <= 0 or h <= 0:
            return None
        if self._zoom == "fit":
            view = self.viewport().size()
            vw, vh = max(view.width() - 4, 16), max(view.height() - 4, 16)
            scale = min(vw / w, vh / h, 1.0)     # 只缩不放：小图别被拉糊
        else:
            try:
                scale = float(self._zoom)
            except (TypeError, ValueError):
                scale = 1.0
        return max(int(w * scale), 1), max(int(h * scale), 1)

    def _render(self) -> None:
        target = self._target_size()
        if target is None:
            self._label.setPixmap(QPixmap())
            return
        w, h = target
        if self._is_svg:
            if QSvgRenderer is None:
                return
            image = QImage(w, h, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            renderer = QSvgRenderer(self._svg_data)
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
        else:
            image = self._image.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._label.setPixmap(QPixmap.fromImage(image))
        self._label.resize(w, h)


class BodyPane(QWidget):
    """body 视图（模式切换 + 文本/表单/图片/十六进制 四种渲染）。

    请求、响应、WebSocket 消息共用这一个组件：三处对 body 的期待是一样的，
    拆出来就不用担心「WS 消息忘了支持 JSON 着色」这类偏差。
    """

    wrap_changed = Signal(bool)

    def __init__(self, parent=None, wrap_default: bool = True):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        row = QHBoxLayout()
        row.addWidget(QLabel("body 视图:"))
        self.mode_combo = QComboBox()
        for key, label in view_mode_items():
            self.mode_combo.addItem(label, key)
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.setToolTip(BODY_VIEW_TIP)
        row.addWidget(self.mode_combo)

        self.wrap_cb = QCheckBox("换行")
        self.wrap_cb.setChecked(wrap_default)
        self.wrap_cb.setToolTip(
            "超长行自动折行显示。单行超过 "
            f"{WRAP_MAX_LINE_CHARS // 1024}KB 时会自动临时关闭（换行会让界面卡顿）。"
        )
        row.addWidget(self.wrap_cb)

        self.zoom_combo = QComboBox()
        for key, label in IMAGE_ZOOM_ITEMS:
            self.zoom_combo.addItem(label, key)
        self.zoom_combo.setToolTip("图片缩放")
        self.zoom_combo.setVisible(False)
        row.addWidget(self.zoom_combo)

        self.view_note = QLabel("")
        self.view_note.setStyleSheet("color: #6b6b6b;")
        self.view_note.setToolTip(BODY_VIEW_TIP)
        row.addWidget(self.view_note, stretch=1)
        layout.addLayout(row)

        self.body_stack = QStackedWidget()

        self.body_view = QPlainTextEdit()
        self.body_view.setReadOnly(True)
        self.body_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("ui-monospace, SF Mono, Menlo, Consolas, monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.body_view.setFont(font)
        self._json_highlighter = JsonHighlighter(self.body_view.document())
        self.body_stack.addWidget(self.body_view)

        self.form_table = QTableWidget(0, 2)
        self.form_table.setHorizontalHeaderLabels(["名称", "值"])
        self.form_table.verticalHeader().setVisible(False)
        self.form_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.form_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        header = self.form_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.body_stack.addWidget(self.form_table)

        self.image_view = ImageView()
        self.body_stack.addWidget(self.image_view)

        layout.addWidget(self.body_stack, stretch=1)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.wrap_cb.toggled.connect(self._on_wrap_toggled)
        self.zoom_combo.currentIndexChanged.connect(self._on_zoom_changed)

        self._body_bytes: bytes | None = None
        self._content_type = ""
        self._encoding_note = ""
        self._base_note = ""            # 视图自身说明（不含换行提示）
        self._mode = VIEW_AUTO          # 手动切过就保持（粘性）
        self._resolved = VIEW_RAW       # 「自动」实际选中的视图

    # ------------------------------------------------------------ 展示

    def show_body(self, headers, body_bytes: bytes | None,
                  raw_len: int | None = None) -> None:
        """`raw_len` = 线上原始（压缩后）长度，用于「已解压」提示。"""
        self._content_type = self._content_type_of(headers)
        body, self._encoding_note = self._resolve_encoding(
            headers, body_bytes, raw_len
        )
        self._body_bytes = body
        self._render_body()

    def clear(self) -> None:
        self._body_bytes = None
        self._content_type = ""
        self._encoding_note = ""
        self._render_body()

    def set_wrap_default(self, on: bool) -> None:
        self.wrap_cb.setChecked(on)

    @property
    def current_mode(self) -> str:
        """当前实际生效的视图（`自动` 会解析成具体某一个）。"""
        return self._resolved

    @property
    def body_bytes(self) -> bytes | None:
        return self._body_bytes

    # ------------------------------------------------------------ 搜索高亮

    def highlight(self, term: str, case_sensitive: bool) -> int:
        """高亮 body 中所有命中，返回命中次数。"""
        current = self.body_stack.currentWidget()
        if current is self.form_table:
            return self._highlight_table(term, case_sensitive)
        if current is self.image_view:
            return 0                      # 图片没有文本可搜
        self.body_view.setExtraSelections([])
        if not term:
            return 0
        flags = QTextDocument.FindFlags()
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        selections = []
        count = 0
        doc = self.body_view.document()
        cursor = QTextCursor(doc)
        while True:
            cursor = doc.find(term, cursor, flags)
            if cursor.isNull():
                break
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = _HIGHLIGHT_FORMAT
            selections.append(sel)
            count += 1
            if count > 2000:  # 防失控
                break
        self.body_view.setExtraSelections(selections)
        return count

    def _highlight_table(self, term: str, case_sensitive: bool) -> int:
        """表单表格：命中的单元格铺底色（文本视图用 ExtraSelections，这里只能刷 item）。"""
        count = 0
        needle = term if case_sensitive else (term or "").lower()
        for r in range(self.form_table.rowCount()):
            for c in range(2):
                item = self.form_table.item(r, c)
                if item is None:
                    continue
                text = item.text()
                hay = text if case_sensitive else text.lower()
                hit = bool(needle) and needle in hay
                item.setBackground(_FORM_HIT_BG if hit else QBrush())
                if hit:
                    count += 1
        return count

    # ------------------------------------------------------------ 内部

    def _on_mode_changed(self) -> None:
        self._mode = self.mode_combo.currentData() or VIEW_AUTO
        self._render_body()

    def _on_wrap_toggled(self, on: bool) -> None:
        self._apply_wrap()
        self.wrap_changed.emit(on)

    def _set_note(self, text: str) -> None:
        """记下基础说明并渲染（换行提示由 `_apply_wrap` 追加，不重复叠加）。"""
        self._base_note = text
        self._paint_note()

    def _paint_note(self, extra: str = "") -> None:
        parts = [p for p in (self._base_note, extra) if p]
        self.view_note.setText(" · ".join(parts))

    def _on_zoom_changed(self) -> None:
        self.image_view.set_zoom(self.zoom_combo.currentData())

    @staticmethod
    def _content_type_of(headers) -> str:
        if headers is None:
            return ""
        try:
            return headers.get("content-type", "") or ""
        except Exception:
            return ""

    @staticmethod
    def _resolve_encoding(headers, body: bytes | None, raw_len: int | None):
        """压缩内容的兜底解压 + 提示文案。

        mitmproxy 的 `get_content()` 已经按 content-encoding 解压过了；只有当
        解压失败（返回长度 == 原始长度）时才轮到我们按魔数再试一次——比如服务端
        谎报编码、或 brotli/zstd 这类 mitmproxy 未必接得住的格式。
        """
        ce = content_encoding_of(headers)
        if not body or not ce:
            return body, ""
        raw_len = raw_len or 0
        if raw_len and len(body) == raw_len:     # 没变小 → mitmproxy 没解成功
            out, kind = sniff_decompress(body)
            if out is not None:
                return out, decoded_note(kind or ce, raw_len, len(out), "fallback")
            return body, f"已按 {ce} 压缩，但解压失败，显示的是原始压缩字节"
        return body, decoded_note(ce, raw_len, len(body), "mitmproxy")

    def _show_text(self, text: str, json_mode: bool = False) -> None:
        self.body_stack.setCurrentWidget(self.body_view)
        self.zoom_combo.setVisible(False)
        self.body_view.setPlainText(text)
        self._apply_wrap()
        # 大文本暂停着色：QSyntaxHighlighter 按 block 走，2 万行约 260ms
        colored = json_mode and len(text) <= HIGHLIGHT_LIMIT
        self._json_highlighter.set_enabled(colored, dark=is_dark(self.body_view))

    def _apply_wrap(self) -> None:
        """换行开关 → 真正应用（可能被超长单行闸门拦下）。"""
        if self.body_stack.currentWidget() is not self.body_view:
            return
        wrap, reason = should_wrap(self.body_view.toPlainText(), self.wrap_cb.isChecked())
        self.body_view.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if wrap else QPlainTextEdit.LineWrapMode.NoWrap
        )
        # reason 只在用户开着换行却被闸门拦下时出现——说明「不是不换，是换不起」
        self._paint_note(reason if self.wrap_cb.isChecked() else "")

    def _show_form(self, pairs: list[tuple[str, str]]) -> None:
        self.body_stack.setCurrentWidget(self.form_table)
        self.zoom_combo.setVisible(False)
        self.form_table.setRowCount(len(pairs))
        for i, (k, v) in enumerate(pairs):
            self.form_table.setItem(i, 0, QTableWidgetItem(str(k)))
            self.form_table.setItem(i, 1, QTableWidgetItem(str(v)))

    def _show_image(self, body: bytes) -> bool:
        ok, info = self.image_view.set_data(body, self._content_type)
        if not ok:
            return False
        self.body_stack.setCurrentWidget(self.image_view)
        self.zoom_combo.setVisible(True)
        parts = [info]
        if self._encoding_note:
            parts.append(self._encoding_note)
        self._set_note(" · ".join(parts))
        return True

    def _render_body(self) -> None:
        body = self._body_bytes
        if body is None:
            self._resolved = VIEW_RAW
            self._set_note(self._encoding_note)
            self._show_text("（无 body）")
            return
        if not body:
            self._resolved = VIEW_RAW
            self._set_note(self._encoding_note)
            self._show_text("（空 body）")
            return

        auto = self._mode == VIEW_AUTO
        mode = detect_view_mode(self._content_type, body) if auto else self._mode
        self._resolved = mode

        def note(detail: str = "") -> None:
            """提示文案：自动模式下带上「自动 → X」，原因与解压说明依次追加。"""
            label = view_mode_label(mode)
            prefix = f"自动 → {label}" if auto else label
            parts = [f"{prefix}：{detail}" if detail else prefix]
            if self._encoding_note:
                parts.append(self._encoding_note)
            self._set_note(" · ".join(parts))

        note()

        if mode == VIEW_HEX:
            self._show_text(hex_dump(body, total=len(body)))
            return

        if mode == VIEW_IMAGE:
            if self._show_image(body):
                return
            # 图片加载不了（损坏 / 不支持的格式）→ 老实回落十六进制，别留空白
            note("无法渲染为图片，已显示十六进制")
            self._show_text(hex_dump(body, total=len(body)))
            return

        if mode == VIEW_JSON:
            result = format_json_body(body, self._content_type)
            if result.ok:
                extra = "已截断显示" if result.truncated else ""
                note(extra)
                self._show_text(result.text, json_mode=True)
                return
            note(result.note)
            self._show_text(result.text)
            return

        text = decode_body(body[:BODY_PREVIEW_LIMIT], self._content_type)
        if text is None:
            # 要文本但解不出来 → 老实给十六进制，并说清楚为什么
            note("无法按文本解码，已显示十六进制")
            self._show_text(hex_dump(body, total=len(body)))
            return

        if mode == VIEW_FORM:
            pairs = parse_urlencoded(text.strip())
            if pairs:
                self._show_form(pairs)
                note(f"{len(pairs)} 个字段（已 URL 解码）")
                return
            note("无法解析为表单，已显示原文")
            self._show_text(self._with_truncation(text, len(body)))
            return

        # VIEW_RAW
        self._show_text(self._with_truncation(text, len(body)))

    @staticmethod
    def _with_truncation(text: str, total: int) -> str:
        return text + truncation_note(total) if total > BODY_PREVIEW_LIMIT else text


class MessagePane(QWidget):
    """单条消息（请求或响应）的 headers 表 + body 视图。"""

    def __init__(self, parent=None, wrap_default: bool = True):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.summary_label = QLabel("（未选择会话）")
        self.summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.summary_label)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.headers_table = QTableWidget(0, 2)
        self.headers_table.setHorizontalHeaderLabels(["Header", "Value"])
        self.headers_table.horizontalHeader().setStretchLastSection(True)
        self.headers_table.verticalHeader().setVisible(False)
        self.headers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        splitter.addWidget(self.headers_table)

        self.body_pane = BodyPane(wrap_default=wrap_default)
        splitter.addWidget(self.body_pane)

        splitter.setSizes([180, 320])
        layout.addWidget(splitter)

    # ------------------------------------------------------------ 展示

    def show_message(self, summary_line: str, headers, body_bytes: bytes | None,
                     raw_len: int | None = None) -> None:
        self.summary_label.setText(summary_line)
        self._fill_headers(headers)
        self.body_pane.show_body(headers, body_bytes, raw_len)

    def clear(self) -> None:
        self.summary_label.setText("（未选择会话）")
        self.headers_table.setRowCount(0)
        self.body_pane.clear()

    @property
    def body_pane_view(self) -> BodyPane:
        return self.body_pane

    # ------------------------------------------------------------ 搜索高亮

    def highlight(self, term: str, case_sensitive: bool) -> int:
        return self.body_pane.highlight(term, case_sensitive)

    # ------------------------------------------------------------ 内部

    def _fill_headers(self, headers) -> None:
        self.headers_table.setRowCount(0)
        if not headers:
            return
        try:
            items = list(headers.items(multi=True))
        except TypeError:
            items = list(headers.items())
        self.headers_table.setRowCount(len(items))
        for i, (k, v) in enumerate(items):
            self.headers_table.setItem(i, 0, QTableWidgetItem(str(k)))
            self.headers_table.setItem(i, 1, QTableWidgetItem(str(v)))


class WebSocketPane(QWidget):
    """WebSocket 消息列表 + 选中消息的 payload 视图（DESIGN 3.9）。

    mitmproxy 把 WebSocket 连接表示成带 `websocket` 属性的 HTTP flow，
    握手是 101 响应，之后每条消息走 `websocket_message` 钩子。
    """

    def __init__(self, parent=None, wrap_default: bool = True):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        self.info_label = QLabel("")
        self.info_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.info_label)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["#", "时间", "方向", "类型", "长度", "内容预览"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)

        self.body_pane = BodyPane(wrap_default=wrap_default)
        splitter.addWidget(self.body_pane)

        splitter.setSizes([260, 240])
        layout.addWidget(splitter)

        self._flow_id = ""
        self._messages: list = []
        self._shown = 0
        self._overflow = False

    # ------------------------------------------------------------ 展示

    def show_flow(self, flow) -> None:
        self._flow_id = getattr(flow, "id", "") or ""
        self.table.setRowCount(0)
        self._messages = []
        self._shown = 0
        self._overflow = False
        self.body_pane.clear()
        self.refresh(flow)

    def refresh(self, flow) -> bool:
        """把新到的消息追加进表；返回是否有变化。

        增量追加而不是整体重建：WebSocket 消息可能每秒几十条，重建会丢掉
        滚动位置与选中行。
        """
        ws = getattr(flow, "websocket", None)
        if ws is None:
            return False
        messages = list(getattr(ws, "messages", []) or [])
        if len(messages) == self._shown and self._flow_id == getattr(flow, "id", ""):
            self._update_info(flow)
            return False
        self._flow_id = getattr(flow, "id", "") or ""

        at_bottom = self._at_bottom()
        start = self._shown
        for i in range(start, len(messages)):
            if self.table.rowCount() >= WS_TABLE_LIMIT:
                self._overflow = True
                # 滚动窗口：丢最旧一行，最新消息始终可见——否则长连接
                # 跑过上限后用户看到的全是最早的旧消息，还被"最近"文案误导
                self.table.removeRow(0)
            # 序号用消息真实下标（i+1）：滚动删除头部后行数不再等于序号，
            # 用行数+1 会出现重复序号；i+1 始终是"第几条消息"
            self._append_row(i + 1, messages[i])
        self._shown = len(messages)
        self._messages = messages
        self._update_info(flow)
        if at_bottom and self.table.rowCount():
            self.table.scrollToBottom()
        return True

    def clear(self) -> None:
        self._flow_id = ""
        self._messages = []
        self._shown = 0
        self._overflow = False
        self.table.setRowCount(0)
        self.info_label.setText("")
        self.body_pane.clear()

    def highlight(self, term: str, case_sensitive: bool) -> int:
        return self.body_pane.highlight(term, case_sensitive)

    # ------------------------------------------------------------ 内部

    def _append_row(self, index: int, message) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        content = getattr(message, "content", b"") or b""
        is_text = bool(getattr(message, "is_text", False))
        kind = "文本" if is_text else "二进制"
        try:
            mtype = getattr(message, "type", None)
            kind = (getattr(mtype, "name", None) or kind).upper()
        except Exception:
            pass
        ts = getattr(message, "timestamp", 0) or 0
        values = [
            str(index),
            datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3] if ts else "-",
            "→ 发送" if getattr(message, "from_client", False) else "← 接收",
            kind,
            str(len(content)),
            _preview_text(content, is_text),
        ]
        for c, value in enumerate(values):
            item = QTableWidgetItem(value)
            if c == 2:
                color = QColor("#0969da") if getattr(message, "from_client", False) \
                    else QColor("#1a7f37")
                item.setForeground(color)
            self.table.setItem(row, c, item)

    def _update_info(self, flow) -> None:
        ws = getattr(flow, "websocket", None)
        req = getattr(flow, "request", None)
        url = _ws_display_url(
            getattr(req, "pretty_url", "") if req is not None else ""
        )
        total = len(getattr(ws, "messages", []) or [])
        sent = sum(
            1 for m in (getattr(ws, "messages", []) or [])
            if getattr(m, "from_client", False)
        )
        parts = [f"{url}", f"共 {total} 条消息（发送 {sent} / 接收 {total - sent}）"]
        if getattr(ws, "timestamp_end", None):
            parts.append(
                f"已关闭：code={getattr(ws, 'close_code', '')} "
                f"{getattr(ws, 'close_reason', '') or ''}".strip()
            )
        else:
            parts.append("连接中…")
        if self._overflow:
            parts.append(f"（表格仅显示最近 {WS_TABLE_LIMIT} 条）")
        self.info_label.setText("  |  ".join(parts))

    def _on_selection_changed(self) -> None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        if not (0 <= row < len(self._messages)):
            return
        message = self._messages[row]
        content = getattr(message, "content", b"") or b""
        self.body_pane.show_body(None, content)

    def _at_bottom(self) -> bool:
        bar = self.table.verticalScrollBar()
        return not bar.isVisible() or bar.value() >= bar.maximum() - 1


def _ws_display_url(url: str) -> str:
    """握手请求行是 `http://`（RFC 6455 规定），但给人看应该显示 `ws://`。"""
    if url.startswith("http://"):
        return "ws://" + url[len("http://"):]
    if url.startswith("https://"):
        return "wss://" + url[len("https://"):]
    return url


def _preview_text(content: bytes, is_text: bool, limit: int = 200) -> str:
    """表格里的消息预览：换行压成空格，超长截断。"""
    if not content:
        return "（空）"
    if is_text:
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = ""
    else:
        text = content[: limit * 2].hex(" ", 1)
    text = text.replace("\r", " ").replace("\n", " ")
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


class DetailPanel(QWidget):
    """请求 / 响应 / WebSocket 三个页签。

    WebSocket 页只在当前会话是 WS 时才可见——普通 HTTP 会话挂一个空页签
    只会让人以为功能坏了。
    """

    wrap_changed = Signal(bool)

    def __init__(self, parent=None, wrap_default: bool = True):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.wrap_default = wrap_default
        # 备注条：用户给会话写的 comment，置顶显示（空时隐藏，不占地方）
        self.comment_label = QLabel()
        self.comment_label.setWordWrap(True)
        self.comment_label.setVisible(False)
        self.comment_label.setStyleSheet(
            "padding: 4px 8px; background: rgba(127, 127, 127, 0.15);"
            " border-radius: 3px;"
        )
        layout.addWidget(self.comment_label)
        self.tabs = QTabWidget()
        self.request_pane = MessagePane(wrap_default=wrap_default)
        self.response_pane = MessagePane(wrap_default=wrap_default)
        self.ws_pane = WebSocketPane(wrap_default=wrap_default)
        self.tabs.addTab(self.request_pane, "请求")
        self.tabs.addTab(self.response_pane, "响应")
        self.ws_index = self.tabs.addTab(self.ws_pane, "WebSocket")
        self.tabs.setTabVisible(self.ws_index, False)
        layout.addWidget(self.tabs)

        for pane in (self.request_pane, self.response_pane):
            pane.body_pane.wrap_changed.connect(self.wrap_changed)
        self.ws_pane.body_pane.wrap_changed.connect(self.wrap_changed)

        self._flow = None

    def set_wrap_default(self, on: bool) -> None:
        self.wrap_default = on
        for pane in (self.request_pane, self.response_pane, self.ws_pane):
            pane.body_pane.set_wrap_default(on)

    def _show_comment(self, comment: str) -> None:
        self.comment_label.setVisible(bool(comment))
        if comment:
            self.comment_label.setText(f"💬 {comment}")

    def refresh_comment(self) -> None:
        """用户在列表里改备注时，若详情面板正看着这条就同步。"""
        self._show_comment(getattr(self._flow, "comment", "") or "")

    def show_flow(self, flow) -> None:
        self._flow = flow
        self._show_comment(getattr(flow, "comment", "") or "")
        req = getattr(flow, "request", None)
        res = getattr(flow, "response", None)

        if req is not None:
            self.request_pane.show_message(
                f"{req.method} {req.pretty_url}",
                req.headers,
                req.get_content(strict=False),
                len(req.raw_content or b""),
            )
        else:
            self.request_pane.clear()

        if res is not None:
            self.response_pane.show_message(
                f"HTTP {res.status_code} {res.reason or ''}".strip(),
                res.headers,
                res.get_content(strict=False),
                len(res.raw_content or b""),
            )
        else:
            self.response_pane.clear()

        ws = getattr(flow, "websocket", None)
        self.tabs.setTabVisible(self.ws_index, ws is not None)
        if ws is not None:
            self.ws_pane.show_flow(flow)
            if self.tabs.currentIndex() != self.ws_index and not res:
                self.tabs.setCurrentIndex(self.ws_index)
        else:
            self.ws_pane.clear()

    def update_flow(self, flow) -> bool:
        """同一条 flow 有新数据时增量刷新（WebSocket 消息到达）。

        返回是否真的刷新了——没刷新就不用重算搜索高亮。
        """
        if flow is None or self._flow is None:
            return False
        if getattr(flow, "id", None) != getattr(self._flow, "id", None):
            return False
        if getattr(flow, "websocket", None) is None:
            return False
        return self.ws_pane.refresh(flow)

    def clear(self) -> None:
        self._flow = None
        self._show_comment("")
        self.request_pane.clear()
        self.response_pane.clear()
        self.ws_pane.clear()
        self.tabs.setTabVisible(self.ws_index, False)

    def highlight(self, term: str, case_sensitive: bool) -> int:
        total = self.request_pane.highlight(term, case_sensitive)
        total += self.response_pane.highlight(term, case_sensitive)
        total += self.ws_pane.highlight(term, case_sensitive)
        return total
