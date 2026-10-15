"""主窗口：工具栏 + 过滤栏 + 搜索栏 + 流量表格/详情 + Mock 规则页。

线程边界（DESIGN.md 2.4）：
- mitmproxy 在 ProxyService 的 asyncio 线程运行；
- CaptureAddon 只调 FlowBridge.emit_flow（pyqtSignal，跨线程安全）；
- 本类所有方法都在 Qt 主线程执行。
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from addons.capture import CaptureAddon
from addons.maplocal import MapLocalAddon
from addons.mock import MockAddon
from addons.throttle import ThrottleAddon
from app.certserver import CA_PEM_PATH, CertServer, _lan_ips
from app.ui.tool_panel import ToolPanel
from app.network import build_map_remote_specs, map_local_entries
from app.export import (
    FORMAT_HAR,
    FORMAT_RESPONSE,
    REQUIRES_RESPONSE,
    SINGLE_ONLY_FORMATS,
    build_curl_many,
    default_filename,
    ensure_suffix,
    export_bytes,
    name_filters,
)
from app.proxy import ProxyService
from app.replay import apply_request_edits, make_replay_copy
from app.rules import RuleStore
from app import session as session_mod
from app.session import (
    SESSION_EXT,
    archive_autosave,
    clear_autosave,
    load_session,
    read_autosave_meta,
    save_autosave,
    save_session,
)
from app.settings import (
    FLOW_LIMIT_CHOICES,
    Settings,
    load_settings,
    sanitize_max_flows,
    save_settings,
)
from app.bodyview import BODY_PREVIEW_LIMIT as BODY_SEND_LIMIT
from app import sysproxy
from app.textutil import decode_body
from app.ui.compare_dialog import CompareDialog
from app.ui.detail_panel import DetailPanel
from app.ui.filter_model import FlowFilterProxyModel
from app.ui.flow_store import COL_ID, FlowStore, format_size
from app.ui.network_panel import NetworkPanel
from app.ui.replay_dialog import ReplayEditDialog
from app.ui.rules_panel import RulesPanel
from app.ui.signals import FlowBridge
from app.ui.traffic_table import FilterBar, SearchBar, TrafficTable
from app.ui import theme

log = logging.getLogger(__name__)

CA_EXPORT_HINT = (
    "CA 证书位置：{path}\n\n"
    "macOS：双击后在「钥匙串访问」中设为始终信任；\n"
    "手机：点「证书服务」按钮，用手机浏览器打开显示的地址安装。"
)

#: 重放并对比：等重放响应到达的超时（秒）。超时说明上游没响应，
#: 清理 pending 并在状态栏告知，避免永远等一个不会来的 flow。
COMPARE_TIMEOUT_S = 20
#: 对比对话框保留个数：开太多不关也不至于无限攒着
COMPARE_DIALOG_KEEP = 5


class MainWindow(QMainWindow):
    def __init__(self, parent=None, restore_prompt: bool = True):
        super().__init__(parent)
        self.setWindowTitle("MiteProxy")
        self.resize(1280, 800)
        #: 启动时是否询问恢复上次会话快照（脚本/测试可关掉，避免模态框阻塞）
        self.restore_prompt = restore_prompt

        # ---- 核心对象
        self.settings: Settings = load_settings()
        # bridge 先建：规则命中回调要从代理线程回到主线程，得走信号
        self.bridge = FlowBridge()
        #: 系统代理接管/还原串行化：停代理与后台接管线程竞争时保证不漏还原
        self._sysproxy_lock = threading.Lock()
        self.rule_store = RuleStore()
        self.rule_store.load()
        self.rule_store.set_callbacks(
            on_change=self._on_rules_changed,
            on_rule_hit=self.bridge.emit_rule_hit,
            on_rule_error=self.bridge.emit_rule_error,
        )

        self.capture = CaptureAddon(
            on_flow=self.bridge.emit_flow,
            on_update=self.bridge.emit_flow_update,
        )
        self.mock = MockAddon(self.rule_store)
        self.throttle = ThrottleAddon(self.settings.throttle)
        self.maplocal = MapLocalAddon(
            map_local_entries(self.settings.map_rules)
        )

        self.proxy = self._make_proxy(self.settings.proxy_port)
        self.cert_server: CertServer | None = None
        # 整应用重启标记：置位后退出路径跳过系统代理还原（快照留给新实例，
        # 新实例启动时 recover_if_needed 先还原再接管，顺序才不会互相覆盖）
        self._restarting = False

        # ---- 重放并对比（DESIGN 3.6）：pending 等重放响应到达后关联弹框
        self._pending_compare: list[dict] = []
        self._compare_dialogs: list[CompareDialog] = []
        self._compare_timer = QTimer(self)
        self._compare_timer.setInterval(5000)
        self._compare_timer.timeout.connect(self._expire_pending_compare)

        # ---- 界面
        self._build_ui()
        self._build_menu()
        self._wire()

        # -- 主题：启动即应用保存的档位（默认跟随系统），
        #    并监听全局 PaletteChange（系统深浅切换 / 手动切档）广播给各面板
        theme.apply(getattr(self.settings, "theme", "system"))
        theme.add_listener(self._update_status)   # 切主题时状态栏重染色
        QApplication.instance().installEventFilter(self)

        self._apply_filter_config(self.settings.filter)
        self._apply_flow_limit(self.settings.max_flows)
        self._apply_list_order()
        self._restore_geometry()
        self._update_status()

        # 启动后询问是否恢复上次退出时的会话快照。
        # 用 singleShot(0) 而不是直接调用：等窗口先显示出来，模态框不会挡在空白窗口上；
        # restore_prompt=False 时不挂这个定时器，脚本环境不会有模态框阻塞。
        if self.restore_prompt:
            QTimer.singleShot(0, self._maybe_restore_autosave)

    # ================================================================ 窗口状态

    def _on_theme_selected(self, mode: str) -> None:
        """外观菜单切档：立即应用并落盘（下次启动保持）。"""
        self.settings.theme = mode
        save_settings(self.settings)
        theme.apply(mode)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        # 系统深浅色切换（或手动切档）后 Qt 广播 PaletteChange——singleShot(0)
        # 等调色板真正落位再广播，各面板的 _retheme 统一在这里触发
        if event.type() == QEvent.Type.PaletteChange \
                and obj is QApplication.instance():
            QTimer.singleShot(0, theme.notify)
        return super().eventFilter(obj, event)

    def _restore_geometry(self) -> None:
        geo = self.settings.window_geometry
        if geo:
            try:
                self.restoreGeometry(geo)
            except Exception:      # 损坏的几何数据不应阻断启动
                log.warning("窗口几何恢复失败，使用默认尺寸", exc_info=True)
        state = getattr(self.settings, "splitter_state", None)
        if state:
            try:
                self.traffic_splitter.restoreState(state)
            except Exception:
                log.warning("分隔条位置恢复失败，使用默认比例", exc_info=True)
            finally:
                # Qt 的 restoreState 会用 state 里记录的值覆盖 childrenCollapsible，
                # 必须重设，否则拖动分隔条时可以把某一边拖到 0（折叠消失）
                self.traffic_splitter.setChildrenCollapsible(False)

    def _on_layout_changed(self) -> None:
        """切换流量列表与详情区的排布方向（左右 ↔ 上下）。

        切换时按当前比例换算到新方向的长度，避免 Qt 用 sizeHint 重新分配
        把某一边挤没。选择立即落盘：就算之后崩溃，下次启动也是用户选的方向。
        """
        side = self.layout_combo.currentData() == "h"
        new = Qt.Orientation.Horizontal if side else Qt.Orientation.Vertical
        if self.traffic_splitter.orientation() == new:
            return
        sizes = self.traffic_splitter.sizes()   # [列表, 详情]，与方向无关
        self.traffic_splitter.setOrientation(new)
        total = sum(sizes)
        length = (self.traffic_splitter.width() if side
                  else self.traffic_splitter.height())
        if total > 0 and length > 0:
            first = max(int(length * sizes[0] / total), 60)
            self.traffic_splitter.setSizes([first, max(length - first, 60)])
        self.settings.traffic_side_by_side = side
        save_settings(self.settings)

    def _save_geometry(self) -> None:
        try:
            self.settings.window_geometry = bytes(self.saveGeometry())
            self.settings.splitter_state = bytes(self.traffic_splitter.saveState())
            save_settings(self.settings)
        except Exception:
            log.warning("窗口几何保存失败", exc_info=True)

    # ================================================================ UI 构建

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # -- 工具栏（排列：列表操作 | 抓包选项 | 代理控制 | 视图 | 低频功能）
        toolbar_row = QHBoxLayout()

        self.clear_btn = QPushButton("清除列表")
        toolbar_row.addWidget(self.clear_btn)

        toolbar_row.addSpacing(12)
        toolbar_row.addWidget(QLabel("保存数量:"))
        self.limit_combo = QComboBox()
        for n in FLOW_LIMIT_CHOICES:
            self.limit_combo.addItem(f"{n} 条", n)
        self.limit_combo.setToolTip(
            "流量列表最多保留的会话数，超出后从最旧一条开始丢弃（上限 5000）"
        )
        idx = self.limit_combo.findData(self.settings.max_flows)
        self.limit_combo.setCurrentIndex(max(idx, 0))
        toolbar_row.addWidget(self.limit_combo)

        # URL 关键字高亮（v1.15）：实时生效，对新到的流量也生效——
        # 与「搜索」（只针对当时的历史请求）互补
        toolbar_row.addSpacing(12)
        toolbar_row.addWidget(QLabel("高亮:"))
        self.highlight_edit = QLineEdit()
        self.highlight_edit.setPlaceholderText("URL 关键字")
        self.highlight_edit.setClearButtonEnabled(True)
        self.highlight_edit.setFixedWidth(150)
        self.highlight_edit.setToolTip(
            "URL 包含该关键字的请求整行黄色高亮。\n"
            "实时生效：正在显示的与之后新到的流量都会高亮；清空即关闭。"
        )
        toolbar_row.addWidget(self.highlight_edit)

        toolbar_row.addSpacing(12)
        self.auto_scroll_cb = QCheckBox("自动滚动")
        self.auto_scroll_cb.setChecked(self.settings.auto_scroll)
        self.auto_scroll_cb.setToolTip(
            "新会话到达时自动滚到最新一条。\n"
            "你手动翻到别处时不会来抢滚动条——只有停在最新端才跟着走。"
        )
        toolbar_row.addWidget(self.auto_scroll_cb)

        self.sysproxy_cb = QCheckBox("设为系统代理")
        self.sysproxy_cb.setChecked(self.settings.auto_system_proxy)
        self.sysproxy_cb.setToolTip(
            "启动代理时自动把系统 HTTP/HTTPS 代理指向本应用，停止或退出时自动还原\n"
            "（对齐 Fiddler「Act as System Proxy」）。\n"
            "macOS 首次接管会请求一次管理员授权；不想自动改系统设置就取消勾选。"
        )
        self.sysproxy_cb.toggled.connect(self._on_sysproxy_toggled)
        toolbar_row.addWidget(self.sysproxy_cb)

        toolbar_row.addSpacing(12)
        self.proxy_btn = QPushButton("启动代理")
        self.proxy_btn.setCheckable(True)
        toolbar_row.addWidget(self.proxy_btn)

        toolbar_row.addWidget(QLabel("端口:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(self.settings.proxy_port)
        # editingFinished（回车/失焦提交）而非 valueChanged：后者每敲一个数字
        # 触发一次，运行中会连续 stop/start 代理，中间值还可能撞别的端口
        self.port_spin.editingFinished.connect(self._on_port_changed)
        toolbar_row.addWidget(self.port_spin)

        toolbar_row.addSpacing(12)
        toolbar_row.addWidget(QLabel("顺序:"))
        self.order_combo = QComboBox()
        self.order_combo.addItem("到达顺序（新在底部）", False)
        self.order_combo.addItem("新的在顶部", True)
        self.order_combo.setToolTip("倒序 = 按到达序号降序，最新的会话排在最上面")
        self.order_combo.setCurrentIndex(1 if self.settings.newest_first else 0)
        toolbar_row.addWidget(self.order_combo)

        toolbar_row.addWidget(QLabel("布局:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItem("左右布局", "h")
        self.layout_combo.addItem("上下布局", "v")
        self.layout_combo.setToolTip(
            "流量列表与详情区的排布方向。左右 = Fiddler 风格（列表在左、body 在右），\n"
            "上下 = 列表在上、body 在下。选择会记住，下次启动保持。"
        )
        self.layout_combo.setCurrentIndex(
            0 if getattr(self.settings, "traffic_side_by_side", True) else 1
        )
        self.layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        toolbar_row.addWidget(self.layout_combo)

        # 证书功能不常用，放到工具栏最后面（DESIGN：低频操作靠右）
        toolbar_row.addSpacing(12)
        self.cert_btn = QPushButton("证书服务")
        self.cert_btn.setToolTip("启动局域网证书下载服务（手机装 CA 用）")
        toolbar_row.addWidget(self.cert_btn)

        self.export_ca_btn = QPushButton("导出 CA 证书")
        toolbar_row.addWidget(self.export_ca_btn)

        toolbar_row.addStretch(1)
        root.addLayout(toolbar_row)

        # -- 过滤栏 / 搜索栏
        self.filter_bar = FilterBar()
        root.addWidget(self.filter_bar)

        self.search_bar = SearchBar()
        self.search_bar.hide()
        root.addWidget(self.search_bar)

        # -- 标签页：流量 / Mock 规则
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, stretch=1)

        # 流量页
        traffic_page = QWidget()
        traffic_layout = QVBoxLayout(traffic_page)
        traffic_layout.setContentsMargins(0, 0, 0, 0)
        # 左右（Fiddler 风格，默认）或上下，用户可在工具栏切换
        side_by_side = bool(getattr(self.settings, "traffic_side_by_side", True))
        self.traffic_splitter = QSplitter(
            Qt.Orientation.Horizontal if side_by_side
            else Qt.Orientation.Vertical
        )
        self.traffic_splitter.setHandleWidth(6)   # 分隔条加宽：看得见、好抓
        self.flow_store = FlowStore()
        self.traffic_table = TrafficTable()
        self.proxy_model = FlowFilterProxyModel()
        self.proxy_model.setSourceModel(self.flow_store)
        self.proxy_model.flow_lookup = self.capture.get_flow
        self.traffic_table.setModel(self.proxy_model)
        self.detail_panel = DetailPanel(wrap_default=self.settings.body_wrap)
        # 水平方向 Ignored：详情面板不向 splitter 申报宽度意图。
        # 否则切换请求时（长 URL 摘要、表单列宽、图片页等 sizeHint 变化）会
        # 触发 splitter 重新分配，body 区域左右漂移；显式最小宽度防拖穿。
        self.detail_panel.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.detail_panel.setMinimumWidth(200)
        self.traffic_splitter.addWidget(self.traffic_table)
        self.traffic_splitter.addWidget(self.detail_panel)
        self.traffic_splitter.setSizes([420, 300])
        self.traffic_splitter.setChildrenCollapsible(False)
        traffic_layout.addWidget(self.traffic_splitter)
        self.tabs.addTab(traffic_page, "流量")

        # Mock 规则页
        self.rules_panel = RulesPanel(self.rule_store)
        self.tabs.addTab(self.rules_panel, "Mock 规则")

        # 网络模拟页（弱网限速 + 域名映射）
        self.network_panel = NetworkPanel()
        self.network_panel.load_config(self.settings.throttle, self.settings.map_rules)
        self.tabs.addTab(self.network_panel, "网络模拟")

        # 工具页（编码转换 + JSON 格式化/JSONPath，对齐 Fiddler TextWizard + json.cn）
        self.tool_panel = ToolPanel()
        self.tabs.addTab(self.tool_panel, "工具")

        # -- 状态栏
        self.status_bar = self.statusBar()
        self.count_label = QLabel("")
        self.proxy_state_label = QLabel("代理未启动")
        self.cert_state_label = QLabel("")
        for w in (self.count_label, self.proxy_state_label, self.cert_state_label):
            self.status_bar.addPermanentWidget(w)
        # Fiddler 式左下角抓包状态：绿点=接管系统代理抓包中，点击切换
        self.capture_label = QLabel("")
        self.capture_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.capture_label.setToolTip(
            "点击开始/停止抓包（接管或还原系统代理，与工具栏「设为系统代理」联动）"
        )
        self.capture_label.mousePressEvent = lambda _ev: self._on_capture_clicked()
        self.status_bar.insertWidget(0, self.capture_label)

        # Ctrl+F 全局快捷键
        from PySide6.QtGui import QShortcut

        QShortcut(QKeySequence("Ctrl+F"), self, self._on_find_shortcut)
        # Ctrl+R 重放选中请求（对齐 Fiddler）
        QShortcut(QKeySequence("Ctrl+R"), self, lambda: self._replay_selected(edit=False))
        # 复制 / 导出选中会话（对齐 Fiddler 的右键 Copy / Save 菜单）
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, lambda: self._copy_curl("posix"))
        QShortcut(QKeySequence("Ctrl+Shift+U"), self, self._copy_url)
        QShortcut(QKeySequence("Ctrl+E"), self, self._export_selected)
        # Ctrl+Shift+E 直达「完整响应（Headers+Body）」导出
        QShortcut(
            QKeySequence("Ctrl+Shift+E"),
            self,
            lambda: self._export_selected(FORMAT_RESPONSE),
        )

        # 流量表格右键菜单
        self.traffic_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.traffic_table.customContextMenuRequested.connect(self._on_table_context_menu)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        save_action = QAction("保存会话…", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._save_session_dialog)
        file_menu.addAction(save_action)

        open_action = QAction("打开会话…", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._open_session_dialog)
        file_menu.addAction(open_action)

        file_menu.addSeparator()
        clear_action = QAction("清除列表", self)
        clear_action.triggered.connect(self._on_clear)
        file_menu.addAction(clear_action)

        file_menu.addSeparator()
        auto_action = QAction("退出时自动保存会话", self)
        auto_action.setCheckable(True)
        auto_action.setChecked(self.settings.auto_save_session)
        auto_action.toggled.connect(self._on_toggle_autosave)
        file_menu.addAction(auto_action)
        self.autosave_action = auto_action

        file_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        tool_menu = self.menuBar().addMenu("工具")
        codec_action = QAction("编码转换…", self)
        codec_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        codec_action.triggered.connect(lambda: self._goto_tool("codec"))
        tool_menu.addAction(codec_action)

        json_action = QAction("JSON 格式化 / 提取…", self)
        json_action.setShortcut(QKeySequence("Ctrl+Shift+J"))
        json_action.triggered.connect(lambda: self._goto_tool("json"))
        tool_menu.addAction(json_action)

        compare_action = QAction("JSON 比对…", self)
        compare_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        compare_action.triggered.connect(lambda: self._goto_tool("compare"))
        tool_menu.addAction(compare_action)

        # -- 外观：跟随系统 / 浅色 / 深色（默认跟随系统，选择随 settings 持久化）
        view_menu = self.menuBar().addMenu("外观")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._theme_actions: dict[str, QAction] = {}
        for mode, label in (
            ("system", "跟随系统"),
            ("light", "浅色模式"),
            ("dark", "深色模式"),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(self.settings.theme == mode)
            action.triggered.connect(
                lambda _=False, m=mode: self._on_theme_selected(m)
            )
            self._theme_group.addAction(action)
            view_menu.addAction(action)
            self._theme_actions[mode] = action

        menu = self.menuBar().addMenu("帮助")
        feedback_action = QAction("意见反馈…", self)
        feedback_action.triggered.connect(self._show_feedback)
        menu.addAction(feedback_action)
        about = QAction("关于", self)
        about.triggered.connect(self._show_about)
        menu.addAction(about)

    def _goto_tool(self, page: str = "codec") -> None:
        """切到工具页的指定子页并把焦点给输入框。"""
        self.tabs.setCurrentWidget(self.tool_panel)
        self.tool_panel.show_page(page)
        if page == "json":
            editor = self.tool_panel.json_panel.input_edit
        elif page == "compare":
            editor = self.tool_panel.compare_panel.left_edit
        else:
            editor = self.tool_panel.codec_panel.input_edit
        editor.setFocus()
        editor.selectAll()

    def _wire(self) -> None:
        self.proxy_btn.clicked.connect(self._on_toggle_proxy)
        self.cert_btn.clicked.connect(self._on_toggle_cert_server)
        self.export_ca_btn.clicked.connect(self._on_export_ca)
        self.clear_btn.clicked.connect(self._on_clear)
        self.limit_combo.currentIndexChanged.connect(self._on_flow_limit_changed)
        self.highlight_edit.textChanged.connect(self.flow_store.set_highlight)

        self.bridge.flow_arrived.connect(self._on_flow_arrived)
        self.bridge.flow_updated.connect(self._on_flow_updated)
        self.bridge.rule_hit.connect(self.rules_panel.update_hit)
        self.bridge.rule_error.connect(self.rules_panel.update_rule_error)
        self.bridge.sysproxy_done.connect(self._on_sysproxy_done)
        self.filter_bar.changed.connect(self._on_filter_changed)
        self.search_bar.config_changed.connect(self._on_search_changed)
        self.search_bar.closed.connect(self._on_search_closed)
        self.search_bar.prev_btn.clicked.connect(lambda: self._cycle_match(-1))
        self.search_bar.next_btn.clicked.connect(lambda: self._cycle_match(1))

        self.auto_scroll_cb.toggled.connect(self._on_auto_scroll_changed)
        self.order_combo.currentIndexChanged.connect(self._on_order_changed)
        self.detail_panel.wrap_changed.connect(self._on_body_wrap_changed)

        self.traffic_table.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )
        # 排序状态变化 → 状态栏显示「已排序」
        self.traffic_table.horizontalHeader().sortIndicatorChanged.connect(
            lambda *_: self._update_status()
        )

        self.network_panel.changed.connect(self._on_network_changed)

    # ================================================================ 代理控制

    def _make_proxy(self, port: int) -> ProxyService:
        """构造代理实例（addon 与启动选项都从这里统一来）。

        端口变更/重启都走这里，避免出现「重建代理时漏了某个 addon 或漏了
        域名映射选项」这种只在重启后才暴露的偏差。
        """
        specs, _ = build_map_remote_specs(self.settings.map_rules)
        # 告诉 MockAddon 本代理监听哪：重定向规则指向自己时直接拒绝（死循环）
        self.mock.proxy_addr = ("127.0.0.1", port)
        return ProxyService(
            # 监听全部网卡（与证书服务一致）：手机/局域网设备才能通过
            # 内网 IP 走代理抓包；只绑 127.0.0.1 的话本机能用、手机连不上
            host="0.0.0.0",
            port=port,
            # 顺序很重要：throttle 必须排在会"造响应"的 mock / map-local 之后，
            # 这样在它的 request 钩子里 flow.response 才已被注入，弱网延迟才能
            # 作用到 mock 出来的接口上
            addons=[self.mock, self.capture, self.maplocal, self.throttle],
            options={"map_remote": specs},
        )

    def _on_toggle_proxy(self) -> None:
        if self.proxy.running:
            self.stop_proxy()
        else:
            self.start_proxy(verify=False)   # 手动启动失败已由按钮态自明，无需弹窗
            
    def start_proxy(self, verify: bool = False) -> bool:
        """启动代理（幂等）。verify=True 时异步校验是否真正监听成功。

        入口 main() 用 verify=True：若端口被占用，代理线程会立刻退出，
        由 _verify_proxy_started 收尾复位按钮并提示，避免出现
        "界面显示运行中、实际没有代理" 的假象。
        """
        if self.proxy.running:
            return True
        # 上次异常退出没还原的系统代理，先补还原（幂等，无记录时 no-op；
        # 快照丢失时按我们的端口兜底扫描关闭）
        sysproxy.recover_if_needed(port=self.settings.proxy_port)
        self.proxy.port = self.settings.proxy_port
        self.rule_store.load()      # 启动前重载规则（支持外部编辑 rules.json）
        # load() 会重建全部 Rule 对象，规则页表格还是旧引用——不刷新的话
        # 用户点「编辑/删除」时行号会映射到新列表的另一条规则上，静默改错
        self.rules_panel.refresh()
        self.proxy.start()
        self.proxy_btn.setText("停止代理")
        self.proxy_btn.setChecked(True)
        self._update_status()
        self._takeover_sysproxy_async()
        if verify:
            QTimer.singleShot(700, self._verify_proxy_started)
        return True

    def stop_proxy(self) -> None:
        """停止代理（幂等），同时收掉证书服务。"""
        if self.proxy.running:
            self.proxy.stop()
        self._stop_cert_server()
        self.proxy_btn.setText("启动代理")
        self.proxy_btn.setChecked(False)
        self._update_status()
        if not self._restarting:        # 整应用重启时快照留给新实例处理
            self._restore_sysproxy_async()

    # ------------------------------------------------------------ 系统代理接管

    def _sysproxy_enabled(self) -> bool:
        return self.sysproxy_cb.isChecked()

    def _takeover_sysproxy_async(self) -> None:
        """后台接管系统代理（networksetup 逐服务执行，可能要几秒，别卡 UI）。"""
        if not self._sysproxy_enabled():
            return

        def work():
            with self._sysproxy_lock:
                ok, msg = sysproxy.takeover(self.proxy.port)
            self.bridge.sysproxy_done.emit(ok, msg)

        threading.Thread(target=work, daemon=True, name="sysproxy-takeover").start()

    def _restore_sysproxy_async(self) -> None:
        port = self.proxy.port

        def work():
            with self._sysproxy_lock:
                ok, msg = sysproxy.restore(port=port)
            if msg != "无接管记录":
                self.bridge.sysproxy_done.emit(ok, msg)

        threading.Thread(target=work, daemon=True, name="sysproxy-restore").start()

    def _restore_sysproxy_sync(self) -> None:
        """退出路径用同步还原：必须还原完再关窗口。"""
        with self._sysproxy_lock:
            ok, msg = sysproxy.restore(port=self.proxy.port)
        if ok and msg != "无接管记录":
            log.info("系统代理已还原: %s", msg)

    def _on_sysproxy_done(self, ok: bool, msg: str) -> None:
        if ok:
            self.status_bar.showMessage(f"{msg}（停止代理或退出时自动还原）", 6000)
            return
        self.status_bar.showMessage(
            f"系统代理接管失败：{msg}（可手动设置代理 127.0.0.1:{self.proxy.port}）",
            8000,
        )
        # macOS 最常见失败原因是缺管理员权限 → 给一次提权重试（弹密码框）
        if (platform.system() == "darwin"
                and not getattr(self, "_sysproxy_elevate_asked", False)):
            self._sysproxy_elevate_asked = True  # 每次会话只问一次，别烦人
            answer = QMessageBox.question(
                self,
                "系统代理接管失败",
                f"{msg}\n\n用管理员权限重试？（会弹出密码确认框，与 Charles 行为一致）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes and self.proxy.running:
                threading.Thread(
                    target=lambda: self._sysproxy_elevated_takeover(),
                    daemon=True,
                    name="sysproxy-takeover-elevated",
                ).start()

    def _sysproxy_elevated_takeover(self) -> None:
        with self._sysproxy_lock:
            ok, msg = sysproxy.takeover(self.proxy.port, elevate=True)
        self.bridge.sysproxy_done.emit(ok, msg)

    def _on_sysproxy_toggled(self, checked: bool) -> None:
        self.settings.auto_system_proxy = checked
        save_settings(self.settings)
        self._update_capture_status()   # 左下角状态立即跟随
        if self.proxy.running:
            if checked:
                self._takeover_sysproxy_async()
            else:
                self._restore_sysproxy_async()

    def _verify_proxy_started(self) -> None:
        if not self.proxy_btn.isChecked():
            return                    # 用户已手动停掉，不打扰
        if self.proxy.running:
            return                    # 正常监听中
        # 线程已退出 → 启动失败（端口占用等）
        self.proxy_btn.setText("启动代理")
        self.proxy_btn.setChecked(False)
        self._update_status()
        self._restore_sysproxy_async()   # 可能刚接管完代理就挂了，补还原
        QMessageBox.critical(
            self,
            "代理启动失败",
            f"端口 {self.settings.proxy_port} 可能已被占用，或权限不足。\n"
            "请在工具栏换一个端口后重试。",
        )

    def _on_flow_limit_changed(self) -> None:
        limit = self.limit_combo.currentData()
        if limit is None:
            return
        self._apply_flow_limit(int(limit))
        save_settings(self.settings)

    def _apply_flow_limit(self, limit: int) -> None:
        """保存条数生效：列表立即从最旧一端裁剪，捕获缓存按需裁剪。

        `trim_now` 只在代理停止时给——代理运行中 `CaptureAddon.flows` 由
        asyncio 线程写，UI 线程不能遍历它（见 addons/capture.set_max_flows）。
        """
        limit = sanitize_max_flows(limit)
        self.settings.max_flows = limit
        self.capture.set_max_flows(limit, trim_now=not self.proxy.running)
        self.flow_store.set_max_rows(limit)
        self._update_status()

    def _on_port_changed(self) -> None:
        """端口变更（回车/失焦提交）：保存设置；运行中弹窗询问是否立即重启。

        对齐 Fiddler 心智：改端口需要重启代理才生效，让用户自己决定——
        选「是」立即重启（系统代理同步切到新端口），选「否」下次启动生效。
        """
        port = self.port_spin.value()
        if port == self.settings.proxy_port:
            return
        self.settings.proxy_port = port
        save_settings(self.settings)
        if not self.proxy.running:
            return
        answer = QMessageBox.question(
            self,
            "端口已修改",
            f"代理端口已修改为 {port}，需要重启才能生效。\n\n"
            "是否立即重启应用？重启后系统代理会自动切换到新端口。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._restart_app_for_port(port)
        else:
            self.status_bar.showMessage(
                f"新端口 {port} 将在下次启动时生效", 6000
            )

    def _app_restart_command(self) -> list[str] | None:
        """构造「重新拉起自己」的命令；构造不出来返回 None（走兜底）。"""
        exe = sys.executable
        if not exe:
            return None
        if getattr(sys, "frozen", False):
            if platform.system() == "darwin":
                bundle = Path(exe).parents[2]        # …/MiteProxy.app
                if bundle.name.endswith(".app") and bundle.is_dir():
                    return ["open", "-n", str(bundle)]
            return [exe]                             # Windows / 其他冻结环境
        # 源码运行：原样重新执行入口脚本（脚本目录自动进 sys.path）
        entry = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
        if entry.endswith(".py") and os.path.isfile(entry):
            return [exe, entry]
        return None

    def _restart_app_for_port(self, port: int) -> None:
        """整个应用退出并重新打开（对齐 Fiddler 的重启生效）。

        新实例监听新端口，不会撞旧实例正在释放的旧端口；系统代理不在这里
        还原——旧实例退出时保留接管快照，新实例启动时 recover_if_needed
        先还原旧接管、再按新端口重新接管，两条路径不会互相覆盖。
        """
        cmd = self._app_restart_command()
        if cmd is None:
            # 兜底：构造不出重启命令（异常运行环境），退回仅重启代理
            self._restart_proxy_on_port(port)
            return
        self._restarting = True
        self.status_bar.showMessage(f"正在重启应用，切换到端口 {port} …", 5000)
        try:
            subprocess.Popen(
                cmd,
                start_new_session=platform.system() != "Windows",
            )
        except Exception:
            log.exception("重启应用失败，退回仅重启代理")
            self._restarting = False
            self._restart_proxy_on_port(port)
            return
        self.close()        # 走 closeEvent：停代理、保留快照、不还原系统代理

    def _restart_proxy_on_port(self, port: int) -> None:
        """运行中按新端口重启代理 + 系统代理重接管 + 证书服务静默重启。"""
        self.status_bar.showMessage(f"正在重启代理，切换到 127.0.0.1:{port} …", 4000)
        self.proxy.stop(timeout=2.0)
        self.proxy = self._make_proxy(port)
        self.proxy.start()
        self._update_status()
        # 重启成功要有可见反馈：按钮文字不变、流量列表不清空，用户无从
        # 判断是否真的重启了（之前被当成「点了 Yes 没反应」）
        self.status_bar.showMessage(
            f"代理已重启，监听 127.0.0.1:{port}；系统代理切换中…", 8000
        )
        # 系统代理还挂在旧端口上：后台先还原再按新端口重接管。顺序不能反——
        # 直接重接管会把「127.0.0.1:旧端口」当成原始设置存进状态文件，还原就错了
        if self._sysproxy_enabled():
            self._retake_sysproxy(port)
        # 证书服务页面上显示的代理端口也要跟上
        if self.cert_server is not None and self.cert_server.running:
            self._stop_cert_server()
            try:
                server = CertServer(
                    port=self.settings.cert_port, proxy_port=port
                )
                server.start()
                self.cert_server = server
            except OSError:
                self.cert_server = None
                log.warning("证书服务重启失败（端口被占用？）", exc_info=True)
        # 新端口若被占用，代理线程会立刻退出——700ms 后校验并弹窗
        QTimer.singleShot(700, self._verify_proxy_started)

    def _retake_sysproxy(self, port: int) -> None:
        """后台「还原旧接管 → 按新端口重接管」，全程持锁避免与启停路径竞态。"""

        def work():
            with self._sysproxy_lock:
                sysproxy.restore()
                ok, msg = sysproxy.takeover(port)
            self.bridge.sysproxy_done.emit(ok, msg)

        threading.Thread(
            target=work, daemon=True, name="sysproxy-retake"
        ).start()

    def _on_toggle_cert_server(self) -> None:
        if self.cert_server is not None and self.cert_server.running:
            self._stop_cert_server()
            return
        try:
            server = CertServer(
                port=self.settings.cert_port, proxy_port=self.settings.proxy_port
            )
            server.start()
            self.cert_server = server
            self._show_cert_dialog(server)
        except FileNotFoundError:
            QMessageBox.critical(
                self,
                "未找到 CA 证书",
                f"请先启动一次代理以生成 CA 证书（{CA_PEM_PATH}）",
            )
        except ValueError as e:
            # CA 文件存在但内容为空/损坏：load_ca 解析时抛 ValueError
            QMessageBox.critical(
                self, "CA 证书损坏", f"证书文件无法解析，删除后重启可重新生成:\n{e}"
            )
        except OSError as e:
            QMessageBox.critical(self, "启动失败", f"端口 {self.settings.cert_port} 可能被占用:\n{e}")
        self._update_status()

    @staticmethod
    def _qr_pixmap(url: str) -> QPixmap | None:
        """URL → 二维码 QPixmap；segno 缺失/失败返回 None（调用方降级为纯文字）。"""
        try:
            import io

            import segno

            buf = io.BytesIO()
            segno.make(url, error="m").save(
                buf, kind="png", scale=6, border=2, dark="#1a1a1a"
            )
            pm = QPixmap()
            return pm if pm.loadFromData(buf.getvalue(), "PNG") else None
        except Exception:
            log.debug("弹窗二维码生成失败", exc_info=True)
            return None

    def _show_cert_dialog(self, server: CertServer) -> None:
        """证书服务弹窗：直接显示各局域网地址的二维码（v1.12 只有网页里有，
        弹窗只给纯链接——手机还得先抄地址，体验对齐「打开就扫」）。"""
        dlg = QDialog(self)
        dlg.setWindowTitle("证书服务已启动")
        lay = QVBoxLayout(dlg)
        hint = QLabel(
            "手机连上同一 Wi-Fi，用相机扫下方任一二维码（或浏览器打开地址），\n"
            "在打开的网页里下载并安装证书："
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)

        urls = [f"http://{ip}:{server.port}" for ip in _lan_ips()][:4]
        if not urls:
            urls = [server.url]     # 拿不到局域网 IP 时至少给本机地址
        row = QHBoxLayout()
        for url in urls:
            col = QVBoxLayout()
            col.addStretch(1)
            pm = self._qr_pixmap(url)
            if pm is not None:
                img = QLabel()
                img.setPixmap(pm)
                img.setAlignment(Qt.AlignmentFlag.AlignCenter)
                col.addWidget(img)
            lbl = QLabel(f'<a href="{url}">{url}</a>')
            lbl.setOpenExternalLinks(True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(lbl)
            col.addStretch(1)
            row.addLayout(col)
        lay.addLayout(row)

        tip = QLabel(
            f"安装证书后，手机 Wi-Fi 的代理请设为：电脑IP : {self.settings.proxy_port}"
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)
        btn = QPushButton("好")
        btn.setDefault(True)
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        dlg.exec()

    def _stop_cert_server(self) -> None:
        if self.cert_server is not None:
            self.cert_server.stop()
            self.cert_server = None
        self._update_status()

    def _on_export_ca(self) -> None:
        if not CA_PEM_PATH.exists():
            QMessageBox.critical(
                self, "未找到 CA 证书", CA_EXPORT_HINT.format(path=CA_PEM_PATH)
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CA 证书", "mitmproxy-ca-cert.pem", "证书 (*.pem *.cer)"
        )
        if path:
            shutil.copy(CA_PEM_PATH, path)
            QMessageBox.information(
                self, "已导出", CA_EXPORT_HINT.format(path=Path(path))
            )

    def _on_clear(self) -> None:
        self.flow_store.clear()
        self.capture.clear()
        self.detail_panel.clear()
        self._update_status()

    # ================================================================ 流量展示

    def _on_flow_arrived(self, summary: dict) -> None:
        # 自动滚动只在"用户本来就停在最新端"时才生效，且只在按到达顺序排列时——
        # 用户按耗时排完序再被拽回底部是最招人烦的。
        follow = (
            self.settings.auto_scroll
            and self._following_arrival()
            and self._at_newest_edge()
        )
        self.flow_store.append(summary)
        self._update_status()
        # 重放并对比：副本的 id 与pending 里记的 copy_id 一致，精确关联
        self._match_pending_compare(summary)
        if follow:
            self.traffic_table.scroll_to_newest(self.settings.newest_first)

    def _on_flow_updated(self, summary: dict) -> None:
        """已存在会话的增量更新（WebSocket 消息到达）。"""
        self.flow_store.update(summary)
        selected = self._selected_flow()
        if selected is not None and getattr(selected, "id", None) == summary.get("id"):
            self.detail_panel.update_flow(selected)
        self._update_status()

    def _following_arrival(self) -> bool:
        """当前排序是否是"到达顺序"（未排序或按 # 列排）。"""
        col = self.traffic_table.horizontalHeader().sortIndicatorSection()
        return col in (-1, COL_ID)

    def _at_newest_edge(self) -> bool:
        return (
            self.traffic_table.at_top() if self.settings.newest_first
            else self.traffic_table.at_bottom()
        )

    def _on_auto_scroll_changed(self, checked: bool) -> None:
        self.settings.auto_scroll = bool(checked)
        save_settings(self.settings)
        if checked:
            self.traffic_table.scroll_to_newest(self.settings.newest_first)

    def _on_order_changed(self) -> None:
        value = self.order_combo.currentData()
        if value is None:
            return
        self.settings.newest_first = bool(value)
        save_settings(self.settings)
        self._apply_list_order()
        self._update_status()

    def _apply_list_order(self) -> None:
        """把顺序设置落到表格：倒序 = 按 # 列降序，正序 = 回到自然到达顺序。"""
        if self.settings.newest_first:
            self.traffic_table.sortByColumn(COL_ID, Qt.SortOrder.DescendingOrder)
        else:
            header = self.traffic_table.horizontalHeader()
            header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
            self.proxy_model.sort(-1)

    def _on_body_wrap_changed(self, on: bool) -> None:
        self.settings.body_wrap = bool(on)
        save_settings(self.settings)

    def _on_selection_changed(self) -> None:
        flow = self._selected_flow()
        if flow is None:
            self.detail_panel.clear()
            self._update_status()
            return
        self.detail_panel.show_flow(flow)
        # 搜索生效时同步高亮
        if self.search_bar.isVisible() and self.search_bar.input.text():
            cfg = self.search_bar.to_config()
            self.detail_panel.highlight(cfg.text, cfg.case_sensitive)
        self._update_status()

    # ================================================================ 过滤 / 搜索

    def _on_filter_changed(self) -> None:
        config = self.filter_bar.to_config()
        self.settings.filter = config
        save_settings(self.settings)
        self._apply_filter_config(config)

    def _apply_filter_config(self, config) -> None:
        self.proxy_model.set_filter_config(config)
        self._update_status()

    def _on_find_shortcut(self) -> None:
        self.search_bar.focus_input()

    def _on_search_changed(self) -> None:
        cfg = self.search_bar.to_config()
        self.proxy_model.set_search_config(cfg)
        self._update_status()
        # 选中项同步高亮
        self._on_selection_changed()

    def _on_search_closed(self) -> None:
        self.search_bar.input.clear()
        self.search_bar.hide()
        self.proxy_model.set_search_config(self.search_bar.to_config())
        self.detail_panel.highlight("", False)
        self._update_status()

    def _cycle_match(self, delta: int) -> None:
        """Enter / 上下按钮：在匹配行间循环跳转（可见行即匹配行）。"""
        model = self.proxy_model
        if model.rowCount() == 0:
            return
        current = self.traffic_table.selectionModel().selectedRows()
        current_row = current[0].row() if current else -1
        next_row = (current_row + delta) % model.rowCount()
        self.traffic_table.selectRow(next_row)
        self.traffic_table.scrollTo(model.index(next_row, 0))

    # ================================================================ 重放

    def _on_table_context_menu(self, pos) -> None:
        flows = self._selected_flows()
        has_selection = bool(flows)
        count = len(flows)
        batch = f"（{count} 条）" if count > 1 else ""
        menu = QMenu(self)
        replay_action = menu.addAction("重放请求 (Ctrl+R)")
        edit_replay_action = menu.addAction("编辑并重放…")
        compare_action = menu.addAction("重放并对比…")
        menu.addSeparator()
        curl_action = menu.addAction(f"复制为 cURL (bash){batch}  Ctrl+Shift+C")
        curl_cmd_action = menu.addAction(f"复制为 cURL (Windows cmd){batch}")
        copy_url_action = menu.addAction(f"仅复制 URL{batch}  Ctrl+Shift+U")
        menu.addSeparator()
        export_action = menu.addAction(f"导出选中会话{batch}…  Ctrl+E")
        export_resp_action = menu.addAction("导出完整响应（Headers+Body）…")
        menu.addSeparator()
        tool_body_action = menu.addAction("在工具页中打开 body")
        tool_body_action.setEnabled(count == 1)
        tool_body_action.triggered.connect(self._send_body_to_tool)
        api_action = menu.addAction("发送到 API 调试")
        api_action.setEnabled(count == 1)
        api_action.triggered.connect(self._send_request_to_api)
        menu.addSeparator()
        mark_action = menu.addAction("标记/备注…")
        mark_action.setEnabled(count == 1)
        mark_action.triggered.connect(self._mark_selected)
        clear_mark_action = menu.addAction("清除备注")
        clear_mark_action.setEnabled(
            count == 1 and bool(getattr(flows[0], "comment", "") if flows else "")
        )
        clear_mark_action.triggered.connect(self._clear_mark_selected)

        for action in (replay_action, edit_replay_action, compare_action,
                       curl_action, curl_cmd_action, copy_url_action,
                       export_action, export_resp_action):
            action.setEnabled(has_selection)

        replay_action.triggered.connect(lambda: self._replay_selected(edit=False))
        edit_replay_action.triggered.connect(lambda: self._replay_selected(edit=True))
        # 先开编辑对话框（可改请求），确认后重放，响应到达自动弹对比框
        compare_action.triggered.connect(
            lambda: self._replay_selected(edit=True, compare=True)
        )
        curl_action.triggered.connect(lambda: self._copy_curl("posix"))
        curl_cmd_action.triggered.connect(lambda: self._copy_curl("cmd"))
        copy_url_action.triggered.connect(self._copy_url)
        export_action.triggered.connect(self._export_selected)
        export_resp_action.triggered.connect(lambda: self._export_selected(FORMAT_RESPONSE))
        menu.exec(self.traffic_table.viewport().mapToGlobal(pos))

    def _send_body_to_tool(self) -> None:
        """把选中会话的 body 送进工具页（有响应就用响应，否则用请求）。

        抓到一段 base64 参数或一段 JSON，直接送过去解/格式化，不用手选中再复制。
        送到哪个子页由用户当前停留在哪一页决定。
        """
        flows = self._selected_flows()
        if len(flows) != 1:
            return
        flow = flows[0]
        res = getattr(flow, "response", None)
        req = getattr(flow, "request", None)
        message = res if res is not None else req
        if message is None:
            return
        getter = getattr(message, "get_content", None)
        data = getter(strict=False) if callable(getter) else None
        if not data:
            self.status_bar.showMessage("该会话没有 body 可转换", 4000)
            return
        try:
            content_type = message.headers.get("content-type", "") or ""
        except Exception:  # pragma: no cover - headers 异常不该阻断
            content_type = ""
        if len(data) > BODY_SEND_LIMIT:
            data = data[:BODY_SEND_LIMIT]
            truncated = True
        else:
            truncated = False
        text = decode_body(data, content_type)
        if text is None:
            # 二进制内容没法当文本解——给十六进制，用户还能接着做 Hex 解码
            text = data.hex()
            note = "（二进制内容已按十六进制导入）"
        else:
            note = "（已截断到前 512KB）" if truncated else ""
        page = self.tool_panel.current_key
        self.tabs.setCurrentWidget(self.tool_panel)
        self.tool_panel.set_body_text(text, page)
        label = {"json": "JSON 工具", "compare": "JSON 比对", "api": "API 调试"}.get(
            page, "编码转换"
        )
        self.status_bar.showMessage(
            f"已把该会话的 body 送入工具页 · {label}{note}", 5000
        )

    def _send_request_to_api(self) -> None:
        """把选中会话的**整个请求**（method/URL/headers/body）带入 API 调试页。

        与 _send_body_to_tool 的差别：那个只送 body（当作要解/要格式的素材），
        这个送完整请求（当作要照着发的模板）——抓到一条接口调用，改几个
        参数重发是最高频的调试动作。
        """
        flows = self._selected_flows()
        if len(flows) != 1:
            return
        req = getattr(flows[0], "request", None)
        if req is None:
            return
        headers = {}
        try:
            for k, v in req.headers.items(multi=True):
                headers.setdefault(str(k), str(v))  # 重复头取首值（表单编辑不了多值）
        except TypeError:
            headers = {str(k): str(v) for k, v in req.headers.items()}
        body_text = ""
        data = req.get_content(strict=False) if callable(getattr(req, "get_content", None)) else b""
        if data:
            content_type = ""
            try:
                content_type = req.headers.get("content-type", "") or ""
            except Exception:  # pragma: no cover
                pass
            if len(data) > BODY_SEND_LIMIT:
                data = data[:BODY_SEND_LIMIT]
            text = decode_body(data, content_type)
            body_text = text if text is not None else data.hex()
        self.tabs.setCurrentWidget(self.tool_panel)
        self.tool_panel.show_page("api")
        self.tool_panel.api_panel.load_request(
            method=req.method, url=req.pretty_url, headers=headers, body=body_text
        )
        self.status_bar.showMessage("已把该请求带入 API 调试页（改完点「发送」）", 5000)

    # ================================================================ 复制 / 导出

    def _mark_selected(self) -> None:
        """给选中的单条会话写备注（对齐 Fiddler 的 Comment）。

        写 flow.comment（mitmproxy 原生字段，会话保存/恢复天然带上），
        不动 marked——那个是 MOCK/REPLAY 徽标的地盘。
        """
        flows = self._selected_flows()
        if len(flows) != 1:
            return
        flow = flows[0]
        text, ok = QInputDialog.getText(
            self,
            "标记/备注",
            "给这条会话写个备注（列表「标记」列显示）：",
            text=getattr(flow, "comment", "") or "",
        )
        if not ok:
            return
        self._set_flow_comment(flow, text.strip())

    def _clear_mark_selected(self) -> None:
        flows = self._selected_flows()
        if len(flows) != 1:
            return
        self._set_flow_comment(flows[0], "")

    def _set_flow_comment(self, flow, comment: str) -> None:
        flow.comment = comment
        flow_id = getattr(flow, "id", "")
        if not self.flow_store.set_comment(flow_id, comment):
            # 列表里没有这一行（理论上不会）：退回整行刷新
            self.flow_store.update(self.capture.summarize(flow))
        # 详情面板正看着这条的话，备注条要同步
        if getattr(self.detail_panel, "_flow", None) is flow:
            self.detail_panel.refresh_comment()
        self.status_bar.showMessage(
            "已备注" if comment else "已清除备注", 3000
        )

    def _copy_curl(self, style: str = "posix") -> None:
        flows = self._selected_flows()
        if not flows:
            return
        text = build_curl_many(flows, style=style)
        if not text:
            return
        QApplication.clipboard().setText(text)
        label = "bash" if style == "posix" else "Windows cmd"
        extra = f"{len(flows)} 条 · " if len(flows) > 1 else ""
        self.status_bar.showMessage(
            f"已复制 cURL（{label}，{extra}{len(text)} 字符）: {text[:80]}…", 5000
        )

    def _copy_url(self) -> None:
        flows = self._selected_flows()
        if not flows:
            return
        urls = [getattr(f.request, "pretty_url", "") or "" for f in flows]
        urls = [u for u in urls if u]
        if not urls:
            return
        QApplication.clipboard().setText("\n".join(urls))
        shown = urls[0] if len(urls) == 1 else f"{len(urls)} 条（首条 {urls[0]}）"
        self.status_bar.showMessage(f"已复制 URL: {shown}", 5000)

    def _export_selected(self, preferred: str | None = None) -> None:
        flows = self._selected_flows()
        if not flows:
            QMessageBox.information(self, "提示", "请先在流量列表里选中一条会话")
            return
        if len(flows) > 1 and preferred in SINGLE_ONLY_FORMATS:
            QMessageBox.information(
                self,
                "该格式不支持多选",
                "「仅响应 Body」一个文件只能装一条会话的 body。\n"
                "请只选一条，或改用 HAR / 原始报文 / 完整响应。",
            )
            return
        missing = [f for f in flows if getattr(f, "response", None) is None]
        if missing and (preferred in REQUIRES_RESPONSE):
            QMessageBox.information(
                self,
                "暂无响应",
                "所选会话里有还没响应的请求（请求进行中或连接已中断），无法导出。",
            )
            return
        filters, mapping = name_filters()
        selected = next((label for label, f in mapping.items() if f == preferred), None)
        path, selected = QFileDialog.getSaveFileName(
            self,
            f"导出选中会话（{len(flows)} 条）" if len(flows) > 1 else "导出选中会话",
            default_filename(flows, preferred or FORMAT_HAR),
            filters,
            selected or "",
        )
        if not path:
            return
        fmt = mapping.get(selected, preferred or FORMAT_HAR)
        if len(flows) > 1 and fmt in SINGLE_ONLY_FORMATS:
            QMessageBox.information(
                self, "该格式不支持多选", "「仅响应 Body」请只选一条会话。"
            )
            return
        if fmt in REQUIRES_RESPONSE and any(
            getattr(f, "response", None) is None for f in flows
        ):
            QMessageBox.information(self, "暂无响应", "所选会话里有还没响应的请求，无法导出。")
            return
        path = ensure_suffix(path, fmt, flows)
        try:
            Path(path).write_bytes(export_bytes(flows, fmt))
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "导出失败", f"写入 {path} 失败:\n{e}")
            return
        self.status_bar.showMessage(
            f"已导出 {len(flows)} 条 → {path}" if len(flows) > 1 else f"已导出 → {path}",
            5000,
        )

    def _selected_flows(self) -> list:
        """按列表中当前可见顺序返回选中会话（最多 5000 条，开销可忽略）。"""
        indexes = self.traffic_table.selectionModel().selectedRows()
        if not indexes:
            return []
        out = []
        for index in sorted(indexes, key=lambda i: i.row()):
            source_index = self.proxy_model.mapToSource(index)
            row = self.flow_store.row_data(source_index.row())
            if row is None:
                continue
            flow = self.capture.get_flow(row["id"])
            if flow is not None:
                out.append(flow)
        return out

    def _selected_flow(self):
        """详情面板/重放用的主选中项：取多选里的第一条。"""
        flows = self._selected_flows()
        return flows[0] if flows else None

    # ================================================================ 会话保存 / 恢复

    def _session_flows(self) -> list:
        """按列表到达顺序取出全部活会话（保存用）。"""
        out = []
        for row in self.flow_store.all_rows():
            flow = self.capture.get_flow(row["id"])
            if flow is not None:
                out.append(flow)
        return out

    def _session_start_dir(self) -> str:
        saved = self.settings.last_session_dir
        if saved and Path(saved).is_dir():
            return saved
        try:
            # 经模块取（不按值导入）：路径可被测试/脚本改写到临时目录
            session_mod.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            return str(session_mod.SESSIONS_DIR)
        except OSError:
            return str(Path.home())

    def _remember_session_dir(self, path: str) -> None:
        self.settings.last_session_dir = str(Path(path).parent)
        save_settings(self.settings)

    def _on_toggle_autosave(self, checked: bool) -> None:
        self.settings.auto_save_session = bool(checked)
        save_settings(self.settings)
        self.status_bar.showMessage(
            "退出时将自动保存会话快照" if checked else "已关闭退出自动保存", 4000
        )

    def _save_session_dialog(self) -> None:
        flows = self._session_flows()
        if not flows:
            QMessageBox.information(self, "没有可保存的会话", "当前列表是空的。")
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        default = str(Path(self._session_start_dir()) / f"session-{stamp}{SESSION_EXT}")
        path, _ = QFileDialog.getSaveFileName(
            self, f"保存会话（{len(flows)} 条）", default, f"会话文件 (*{SESSION_EXT})"
        )
        if not path:
            return
        if not path.lower().endswith(SESSION_EXT):
            path += SESSION_EXT
        result = save_session(path, flows)
        if not result.ok:
            QMessageBox.critical(self, "保存失败", f"{path}\n\n{result.error}")
            return
        self._remember_session_dir(path)

        size = format_size(result.bytes_written)
        detail = ""
        if result.bodies_dropped:
            detail += (
                f"\n\n注意：有 {result.bodies_dropped} 条会话的 body 未保存"
                "（超出单包体积预算）。"
            )
        elif result.bodies_truncated:
            detail += f"\n\n注意：有 {result.bodies_truncated} 条会话的 body 被截断。"
        QMessageBox.information(
            self,
            "已保存",
            f"共 {result.count} 条会话 → {path}\n文件大小 {size}{detail}",
        )
        self.status_bar.showMessage(f"已保存 {result.count} 条会话 → {path}", 5000)

    def _open_session_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开会话", self._session_start_dir(), f"会话文件 (*{SESSION_EXT})"
        )
        if not path:
            return
        self._load_session_file(path)

    def _load_session_file(self, path: str, confirm_clear: bool = True) -> bool:
        """把会话文件恢复到列表；返回是否真的恢复了。"""
        if confirm_clear and self.flow_store.rowCount() > 0:
            answer = QMessageBox.question(
                self,
                "打开会话",
                f"当前列表有 {self.flow_store.rowCount()} 条会话，"
                "打开文件会先清空它们。\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        result = load_session(path)
        if not result.ok:
            QMessageBox.critical(self, "打开失败", f"{path}\n\n{result.error}")
            return False
        if not result.flows:
            QMessageBox.information(
                self, "没有可恢复的会话", f"{path}\n\n文件中没有有效会话。"
            )
            return False

        self._remember_session_dir(path)
        dropped = self._apply_loaded_session(result.flows, result.summaries)
        note = ""
        if result.skipped:
            note += f"\n跳过无法解析的行：{result.skipped} 条。"
        if dropped:
            note += f"\n超出保存条数上限，最早的 {dropped} 条未载入。"
        QMessageBox.information(
            self,
            "已恢复",
            f"共恢复 {result.count - dropped} 条会话。{note}",
        )
        self.status_bar.showMessage(f"已打开会话 {path}", 5000)
        return True

    def _apply_loaded_session(self, flows: list, summaries: list) -> int:
        """把恢复的会话灌进列表与缓存；返回因超上限被丢弃的条数。"""
        limit = max(1, int(self.settings.max_flows))
        dropped = 0
        if len(flows) > limit:
            dropped = len(flows) - limit
            # 与抓包时的淘汰方向一致：保留最新的一段
            flows = flows[-limit:]
            summaries = summaries[-limit:]

        self.detail_panel.clear()
        self.capture.load_flows(flows)
        self.flow_store.clear()
        for summary in summaries:
            self.flow_store.append(dict(summary))
        self._update_status()
        return dropped

    def _maybe_restore_autosave(self) -> None:
        """启动时询问是否恢复上次退出时的快照（可在构造时关掉）。"""
        meta = read_autosave_meta()
        if not meta:
            return
        count = int(meta.get("count") or 0)
        saved_at = str(meta.get("saved_at") or "")
        answer = QMessageBox.question(
            self,
            "恢复上次会话",
            f"检测到上次退出时保存的 {count} 条会话"
            + (f"（{saved_at}）" if saved_at else "")
            + "。\n是否恢复到列表？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            if self._load_session_file(str(session_mod.AUTOSAVE_PATH), confirm_clear=False):
                clear_autosave()
            else:
                archive_autosave()      # 加载失败也别每次启动都问
        else:
            # 用户明确不要 → 归档，避免每次启动都弹
            archive_autosave()

    def _autosave_on_exit(self) -> threading.Thread | None:
        """采集当前会话快照并**后台写盘**（返回写盘线程，调用方 join）。

        采集必须在主线程同步做（此时代理 addon 的 flow 数据还完整可读）；
        纯文件 IO 挪后台——与停代理、还原系统代理三路并行，退出提速。
        """
        if not self.settings.auto_save_session:
            return None
        flows = self._session_flows()
        if not flows:
            clear_autosave()            # 列表已空 → 别留旧快照下次误导
            return None

        def work():
            result = save_autosave(flows)
            if result.ok:
                log.info("退出快照：%s 条 → %s", result.count, result.path)
            else:
                log.warning("退出快照保存失败：%s", result.error)

        return threading.Thread(
            target=work, daemon=True, name="autosave-exit"
        )

    # ================================================================ 网络模拟

    def _on_network_changed(self) -> None:
        """面板改动 → 落盘 + 立即推给运行中的代理。"""
        throttle_cfg = self.network_panel.to_throttle()
        rules = self.network_panel.to_rules()
        self.settings.throttle = throttle_cfg
        self.settings.map_rules = rules
        save_settings(self.settings)

        # 限速：整体替换配置对象（asyncio 线程读到的永远是完整配置）
        self.throttle.set_config(throttle_cfg)

        specs, skipped = build_map_remote_specs(rules)
        # local 形态的规则走 MapLocalAddon（target 是目录，不是 host:port）
        self.maplocal.set_entries(map_local_entries(rules))
        local_count = sum(1 for r in rules if r.kind == "local" and r.enabled)
        # 「填写不完整」只数两种形态都认不出的：local 规则不是 remote 的失败
        skipped = [r for r in skipped if r.kind != "local"]
        applied_now = self.proxy.update_options(map_remote=specs)
        state = "已立即生效" if applied_now else "代理启动后生效"

        parts = []
        if throttle_cfg.enabled:
            parts.append(f"弱网 {throttle_cfg.latency_ms}ms / {throttle_cfg.rate_kbps}kbps")
        if specs:
            parts.append(f"{len(specs)} 条域名映射")
        if local_count:
            parts.append(f"{local_count} 条本地目录映射")
        message = "、".join(parts) if parts else "网络模拟已关闭"
        if skipped:
            message += f"（{len(skipped)} 条映射填写不完整，已跳过）"
        message = f"{message} · {state}"
        self.status_bar.showMessage(message, 5000)
        self.network_panel.set_status(message)
        self._update_status()

    # ================================================================ 重放

    def _replay_selected(self, edit: bool, compare: bool = False) -> None:
        flow = self._selected_flow()
        if flow is None:
            return
        if not self.proxy.running:
            QMessageBox.information(self, "提示", "请先启动代理再重放")
            return
        # 副本重放：原会话保留（start_replay 会改 is_replay/清 response，见 app/replay.py）
        copy = make_replay_copy(flow)
        if edit:
            dialog = ReplayEditDialog(copy.request, parent=self, compare=compare)
            if not dialog.exec():
                return
            apply_request_edits(copy, **dialog.result())
        if compare:
            # 先记 pending 再入队：副本 id 与新 flow id 一致，到达即关联
            self._register_pending_compare(flow.id, copy)
        if self.proxy.replay_flow(copy):
            message = f"已加入重放队列: {copy.request.method} {copy.request.pretty_url}"
            if compare:
                message += "（响应到达后自动打开对比）"
            self.status_bar.showMessage(message, 3000)

    # ---------------------------------------------------------- 重放并对比

    def _register_pending_compare(self, origin_id: str, copy) -> None:
        """登记一次待对比的重放。copy.id 就是重放后新 flow 的 id。"""
        self._pending_compare.append(
            {
                "origin_id": origin_id,
                "copy_id": copy.id,
                "url": copy.request.pretty_url,
                "at": time.time(),
            }
        )
        if not self._compare_timer.isActive():
            self._compare_timer.start()

    def _match_pending_compare(self, summary: dict) -> None:
        """新 flow 到达：是重放副本且 id 命中 pending → 弹对比框。"""
        if not self._pending_compare:
            return
        if not summary.get("is_replay"):
            return
        flow_id = summary.get("id") or ""
        for index, pending in enumerate(self._pending_compare):
            if pending["copy_id"] == flow_id:
                self._pending_compare.pop(index)
                if not self._pending_compare:
                    self._compare_timer.stop()
                self._open_compare(pending)
                return

    def _expire_pending_compare(self) -> None:
        """定时清理：上游没响应的重放不该让 pending 永久挂账。"""
        if not self._pending_compare:
            self._compare_timer.stop()
            return
        now = time.time()
        alive = [p for p in self._pending_compare if now - p["at"] <= COMPARE_TIMEOUT_S]
        expired = len(self._pending_compare) - len(alive)
        self._pending_compare = alive
        if expired:
            self.status_bar.showMessage(
                f"重放对比等待超时（{expired} 条）：未收到重放响应", 6000
            )
        if not self._pending_compare:
            self._compare_timer.stop()

    def _open_compare(self, pending: dict) -> None:
        original = self.capture.get_flow(pending["origin_id"])
        new_flow = self.capture.get_flow(pending["copy_id"])
        if original is None or new_flow is None:
            self.status_bar.showMessage(
                "对比失败：原会话或重放会话已被淘汰出缓存", 5000
            )
            return
        dialog = CompareDialog(
            original, new_flow, parent=self, wrap_default=self.settings.body_wrap
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._compare_dialogs.append(dialog)
        # 只保留最近几个，避免开太多不关慢慢攒内存
        for stale in self._compare_dialogs[:-COMPARE_DIALOG_KEEP]:
            stale.close()
        self._compare_dialogs = self._compare_dialogs[-COMPARE_DIALOG_KEEP:]

    # ================================================================ 状态

    def _update_status(self) -> None:
        total = self.flow_store.rowCount()
        shown = self.proxy_model.rowCount()
        filtering = shown != total
        text = f"共 {total} 条" + (f" · 显示 {shown} 条" if filtering else "")
        selected = len(self.traffic_table.selectionModel().selectedRows())
        if selected > 1:
            text += f" · 已选 {selected} 条"
        if self.search_bar.input.text():
            text += f" · 搜索「{self.search_bar.input.text()}」"
        if self.traffic_table.is_sorted():
            text += " · 已排序"
        if self.settings.throttle.enabled:
            text += " · 弱网模拟中"
        self.count_label.setText(text)
        if filtering:
            self.count_label.setStyleSheet(
                f"color: {theme.css('warn')}; font-weight: bold;"
            )
        else:
            self.count_label.setStyleSheet("")

        if self.proxy.running:
            self.proxy_state_label.setText(
                f"代理运行中 127.0.0.1:{self.settings.proxy_port}"
            )
            self.proxy_state_label.setStyleSheet(f"color: {theme.css('ok')};")
        else:
            self.proxy_state_label.setText("代理未启动")
            self.proxy_state_label.setStyleSheet(f"color: {theme.css('error')};")

        if self.cert_server is not None and self.cert_server.running:
            self.cert_state_label.setText(f"证书服务 {self.cert_server.url}")
        else:
            self.cert_state_label.setText("")

        self._update_capture_status()

    def _update_capture_status(self) -> None:
        """左下角抓包状态（对齐 Fiddler 左下 Capturing）：随代理与系统代理状态刷新。

        由 `_update_status` 统一调用——代理启停、主题切换（theme listener 指向
        `_update_status`）都会走到这里，颜色自动跟随主题。
        """
        if self.proxy.running:
            if self._sysproxy_enabled():
                self.capture_label.setText(
                    f"● 抓包中（系统代理 127.0.0.1:{self.settings.proxy_port}）"
                )
                self.capture_label.setStyleSheet(
                    f"color: {theme.css('ok')}; font-weight: bold;"
                )
            else:
                self.capture_label.setText("○ 抓包暂停（未接管系统代理）")
                self.capture_label.setStyleSheet(f"color: {theme.css('warn')};")
        else:
            self.capture_label.setText("○ 未抓包（代理未运行）")
            self.capture_label.setStyleSheet(f"color: {theme.css('hint')};")

    def _on_capture_clicked(self) -> None:
        """点击左下角状态切换抓包（对齐 Fiddler 点 Capturing）。

        代理运行中：切换系统代理接管（复用 sysproxy_cb 的 toggled 链路，
        接管/还原/落盘都在那里）；未运行：直接启动代理。
        """
        if self.proxy.running:
            self.sysproxy_cb.setChecked(not self.sysproxy_cb.isChecked())
        else:
            self.start_proxy()

    def _on_rules_changed(self) -> None:
        # 规则变更即时生效：mock 引擎每请求都实时读 RuleStore（见 3.3 匹配流程）
        pass

    def _show_feedback(self) -> None:
        from app.ui.feedback_dialog import FeedbackDialog

        FeedbackDialog(self).exec()

    def _show_about(self) -> None:
        from app import feedback as _fb

        QMessageBox.about(
            self,
            "关于",
            f"MiteProxy {_fb.APP_VERSION}\n\n"
            "基于 mitmproxy + PySide6 的抓包 / Mock 工具。\n"
            "支持 HTTP/HTTPS 抓包、Mock 规则、Fiddler 规则导入。",
        )

    # ================================================================ 关闭

    def closeEvent(self, event):  # noqa: N802
        # 先把窗口藏起来——用户感知层面立即退出，清理在后台并行收尾
        # （进程会多存活零点几秒，但没有任何可见窗口）
        self.hide()
        # 先同步把规则改动落盘（后台线程可能还没写完），避免最后一次编辑丢失
        try:
            self.rule_store.flush_save(timeout=5.0)
        except Exception:
            log.exception("退出时规则落盘失败")
        self._stop_cert_server()             # 进程内 HTTP 服务，停止是毫秒级
        autosaver = self._autosave_on_exit()   # 采集同步（数据须完整），写盘后台
        if autosaver is not None:
            autosaver.start()
        # 停代理与还原系统代理互不依赖（还原读的是落盘状态，不需要代理先停），
        # 加上快照写盘共三路并行：退出耗时 = 最慢一路，而不是相加。
        # 整应用重启时跳过还原：接管快照留给新实例处理（先还原再接管），
        # 这里还原会跟新实例的接管互相覆盖
        if self._restarting:
            restorer = None
        else:
            restorer = threading.Thread(
                target=self._restore_sysproxy_sync,
                daemon=True,
                name="sysproxy-restore-exit",
            )
            restorer.start()
        self.proxy.stop()
        for worker in (autosaver, restorer):
            if worker is not None:
                worker.join(10.0)    # 快照没写完就退出会丢；还原没完成会断网
        self._save_geometry()
        super().closeEvent(event)
