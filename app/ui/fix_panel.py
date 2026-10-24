"""FIX 工具页：粘贴 FIX 报文 → 树形四列（标签 / 字段 / 值 / 注释）。

布局与约定对齐 JsonPanel（工具页的兄弟姐妹）：
- 左输入右结果，中间竖分割线可拖；
- 状态区整段重画、不叠加（_set_status）；
- 输入改动 220ms 防抖后自动解析（识别为 FIX 才解析，不打扰）；
- 「复制可读原文」把 SOH 渲染成 `|`——SOH 是不可见控制符，直接复制
  出去大概率变成空串，`|` 是日志导出的事实标准。

解析全部委托 app/fix.py（纯逻辑，已单测）；本文件只做展示与文案。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QCoreApplication, QT_TRANSLATE_NOOP, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import fixprofile
from app.fix import FixField, FixGroup, human_time, is_fix_text, parse_fix
from app.ui import dialogs, theme

VIEW_TREE = "tree"
VIEW_RAW = "raw"

#: 值列展示上限（超长 RawData 之类）：单元格截断，完整值进 tooltip
VALUE_CELL_LIMIT = 300

#: 标签列：先给个保守宽度，填充后按实际 tag 自适应。5 位私有 tag（如
#: 16015）在 52px 里会被省略成 `1…`，看不出是哪个 tag——列宽必须让位给它，
#: 但也不该被异常长的内容撑爆，所以夹在 [MIN, MAX] 之间。
TAG_COLUMN_MIN = 52
TAG_COLUMN_MAX = 120

#: FIX 规范把 5000 起划给用户自定义字段；这类 tag 未收录时要说明是私有扩展，
#: 而不是笼统地说「字典没收录」（否则用户会以为解析漏了）
PRIVATE_TAG_FROM = 5000

#: 结果区同时展示的消息 tab 数上限：解析不设限（可读原文始终含全部），
#: 但 tab 建太多既无意义又拖慢首屏，超量部分在状态区提示
MAX_TAB_MESSAGES = 10

#: 错误码 → 提示文案。**NOOP 打标、运行时才 translate**（模块级 translate 会在
#: 翻译器装载前求值，英文模式下永久烤成中文——bodyview 踩过的坑）
ERROR_NOTES: tuple[tuple[str, str], ...] = (
    ("missing_begin_string", QT_TRANSLATE_NOOP(
        "FixPanel", "首字段不是 8=FIX（不是一条完整消息）")),
    ("missing_body_length", QT_TRANSLATE_NOOP("FixPanel", "缺少 BodyLength(9)")),
    ("missing_msg_type", QT_TRANSLATE_NOOP("FixPanel", "缺少 MsgType(35)")),
    ("missing_checksum", QT_TRANSLATE_NOOP("FixPanel", "缺少 CheckSum(10)")),
    ("body_length_mismatch", QT_TRANSLATE_NOOP(
        "FixPanel", "BodyLength 与实际字节数不符")),
    ("checksum_mismatch", QT_TRANSLATE_NOOP("FixPanel", "CheckSum 校验失败")),
    ("group_count_mismatch", QT_TRANSLATE_NOOP(
        "FixPanel", "重复组声明实例数与实际解析不符")),
    ("group_overflow", QT_TRANSLATE_NOOP(
        "FixPanel", "组实例数已达声明值，多出的字段已平铺展示")),
    ("bad_field", QT_TRANSLATE_NOOP("FixPanel", "存在 tag 不是数字的残字段")),
    ("trailing_garbage", QT_TRANSLATE_NOOP("FixPanel", "尾部有不成字段的内容")),
    ("too_many_fields", QT_TRANSLATE_NOOP(
        "FixPanel", "字段数超过上限，后续内容未解析")),
)

#: 时间型字段的类型标注（值合法时顺带给出人话格式）
TIME_TYPE_NOTES: tuple[tuple[str, str], ...] = (
    ("UTCTimestamp", QT_TRANSLATE_NOOP("FixPanel", "UTC 时间戳")),
    ("UTCDateOnly", QT_TRANSLATE_NOOP("FixPanel", "UTC 日期")),
    ("UTCTimeOnly", QT_TRANSLATE_NOOP("FixPanel", "UTC 时间")),
    ("LocalMktDate", QT_TRANSLATE_NOOP("FixPanel", "本地日期")),
)


def _error_note(code: str) -> str:
    for key, label in ERROR_NOTES:
        if key == code:
            return QCoreApplication.translate("FixPanel", label)
    return code


def _time_type_note(ftype: str) -> str:
    for key, label in TIME_TYPE_NOTES:
        if key == ftype:
            return QCoreApplication.translate("FixPanel", label)
    return ""


def _mono_font() -> QFont:
    font = QFont("ui-monospace, SF Mono, Menlo, Consolas, monospace")
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def _cell_text(value: str) -> str:
    """单元格展示值：控制符转义 + 截断（SOH 渲染成 `|`，见模块注释）。"""
    text = (value or "").replace("\x01", "|").replace("\n", "\\n").replace("\t", "\\t")
    if len(text) > VALUE_CELL_LIMIT:
        return text[:VALUE_CELL_LIMIT] + "…"
    return text


class FixPanel(QWidget):
    """工具页子页：FIX 报文解析。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = _mono_font()
        self._messages = []
        self._raw_text = ""
        #: (slug, Dictionary) 缓存：每次按键都读一遍字典文件太浪费
        self._dict_cache: tuple[str, object] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addLayout(self._build_toolbar())
        self._refresh_dicts()
        root.addWidget(self._build_splitter(), stretch=1)
        root.addLayout(self._build_status())

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self._auto_parse)
        self.input_edit.textChanged.connect(self._schedule)

    # ------------------------------------------------------------ 构建

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        self.parse_btn = QPushButton(self.tr("解析"))
        self.parse_btn.setToolTip(self.tr("立即解析输入内容（识别不出 FIX 时也会给出原因）"))
        self.parse_btn.clicked.connect(self._parse)
        row.addWidget(self.parse_btn)

        row.addSpacing(10)
        row.addWidget(QLabel(self.tr("视图:")))
        self.view_combo = QComboBox()
        self.view_combo.addItem(self.tr("字段树"), VIEW_TREE)
        self.view_combo.addItem(self.tr("可读原文"), VIEW_RAW)
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        row.addWidget(self.view_combo)

        # 字典：内置通用字段 / 某个合作方的私有字段（app/fixprofile）
        row.addSpacing(10)
        row.addWidget(QLabel(self.tr("字典:")))
        self.dict_combo = QComboBox()
        self.dict_combo.currentIndexChanged.connect(self._on_dict_changed)
        row.addWidget(self.dict_combo)

        self.dict_menu_btn = QToolButton()
        self.dict_menu_btn.setText("⋯")
        self.dict_menu_btn.setToolTip(self.tr("导入 / 删除合作方 FIX 字典"))
        self.dict_menu_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.dict_menu_btn)
        menu.addAction(self.tr("导入字典文件…"), self._import_dict)
        menu.addAction(self.tr("打开字典文件夹"), self._open_dict_folder)
        menu.addAction(self.tr("删除当前字典"), self._remove_dict)
        menu.addSeparator()
        menu.addAction(self.tr("复制 JSON 模板"),
                       lambda: self._copy_template("json"))
        menu.addAction(self.tr("复制 CSV 模板"),
                       lambda: self._copy_template("csv"))
        self.dict_menu_btn.setMenu(menu)
        row.addWidget(self.dict_menu_btn)

        self.copy_btn = QPushButton(self.tr("复制可读原文"))
        self.copy_btn.setToolTip(
            self.tr("按 | 分隔的报文文本复制到剪贴板（SOH 是不可见控制符，直接复制会丢）")
        )
        self.copy_btn.clicked.connect(self._copy_readable)
        row.addWidget(self.copy_btn)

        row.addStretch(1)

        self.clear_btn = QPushButton(self.tr("清空"))
        self.clear_btn.clicked.connect(self._on_clear)
        row.addWidget(self.clear_btn)
        return row

    def _build_splitter(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        in_box = QGroupBox(self.tr("输入"))
        in_layout = QVBoxLayout(in_box)
        self.input_edit = QPlainTextEdit()
        self.input_edit.setFont(self._font)
        self.input_edit.setPlaceholderText(self.tr(
            "粘贴 FIX 报文，如：\n"
            "8=FIX.4.4|9=65|35=D|49=SENDER|56=TARGET|34=1|52=20261023-14:30:00.000|"
            "11=ORDER-1|55=000001|54=1|38=100|40=2|44=10.5|59=0|10=160|\n"
            "分隔符用 | 或 SOH 均可；一次粘贴多条消息会分别解析"
        ))
        in_layout.addWidget(self.input_edit)
        in_bar = QHBoxLayout()
        in_bar.addStretch(1)
        self.input_count = QLabel("")
        self.input_count.setStyleSheet(f"color: {theme.css('hint')};")
        in_bar.addWidget(self.input_count)
        in_layout.addLayout(in_bar)

        out_box = QGroupBox(self.tr("结果"))
        out_layout = QVBoxLayout(out_box)
        self.out_stack = QStackedWidget()

        # 多条消息时每条一个 tab（#N 35=X 标题 + ✗ 徽标），tab 内是摘要行 +
        # 一棵字段树；单条消息隐藏 tab 栏，体验与单树一致
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.jump_bad_btn = QPushButton()
        self.jump_bad_btn.setToolTip(self.tr("跳到第一个有校验问题的消息"))
        self.jump_bad_btn.setVisible(False)
        self.jump_bad_btn.clicked.connect(self._jump_to_first_bad)
        self.tab_widget.setCornerWidget(
            self.jump_bad_btn, Qt.Corner.TopRightCorner)
        self.out_stack.addWidget(self.tab_widget)

        self.raw_view = QPlainTextEdit()
        self.raw_view.setReadOnly(True)
        self.raw_view.setFont(self._font)
        self.raw_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.out_stack.addWidget(self.raw_view)

        out_layout.addWidget(self.out_stack)
        splitter.addWidget(in_box)
        splitter.addWidget(out_box)
        splitter.setSizes([520, 520])
        return splitter

    def _build_status(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.status_label.setStyleSheet(f"color: {theme.css('hint')};")
        row.addWidget(self.status_label, stretch=1)
        self._status_kind = "hint"
        theme.add_listener(self._retheme)
        return row

    # ------------------------------------------------------------ 对外

    def set_text(self, text: str) -> None:
        """外部灌入内容（右键「在 FIX 工具里打开 body」/ 发送到工具页）。"""
        self.input_edit.setPlainText(text)
        self._parse()

    # ------------------------------------------------------------ 字典（合作方私有字段）

    def _dictionary(self):
        """当前生效的字典（内置 ⊕ 选中的合作方字典），按 slug 缓存。"""
        slug = self.dict_combo.currentData() or ""
        if self._dict_cache is not None and self._dict_cache[0] == slug:
            return self._dict_cache[1]
        if not slug:
            dictionary = fixprofile.BUILTIN
        else:
            path = fixprofile.profile_dir() / "{0}.json".format(slug)
            prof = fixprofile.load_profile(path) if path.exists() else None
            dictionary = fixprofile.merge(prof)
        self._dict_cache = (slug, dictionary)
        return dictionary

    def _refresh_dicts(self) -> None:
        """重填字典下拉：内置 + 已导入的合作方字典（尽量保持当前选择）。"""
        want = (self.dict_combo.currentData()
                if self.dict_combo.count() else fixprofile.get_active_slug())
        self.dict_combo.blockSignals(True)
        self.dict_combo.clear()
        self.dict_combo.addItem(self.tr("内置（通用字段）"), "")
        for prof in fixprofile.list_profiles():
            self.dict_combo.addItem(prof.label(), prof.slug)
            idx = self.dict_combo.count() - 1
            # tooltip 里带上来源文件与更新时间：改版后重新导入过没有，一眼能认
            bits = [self.tr("{0} 个字段").format(len(prof.fields)), prof.slug]
            if prof.source:
                bits.append(Path(prof.source).name)
            if prof.updated_at:
                bits.append(prof.updated_at.replace("T", " ")[:16])
            self.dict_combo.setItemData(
                idx, " · ".join(bits), Qt.ItemDataRole.ToolTipRole)
        pos = self.dict_combo.findData(want) if want else 0
        self.dict_combo.setCurrentIndex(pos if pos >= 0 else 0)
        self.dict_combo.blockSignals(False)
        self._update_dict_tip()

    def _update_dict_tip(self) -> None:
        slug = self.dict_combo.currentData() or ""
        if slug:
            self.dict_combo.setToolTip(self.tr(
                "当前用「{0}」字典解析：内置字段照常可用，同名 tag 以该字典为准").format(
                    self.dict_combo.currentText()))
        else:
            self.dict_combo.setToolTip(self.tr(
                "内置字典只含通用字段；导入合作方字典后，对方的私有 tag 才有名字与枚举释义"))

    def _on_dict_changed(self, _index: int) -> None:
        slug = self.dict_combo.currentData() or ""
        fixprofile.set_active_slug(slug)
        self._dict_cache = None
        self._update_dict_tip()
        if self.input_edit.toPlainText().strip():
            self._parse()

    def _import_dict(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, self.tr("导入合作方 FIX 字典"), "",
            self.tr("FIX 字典 (*.json *.csv *.tsv *.txt);;所有文件 (*)"))
        if path:
            self.import_profile(path)

    def import_profile(self, path: str) -> bool:
        """导入一份字典文件（JSON / CSV / TSV），成功后自动切到它。

        解析问题不阻断导入（对方文档常有空行 / 合并单元格），只把问题条数
        写在状态区，用户自己决定要不要回去改文件。

        **同名即更新**：同一家合作方改版后直接把新文件再导一次就行——按名称
        认人（不看文件名），旧字典被就地覆盖，不会多出 `-2` 副本。
        """
        try:
            text = fixprofile.read_profile_file(path)
        except OSError as exc:
            self._set_status(self.tr("读取字典失败：{0}").format(exc), "error")
            return False
        stem = Path(path).stem
        prof, warnings = fixprofile.parse_profile_text(
            text, slug=fixprofile.slugify(stem) or "profile", source=path)
        if prof is None:
            # 具体原因（哪一行、JSON 哪儿错）只进 tooltip：这些是数据层诊断，
            # 不随界面语言翻译，别让它变成中英混排的状态区文案
            reason = warnings[0] if warnings else self.tr("格式无法识别")
            self._set_status(
                self.tr("导入失败：无法识别字典格式（支持 JSON / CSV / TSV）"),
                "error")
            self.status_label.setToolTip(reason)
            return False
        if not prof.name or prof.name == prof.slug:
            prof.name = stem
        prof.slug, replaced = fixprofile.resolve_slug(prof.name, prof.slug)
        fixprofile.save_profile(prof)
        self._dict_cache = None
        self._refresh_dicts()
        idx = self.dict_combo.findData(prof.slug)
        if idx >= 0:
            self.dict_combo.setCurrentIndex(idx)   # 触发落盘 + 重新解析
        note = (self.tr("，{0} 行无法识别已跳过").format(len(warnings))
                if warnings else "")
        if replaced is None:
            self._set_status(self.tr("已导入字典「{0}」：{1} 个字段{2}").format(
                prof.name, len(prof.fields), note), "ok")
        else:
            self._set_status(self.tr(
                "已更新字典「{0}」：{1} 个字段（原 {2} 个）{3}").format(
                    prof.name, len(prof.fields), len(replaced.fields), note), "ok")
        return True

    def remove_current_profile(self) -> bool:
        """删除当前选中的合作方字典并回落到内置（UI 里先确认再调）。"""
        slug = self.dict_combo.currentData() or ""
        if not slug:
            return False
        ok = fixprofile.delete_profile(slug)
        self._dict_cache = None
        self._refresh_dicts()
        if self.input_edit.toPlainText().strip():
            self._parse()
        self._set_status(
            self.tr("已删除字典「{0}」，回到内置字典").format(slug) if ok
            else self.tr("删除失败：{0}").format(slug),
            "ok" if ok else "error")
        return ok

    def _remove_dict(self) -> None:
        slug = self.dict_combo.currentData() or ""
        if not slug:
            self._set_status(self.tr("当前用的是内置字典，没有可删除的字典"), "hint")
            return
        answer = dialogs.question(
            self, self.tr("删除字典"),
            self.tr("删除字典「{0}」？字典文件会从磁盘上移除。").format(
                self.dict_combo.currentText()))
        if answer == QMessageBox.StandardButton.Yes:
            self.remove_current_profile()

    def _open_dict_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(fixprofile.profile_dir())))

    def _copy_template(self, kind: str) -> None:
        text = fixprofile.TEMPLATE_JSON if kind == "json" else fixprofile.TEMPLATE_CSV
        QApplication.clipboard().setText(text)
        self._set_status(self.tr(
            "模板已复制到剪贴板：按对方文档填好字段，另存为 .json / .csv 后用「导入字典文件…」导入"),
            "ok")

    # ------------------------------------------------------------ 解析

    def _schedule(self) -> None:
        self._update_counts()
        text = self.input_edit.toPlainText()
        if not text.strip():
            self._clear_result()
            self._set_status("", "hint")
            return
        if is_fix_text(text):
            self._timer.start()
        else:
            self._timer.stop()
            self._clear_result()
            self._set_status(self.tr("未识别为 FIX 报文（需以 8=FIX 开头，且含 8/9/35 字段）"), "hint")

    def _auto_parse(self) -> None:
        self._parse()

    def _parse(self) -> None:
        self._timer.stop()
        text = self.input_edit.toPlainText()
        self._update_counts()
        if not text.strip():
            self._clear_result()
            self._set_status("", "hint")
            return
        messages = parse_fix(text, self._dictionary())
        self._messages = messages
        if not messages:
            self._clear_result()
            self._set_status(self.tr("未解析出任何字段——请检查输入是否以 8=FIX 开头"), "error")
            return
        self._render_tabs()
        self._render_raw()
        self._set_status(self._summary_text(messages), self._status_kind_of(messages))
        # tab 栏右侧的「✗ N」跳转按钮（仅多条且存在问题时出现）
        bad = [i for i, m in enumerate(messages[:MAX_TAB_MESSAGES]) if m.errors]
        self.jump_bad_btn.setText(self.tr("✗ {0}").format(len(bad)))
        self.jump_bad_btn.setVisible(len(messages) > 1 and bool(bad))

    def _clear_result(self) -> None:
        self._messages = []
        self.tab_widget.clear()
        self.raw_view.clear()
        self.jump_bad_btn.setVisible(False)

    def _status_kind_of(self, messages) -> str:
        return "error" if any(m.errors for m in messages) else "ok"

    def _summary_text(self, messages) -> str:
        # 单条消息：完整摘要（与 tab 内摘要行一致）
        if len(messages) == 1:
            return self._message_summary(messages[0])
        # 多条消息：总览式——不再逐条复读（20 条时旧版状态区 2300+ 字符）
        parts = [self.tr("共 {0} 条消息").format(len(messages))]
        if len(messages) > MAX_TAB_MESSAGES:
            parts.append(self.tr("显示前 {0} 条").format(MAX_TAB_MESSAGES))
        bad = [i + 1 for i, m in enumerate(messages) if m.errors]
        if bad:
            listed = ", ".join("#{0}".format(n) for n in bad[:10])
            more = self.tr(" 等 {0} 条").format(len(bad)) if len(bad) > 10 else ""
            parts.append(self.tr("{0} 条有问题（{1}{2}）").format(
                len(bad), listed, more))
        notes = []
        for m in messages:
            for code in m.errors:
                note = _error_note(code)
                if note not in notes:
                    notes.append(note)
        if notes:
            parts.append(self.tr("问题：{0}").format("；".join(notes)))
        if any(m.truncated for m in messages):
            parts.append(self.tr("内容超限已截断"))
        return " ┃ ".join(parts)

    # ------------------------------------------------------------ 树

    def _make_tree(self) -> QTreeWidget:
        """建一棵字段树（每个消息 tab 一棵；列头 / 列宽 / 样式保持一致）。"""
        tree = QTreeWidget()
        tree.setColumnCount(4)
        tree.setHeaderLabels([
            self.tr("标签"), self.tr("字段"), self.tr("值"), self.tr("注释"),
        ])
        tree.setAlternatingRowColors(True)
        tree.setRootIsDecorated(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, TAG_COLUMN_MIN)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        tree.setColumnWidth(2, 180)
        return tree

    def _fit_tag_column(self, tree: QTreeWidget) -> None:
        """标签列按实际 tag 宽度重排（Fixed 模式下 resizeColumnToContents 同样生效）。

        私有 tag 常是 4–5 位（`16015`），固定 52px 减去树缩进只剩 ~28px，
        会被省略成 `1…`——tag 号看不全等于没法对字段。这里按内容撑开，
        再夹到 [TAG_COLUMN_MIN, TAG_COLUMN_MAX]，避免异常内容把列撑飞。
        """
        tree.resizeColumnToContents(0)
        width = max(TAG_COLUMN_MIN, min(tree.columnWidth(0), TAG_COLUMN_MAX))
        tree.setColumnWidth(0, width)

    def _message_summary(self, m) -> str:
        """单条消息的摘要行（tab 顶部 / 单条时的状态区共用）。"""
        seg = []
        if m.begin_string:
            seg.append(m.begin_string)
        if m.msg_type:
            seg.append("35={0} {1}".format(m.msg_type, m.msg_type_note)
                       if m.msg_type_note else "35={0}".format(m.msg_type))
        if m.seq_num:
            seg.append(self.tr("SeqNum {0}").format(m.seq_num))
        if m.sender and m.target:
            seg.append("{0} → {1}".format(m.sender, m.target))
        seg.append(self.tr("{0} 个字段").format(m.field_count))
        if m.body_length_ok is True:
            seg.append(self.tr("BodyLength ✓"))
        elif m.body_length_ok is False:
            seg.append(self.tr("BodyLength ✗（声明 {0} / 实际 {1}）").format(
                m.declared_body_length, m.actual_body_length))
        if m.checksum_skipped:
            seg.append(self.tr("CheckSum 未校验（| 分隔输入）"))
        elif m.checksum_ok is True:
            seg.append(self.tr("CheckSum ✓"))
        elif m.checksum_ok is False:
            seg.append(self.tr("CheckSum ✗（声明 {0} / 实际 {1}）").format(
                m.declared_checksum, m.actual_checksum))
        return " · ".join(seg)

    def _render_tabs(self) -> None:
        self.tab_widget.clear()
        shown = self._messages[:MAX_TAB_MESSAGES]
        for i, m in enumerate(shown):
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            summary = QLabel(self._message_summary(m))
            summary.setWordWrap(True)
            summary.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            summary.setStyleSheet("color: {0};".format(
                theme.css("error" if m.errors else "hint")))
            layout.addWidget(summary)
            tree = self._make_tree()
            self._fill_items(tree.invisibleRootItem(), m.items)
            tree.expandToDepth(1)
            self._fit_tag_column(tree)
            layout.addWidget(tree)
            title = "#{0} 35={1}".format(i + 1, m.msg_type or "?")
            if m.errors:
                title += " ✗"
            idx = self.tab_widget.addTab(page, title)
            if m.errors:
                self.tab_widget.tabBar().setTabTextColor(
                    idx, theme.dynamic("error"))
        # 单条消息没有 tab 导航需求，隐藏 tab 栏（内容与单树体验一致）
        self.tab_widget.tabBar().setVisible(len(shown) > 1)

    def _jump_to_first_bad(self) -> None:
        shown = self._messages[:MAX_TAB_MESSAGES]
        for i, m in enumerate(shown):
            if m.errors:
                self.tab_widget.setCurrentIndex(i)
                return

    def _fill_items(self, parent: QTreeWidgetItem, items) -> None:
        for item in items:
            if isinstance(item, FixGroup):
                group_comment = self.tr("重复组 · 解析出 {0} 个实例").format(
                    len(item.instances))
                node = QTreeWidgetItem(parent, [
                    str(item.tag),
                    "{0} {1}".format(item.name_cn, item.name_en),
                    self.tr("{0} 个实例").format(item.count),
                    group_comment,
                ])
                node.setToolTip(0, self.tr("tag {0}").format(item.tag))
                node.setToolTip(3, group_comment)
                for inst in item.instances:
                    child = QTreeWidgetItem(node, [
                        "",
                        self.tr("实例 {0}").format(inst.index),
                        self.tr("{0} 个字段").format(len(inst.fields)),
                        "",
                    ])
                    self._fill_items(child, inst.fields)
            else:
                self._append_field(parent, item)

    def _append_field(self, parent: QTreeWidgetItem, f: FixField) -> None:
        if f.known:
            name = "{0} {1}".format(f.name_cn, f.name_en).strip()
            comment = f.enum_note
            if not comment:
                if f.ftype == "NumInGroup":
                    comment = self.tr("重复组引导字段（该组未收录，后续字段平铺）")
                elif f.ftype in ("UTCTimestamp", "UTCDateOnly",
                                 "UTCTimeOnly", "LocalMktDate"):
                    human = human_time(f.value)
                    if human:
                        comment = "{0}：{1}".format(_time_type_note(f.ftype), human)
                elif f.tag == 9:
                    comment = self.tr("消息体字节数（10 字段之前的长度）")
                elif f.tag == 10:
                    comment = self.tr("前三段字节累加 mod 256")
        else:
            name = self.tr("未收录字段")
            # 5000 起是 FIX 留给用户自定义的区间：这类 tag 本来就查不到名，
            # 说明成「私有扩展」比「字典没收录」更准确，也不会让人以为解析漏了
            if f.tag >= PRIVATE_TAG_FROM:
                comment = self.tr(
                    "私有扩展 tag（FIX 规范 5000 起为用户自定义），字典未收录")
            else:
                comment = self.tr("字典未收录该 tag")
        row = QTreeWidgetItem(parent, [
            str(f.tag), name, _cell_text(f.value), comment,
        ])
        # 列宽有限，长字段名 / 长值 / 长注释都会被省略——悬停给出完整内容
        row.setToolTip(0, self.tr("tag {0}").format(f.tag))
        row.setToolTip(1, name)
        row.setToolTip(2, f.value.replace("\x01", "|"))
        row.setToolTip(3, comment)

    # ------------------------------------------------------------ 可读原文

    def _readable_text(self) -> str:
        """把解析出的消息重新渲染成 | 分隔文本（多消息空行分隔）。"""
        chunks = []
        for m in self._messages:
            chunks.append("|".join("{0}={1}".format(f.tag, f.value)
                                   for f in m.fields))
        return "\n\n".join(chunks)

    def _render_raw(self) -> None:
        self.raw_view.setPlainText(self._readable_text())

    def _copy_readable(self) -> None:
        text = self._readable_text()
        if not text:
            self._set_status(self.tr("暂无可复制的内容"), "hint")
            return
        QApplication.clipboard().setText(text)
        self._set_status(
            self.tr("已复制 {0} 条消息的可读原文（| 分隔）到剪贴板").format(len(self._messages)),
            "ok",
        )

    # ------------------------------------------------------------ 内部

    def _on_view_changed(self, *_args) -> None:
        view = self.view_combo.currentData()
        self.out_stack.setCurrentWidget(
            self.raw_view if view == VIEW_RAW else self.tab_widget)

    def _on_clear(self) -> None:
        self._timer.stop()
        self.input_edit.clear()
        self._clear_result()
        self._set_status("", "hint")
        self._update_counts()

    def _set_status(self, text: str, kind: str) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip("")     # 上一次导入失败的详细原因不要残留
        self._status_kind = kind
        self.status_label.setStyleSheet(f"color: {theme.css(kind)};")

    def _retheme(self) -> None:
        self.input_count.setStyleSheet(f"color: {theme.css('hint')};")
        self.status_label.setStyleSheet(f"color: {theme.css(self._status_kind)};")
        if self._messages:
            # tab 内摘要行 / 错误 tab 色取的是当前主题变体，切主题后重渲染
            cur = self.tab_widget.currentIndex()
            self._render_tabs()
            if 0 <= cur < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(cur)

    def _update_counts(self) -> None:
        text = self.input_edit.toPlainText()
        if not text:
            self.input_count.setText("")
        else:
            self.input_count.setText(QCoreApplication.translate(
                "FixPanel", "{0} 字符 / {1} 字节").format(
                len(text), len(text.encode("utf-8"))))
