"""设置对话框（偏好设置）：把散落在工具栏 / 菜单里的可配置项收拢到一处。

设计要点（与 NetworkPanel 一致）：
- 对话框**只编辑、不落盘**：值通过 ``values()`` 字典交还主窗口，
  由主窗口统一 ``save_settings`` 并同步工具栏/菜单——单一写入口，
  避免「对话框存一份、工具栏存一份」各写各的；
- 端口输入框 :class:`PortSpinBox` 从这里导出，主窗口工具栏同款复用
  （只允许键盘输入，屏蔽滚轮与微调按钮，防误改端口）。
"""

from __future__ import annotations

import platform
import subprocess

from PySide6.QtCore import QT_TRANSLATE_NOOP
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.i18n import available_languages
from app.mcpserver import is_exposed, local_ips
from app.rules import CONFIG_DIR
from app.settings import DEFAULT_MAX_FLOWS, FLOW_LIMIT_CHOICES
from app.ui import dialogs, theme


class PortSpinBox(QSpinBox):
    """端口输入框：只允许键盘输入，彻底屏蔽所有误改手段。

    - 构造处用 ``NoButtons`` 去掉上下微调按钮；
    - 这里再屏蔽滚轮事件，避免鼠标悬停在端口框上滚动页面时把端口改掉。
    """

    def wheelEvent(self, event):  # noqa: N802 (Qt 命名约定)
        # 不调用 super()，滚轮事件直接丢弃，端口值保持不变
        event.ignore()


#: 设置页分类（左侧列表）。文案用 QT_TRANSLATE_NOOP 打标——翻译器在
#: QApplication 创建后才装载，import 期求值永远是中文（NetworkPanel 同款）；
#: 构建列表时再 self.tr()。
_CATEGORIES = (
    QT_TRANSLATE_NOOP("SettingsDialog", "代理"),
    QT_TRANSLATE_NOOP("SettingsDialog", "流量列表"),
    QT_TRANSLATE_NOOP("SettingsDialog", "外观"),
    QT_TRANSLATE_NOOP("SettingsDialog", "会话"),
    QT_TRANSLATE_NOOP("SettingsDialog", "更新"),
)


class SettingsDialog(QDialog):
    """偏好设置对话框：左侧分类 + 右侧堆叠页。

    用法::

        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            values = dlg.values()
            ...  # 主窗口逐项应用（见 MainWindow._apply_settings）
    """

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("设置"))
        self.setMinimumWidth(600)
        self.setMinimumHeight(460)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        body = QHBoxLayout()
        body.setSpacing(10)
        self.category_list = QListWidget()
        self.category_list.setFixedWidth(116)
        for name in _CATEGORIES:
            QListWidgetItem(self.tr(name), self.category_list)
        self.category_list.currentRowChanged.connect(self._on_row_changed)
        body.addWidget(self.category_list)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_proxy_page(settings))
        self.pages.addWidget(self._build_traffic_page(settings))
        self.pages.addWidget(self._build_appearance_page(settings))
        self.pages.addWidget(self._build_session_page(settings))
        self.pages.addWidget(self._build_updates_page(settings))
        body.addWidget(self.pages, stretch=1)
        root.addLayout(body, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        dialogs.cn_button_box(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.category_list.setCurrentRow(0)

    # ================================================================ 页面

    def _build_proxy_page(self, settings) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox(self.tr("监听端口"))
        form = QVBoxLayout(box)
        form.setSpacing(6)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("代理端口:")))
        self.proxy_port_spin = PortSpinBox()
        self.proxy_port_spin.setRange(1024, 65535)
        self.proxy_port_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.proxy_port_spin.setAccelerated(False)
        self.proxy_port_spin.setValue(int(settings.proxy_port))
        self.proxy_port_spin.setToolTip(
            self.tr("HTTP/HTTPS 代理监听端口（默认 8888）\n"
            "被占用时自动顺延到下一个可用端口；修改后重启代理生效")
        )
        row.addWidget(self.proxy_port_spin)
        row.addStretch(1)
        form.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("证书端口:")))
        self.cert_port_spin = PortSpinBox()
        self.cert_port_spin.setRange(1024, 65535)
        self.cert_port_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.cert_port_spin.setAccelerated(False)
        self.cert_port_spin.setValue(int(settings.cert_port))
        self.cert_port_spin.setToolTip(
            self.tr("证书下载服务的监听端口（默认 8081，被占用时自动顺延）\n"
            "证书服务运行中修改会立即用新端口重启")
        )
        row.addWidget(self.cert_port_spin)
        row.addStretch(1)
        form.addLayout(row)
        layout.addWidget(box)

        box = QGroupBox(self.tr("系统代理"))
        form = QVBoxLayout(box)
        self.sysproxy_cb = QCheckBox(self.tr("启动代理时设为系统代理"))
        self.sysproxy_cb.setChecked(bool(settings.auto_system_proxy))
        self.sysproxy_cb.setToolTip(
            self.tr("启动代理时自动把系统 HTTP/HTTPS 代理指向本应用，停止或退出时自动还原\n"
            "（对齐 Fiddler「Act as System Proxy」）。\n"
            "macOS 首次接管会请求一次管理员授权；不想自动改系统设置就取消勾选。")
        )
        form.addWidget(self.sysproxy_cb)
        hint = self._hint(
            self.tr("与工具栏「设为系统代理」实时联动：代理运行中修改会立即接管或还原。")
        )
        form.addWidget(hint)
        layout.addWidget(box)

        layout.addStretch(1)
        return page

    def _build_traffic_page(self, settings) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox(self.tr("流量列表"))
        form = QVBoxLayout(box)
        form.setSpacing(6)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("保存条数:")))
        self.limit_combo = QComboBox()
        for n in FLOW_LIMIT_CHOICES:
            self.limit_combo.addItem(self.tr("{0} 条").format(n), n)
        self.limit_combo.setToolTip(
            self.tr("流量列表最多保留的会话数，超出后从最旧一条开始丢弃（上限 5000）")
        )
        idx = self.limit_combo.findData(int(settings.max_flows))
        self.limit_combo.setCurrentIndex(max(idx, 0))
        row.addWidget(self.limit_combo)
        row.addStretch(1)
        form.addLayout(row)

        self.auto_scroll_cb = QCheckBox(self.tr("自动滚动到最新会话"))
        self.auto_scroll_cb.setChecked(bool(settings.auto_scroll))
        self.auto_scroll_cb.setToolTip(
            self.tr("新会话到达时自动滚到最新一条。\n"
            "你手动翻到别处时不会来抢滚动条——只有停在最新端才跟着走。")
        )
        form.addWidget(self.auto_scroll_cb)

        self.newest_first_cb = QCheckBox(self.tr("新的会话显示在顶部"))
        self.newest_first_cb.setChecked(bool(settings.newest_first))
        self.newest_first_cb.setToolTip(
            self.tr("倒序 = 按到达序号降序，最新的会话排在最上面；\n"
            "取消勾选 = 到达顺序，新的在底部")
        )
        form.addWidget(self.newest_first_cb)

        self.body_wrap_cb = QCheckBox(self.tr("Body 默认自动换行"))
        self.body_wrap_cb.setChecked(bool(settings.body_wrap))
        self.body_wrap_cb.setToolTip(
            self.tr("请求/响应 Body 默认按窗口宽度换行；\n"
            "超长单行会被闸门临时关掉，也可在详情页随时改")
        )
        form.addWidget(self.body_wrap_cb)

        hint = self._hint(
            self.tr("以上各项与工具栏对应控件实时联动，改完点「确定」立即生效。")
        )
        form.addWidget(hint)
        layout.addWidget(box)

        # -- 断点调试：总开关在工具栏「断点」按钮，这里配阶段与命中范围
        bp_box = QGroupBox(self.tr("断点调试"))
        bp_form = QVBoxLayout(bp_box)
        bp_form.setSpacing(6)

        self.bp_request_cb = QCheckBox(self.tr("请求发出前暂停"))
        self.bp_request_cb.setChecked(bool(settings.breakpoint.on_request))
        self.bp_request_cb.setToolTip(
            self.tr("挂起后可改 URL / Header / Body，再放行发往服务器")
        )
        self.bp_response_cb = QCheckBox(self.tr("响应返回前暂停"))
        self.bp_response_cb.setChecked(bool(settings.breakpoint.on_response))
        self.bp_response_cb.setToolTip(
            self.tr("挂起后可改状态码 / Header / Body，再放行返回给客户端")
        )
        bp_form.addWidget(self.bp_request_cb)
        bp_form.addWidget(self.bp_response_cb)

        kw_row = QHBoxLayout()
        kw_row.addWidget(QLabel(self.tr("URL 关键词:")))
        self.bp_keywords_edit = QLineEdit(", ".join(settings.breakpoint.url_keywords))
        self.bp_keywords_edit.setPlaceholderText(
            self.tr("逗号分隔；留空 = 拦截全部")
        )
        kw_row.addWidget(self.bp_keywords_edit, stretch=1)
        bp_form.addLayout(kw_row)

        bp_form.addWidget(self._hint(
            self.tr("总开关在工具栏的「断点」按钮上：开启后命中会话会挂起，"
                    "改完点「继续放行」。")
        ))
        layout.addWidget(bp_box)

        # -- MCP 接口：监听地址 + 端口（开关仍在工具栏「MCP」按钮上）
        mcp_box = QGroupBox(self.tr("MCP 接口"))
        mcp_form = QVBoxLayout(mcp_box)
        mcp_form.setSpacing(6)

        host_row = QHBoxLayout()
        host_row.addWidget(QLabel(self.tr("监听地址:")))
        self.mcp_host_combo = QComboBox()
        self.mcp_host_combo.setEditable(True)
        self.mcp_host_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.mcp_host_combo.setMinimumWidth(180)
        # 先给两个固定档位，再把探测到的本机局域网 IP 列出来（方便只开某一张网卡）
        for value, label in (
            ("127.0.0.1", self.tr("仅本机（127.0.0.1）")),
            ("0.0.0.0", self.tr("局域网：全部网卡（0.0.0.0）")),
        ):
            self.mcp_host_combo.addItem(label, value)
        for ip in local_ips():
            self.mcp_host_combo.addItem(self.tr("局域网：{0}").format(ip), ip)
        self.mcp_host_combo.setToolTip(
            self.tr("MCP 服务绑定哪个网卡。\n"
                    "仅本机 = 只有这台机器能调；改成局域网后，同网段设备（含手机、\n"
                    "另一台电脑上的 AI 客户端）都能读到完整抓包——含 Cookie / 鉴权头。\n"
                    "也可直接填某个网卡 IP，只允许经该网卡访问。")
        )
        host_row.addWidget(self.mcp_host_combo)
        host_row.addStretch(1)
        mcp_form.addLayout(host_row)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel(self.tr("端口:")))
        self.mcp_port_spin = QSpinBox()
        self.mcp_port_spin.setRange(1, 65535)
        self.mcp_port_spin.setValue(int(getattr(settings, "mcp_port", 8899) or 8899))
        self.mcp_port_spin.setToolTip(
            self.tr("被占用时会向上顺延，实际端口看启动后的状态栏提示。")
        )
        port_row.addWidget(self.mcp_port_spin)
        port_row.addStretch(1)
        mcp_form.addLayout(port_row)

        saved_host = str(getattr(settings, "mcp_host", "127.0.0.1") or "").strip()
        idx = self.mcp_host_combo.findData(saved_host)
        if idx >= 0:
            self.mcp_host_combo.setCurrentIndex(idx)
        elif saved_host:
            self.mcp_host_combo.setEditText(saved_host)

        # 写操作开关：默认关。打开后 MCP 客户端可新增 Mock 规则、重放会话、
        # 开关断点——等于把改写流量行为的能力交出去，必须显式授权
        self.mcp_write_cb = QCheckBox(self.tr("允许 MCP 写操作"))
        self.mcp_write_cb.setChecked(
            bool(getattr(settings, "mcp_write_enabled", False))
        )
        self.mcp_write_cb.setToolTip(
            self.tr("打开后 AI 客户端可调用 add_mock_rule（新增 Mock 规则）/ "
                    "replay_flow（重放会话）/ set_breakpoint（开关断点）。\n"
                    "关闭时这三个工具对客户端不存在。监听地址为局域网时尤其要谨慎。")
        )
        mcp_form.addWidget(self.mcp_write_cb)

        self.mcp_exposed_hint = self._hint("")
        mcp_form.addWidget(self.mcp_exposed_hint)
        # 选到局域网地址时提示要变红警告——这一步是安全提示，不能只在 tooltip 里
        self.mcp_host_combo.currentIndexChanged.connect(self._update_mcp_hint)
        self.mcp_host_combo.editTextChanged.connect(self._update_mcp_hint)
        self._update_mcp_hint()
        layout.addWidget(mcp_box)

        layout.addStretch(1)
        return page

    def _build_appearance_page(self, settings) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox(self.tr("主题与语言"))
        form = QVBoxLayout(box)
        form.setSpacing(6)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("主题:")))
        self.theme_combo = QComboBox()
        for mode, label in (
            ("system", self.tr("跟随系统")),
            ("light", self.tr("浅色模式")),
            ("dark", self.tr("深色模式")),
        ):
            self.theme_combo.addItem(label, mode)
        self.theme_combo.setCurrentIndex(
            max(self.theme_combo.findData(getattr(settings, "theme", "system")), 0)
        )
        self.theme_combo.setToolTip(self.tr("切换后立即生效，下次启动保持"))
        row.addWidget(self.theme_combo)
        row.addStretch(1)
        form.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("语言:")))
        self.lang_combo = QComboBox()
        for code, label in available_languages().items():
            self.lang_combo.addItem(label, code)
        idx = self.lang_combo.findData(getattr(settings, "language", "zh_CN"))
        self.lang_combo.setCurrentIndex(max(idx, 0))
        self.lang_combo.setToolTip(self.tr("切换后重启 MiteProxy 生效"))
        row.addWidget(self.lang_combo)
        row.addStretch(1)
        form.addLayout(row)

        hint = self._hint(
            self.tr("主题切换立即生效；语言需要重启应用（翻译器在启动时装载）。")
        )
        form.addWidget(hint)
        layout.addWidget(box)

        layout.addStretch(1)
        return page

    def _build_session_page(self, settings) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox(self.tr("会话快照"))
        form = QVBoxLayout(box)
        form.setSpacing(6)
        self.autosave_cb = QCheckBox(self.tr("退出时自动保存会话"))
        self.autosave_cb.setChecked(bool(settings.auto_save_session))
        self.autosave_cb.setToolTip(
            self.tr("退出时把本次会话快照到磁盘，下次启动可一键恢复。\n"
            "会话始终在内存，只有退出时才落盘，不影响抓包性能。")
        )
        form.addWidget(self.autosave_cb)

        hint = self._hint(
            self.tr("与「文件 → 退出时自动保存会话」是同一开关。")
        )
        form.addWidget(hint)
        layout.addWidget(box)

        box = QGroupBox(self.tr("配置目录"))
        form = QVBoxLayout(box)
        form.setSpacing(6)
        row = QHBoxLayout()
        self.config_dir_edit = QLineEdit(str(CONFIG_DIR))
        self.config_dir_edit.setReadOnly(True)
        row.addWidget(self.config_dir_edit)
        open_btn = QPushButton(self.tr("打开"))
        open_btn.setToolTip(self.tr("在文件管理器中打开配置目录"))
        open_btn.clicked.connect(self._open_config_dir)
        row.addWidget(open_btn)
        form.addLayout(row)
        hint = self._hint(
            self.tr("settings.json（本机设置）、rules.json（Mock 规则）、\n"
            "证书与日志都在这里；删 settings.json 可恢复全部默认设置。")
        )
        form.addWidget(hint)
        layout.addWidget(box)

        layout.addStretch(1)
        return page

    def _build_updates_page(self, settings) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox(self.tr("自动更新"))
        form = QVBoxLayout(box)
        form.setSpacing(6)
        self.check_update_cb = QCheckBox(self.tr("启动时检查更新"))
        self.check_update_cb.setChecked(bool(settings.check_update_on_startup))
        self.check_update_cb.setToolTip(
            self.tr("启动后静默检查新版本，只有确实有新版才弹窗；\n"
            "网络不通一律静默，不影响抓包主流程。手动检查不受此项影响。")
        )
        form.addWidget(self.check_update_cb)

        hint = self._hint(
            self.tr("手动检查：菜单「帮助 → 检查更新…」。")
        )
        form.addWidget(hint)
        layout.addWidget(box)

        layout.addStretch(1)
        return page

    # ================================================================ 值

    def values(self) -> dict:
        """当前编辑结果（纯读取，不改控件——避免和信号形成回路）。

        由主窗口在 ``exec()`` 返回 Accepted 后逐项应用并落盘。
        """
        return {
            "proxy_port": self.proxy_port_spin.value(),
            "cert_port": self.cert_port_spin.value(),
            "auto_system_proxy": self.sysproxy_cb.isChecked(),
            "max_flows": self.limit_combo.currentData() or DEFAULT_MAX_FLOWS,
            "auto_scroll": self.auto_scroll_cb.isChecked(),
            "newest_first": self.newest_first_cb.isChecked(),
            "body_wrap": self.body_wrap_cb.isChecked(),
            "theme": self.theme_combo.currentData() or "system",
            "language": self.lang_combo.currentData() or "zh_CN",
            "auto_save_session": self.autosave_cb.isChecked(),
            "check_update_on_startup": self.check_update_cb.isChecked(),
            # MCP：开关归工具栏按钮管，这里只回传监听地址与端口
            "mcp_host": self._mcp_host_value(),
            "mcp_port": int(self.mcp_port_spin.value()),
            "mcp_write_enabled": bool(self.mcp_write_cb.isChecked()),
            # 断点：总开关归工具栏按钮管，这里只回传阶段与命中范围
            "breakpoint": {
                "on_request": self.bp_request_cb.isChecked(),
                "on_response": self.bp_response_cb.isChecked(),
                "url_keywords": [
                    k.strip()
                    for k in self.bp_keywords_edit.text().split(",")
                    if k.strip()
                ],
            },
        }

    # ================================================================ 内部

    def _on_row_changed(self, row: int) -> None:
        if row >= 0:
            self.pages.setCurrentIndex(row)

    def _mcp_host_value(self) -> str:
        """监听地址下拉的当前值。

        坑：可编辑 combo 里手输文本时 ``currentIndex()`` 仍停在原项上，
        直接取 ``currentData()`` 会把手输的 IP 顶掉（实测输 192.168.1.7
        交回 127.0.0.1）。所以只在「当前文本就是该项文本」时才用 data——
        那说明是选中了预设项而不是手输。
        """
        text = (self.mcp_host_combo.currentText() or "").strip()
        idx = self.mcp_host_combo.currentIndex()
        if idx >= 0 and self.mcp_host_combo.itemText(idx) == self.mcp_host_combo.currentText():
            data = self.mcp_host_combo.itemData(idx)
            if isinstance(data, str) and data:
                return data
        return text or "127.0.0.1"

    def _update_mcp_hint(self) -> None:
        """监听地址对局域网开放时把提示切成警告色。"""
        host = self._mcp_host_value()
        if is_exposed(host):
            self.mcp_exposed_hint.setText(
                self.tr("警告：当前地址对局域网开放，同网段任何人都能读到完整抓包"
                        "（含 Cookie / 鉴权头）。用完记得关掉工具栏的「MCP」按钮。")
            )
            self.mcp_exposed_hint.setStyleSheet(f"color: {theme.css('warn')};")
        else:
            self.mcp_exposed_hint.setText(
                self.tr("总开关在工具栏的「MCP」按钮上，默认关。改完点「确定」立即生效"
                        "（MCP 正在运行时会自动重启）。")
            )
            self.mcp_exposed_hint.setStyleSheet(f"color: {theme.css('hint')};")

    def _hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {theme.css('hint')};")
        return label

    def _open_config_dir(self) -> None:
        """在文件管理器里打开配置目录（跨平台：open / explorer / xdg-open）。"""
        path = str(CONFIG_DIR)
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["explorer", path])
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            dialogs.warning(
                self,
                self.tr("无法打开配置目录"),
                self.tr("请手动前往：\n{0}").format(path),
            )
