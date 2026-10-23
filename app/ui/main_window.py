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

from PySide6.QtCore import QEvent, QTimer, Qt, QCoreApplication, QSize
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
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from addons.breakpoint import BreakpointAddon
from addons.capture import CaptureAddon
from addons.maplocal import MapLocalAddon
from addons.mock import MockAddon
from addons.throttle import ThrottleAddon
from app.certserver import CA_PEM_PATH, CertServer, _lan_ips
from app import single_instance
from app.fix import is_fix_text
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
from app.replay import apply_request_edits, format_request_url, make_replay_copy
from app.rules import (
    CONTAINS,
    MATCH_TYPES,
    REGEX,
    Action,
    EXACT,
    Match,
    Rule,
    RuleStore,
)
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
from app.updater import CURRENT_VERSION, UpdateChecker, is_newer
from app.bodyview import BODY_PREVIEW_LIMIT as BODY_SEND_LIMIT
from app import sysproxy
from app.textutil import decode_body
from app.mcpserver import (
    DEFAULT_MCP_HOST,
    DEFAULT_MCP_PORT,
    McpServer,
    resolve_flow,
)
from app.ui.breakpoint_dialog import BreakpointDialog
from app.ui.compare_dialog import CompareDialog
from app.ui.flow_diff_dialog import FlowDiffDialog
from app.ui.detail_panel import DetailPanel
from app.ui.filter_model import FilterConfig, FlowFilterProxyModel
from app.ui.flow_store import (
    COLUMN_KEYS,
    COL_ID,
    FlowStore,
    column_labels,
    format_size,
)
from app.ui.network_panel import NetworkPanel
from app.ui.replay_dialog import ReplayEditDialog
from app.ui.rules_panel import RulesPanel
from app.ui.rule_editor import RuleEditorDialog
from app.ui.settings_dialog import SettingsDialog
from app.ui.signals import FlowBridge, UiInvoker
from app.ui.log_panel import LogPanel
from app.ui.stats_panel import StatsPanel
from app.ui.scripts_panel import ScriptsPanel
from app.ui.traffic_table import FilterBar, SearchBar, TrafficTable
from app.ui.visuals import StatusDotLabel
from app.ui.minimap import StatusMinimap
from app.ui.command_palette import CommandPalette
from app.ui import dialogs
from app.ui import theme
from app.ui import icons
from app.scripts import ScriptsManager

log = logging.getLogger(__name__)

def _ca_export_hint(path) -> str:
    """CA 证书去向说明（懒翻译：翻译器在 QApplication 创建后才装载）。"""
    return QCoreApplication.translate(
        "MainWindow",
        "CA 证书位置：{path}\n\n"
        "macOS：双击后在「钥匙串访问」中设为始终信任；\n"
        "手机：点「证书服务」按钮，用手机浏览器打开显示的地址安装。"
    ).format(path=path)

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
        # 断点：传的是活的 Settings.breakpoint，界面上开关即时生效
        self.breakpoint = BreakpointAddon(
            self.settings.breakpoint,
            on_intercept=self.bridge.emit_intercepted,
        )
        # MCP：注入取会话的回调，服务不反向依赖 Qt / capture。
        # 写操作（add_mock_rule / replay_flow / set_breakpoint）默认关，
        # 由设置的 mcp_write_enabled 门控（McpServer.write_enabled 可变）
        # 写操作回调跑在 MCP 的 HTTP 工作线程里，必须排回 Qt 主线程再执行
        # （碰工具栏按钮 / 规则表都是未定义行为）——统一包一层，别指望
        # 每个回调自己记得：加新写工具时漏包就埋雷
        self.ui_invoker = UiInvoker(self)
        self.mcp = McpServer(
            flow_provider=self._mcp_flows, port=self.settings.mcp_port,
            host=self.settings.mcp_host, flow_by_id=self._mcp_flow_by_id,
            write_enabled=self.settings.mcp_write_enabled,
            write_ops={
                name: (
                    lambda args, _fn=fn: self.ui_invoker.invoke(
                        lambda: _fn(args)
                    )
                )
                for name, fn in (
                    ("add_mock_rule", self._mcp_add_mock_rule),
                    ("replay_flow", self._mcp_replay_flow),
                    ("set_breakpoint", self._mcp_set_breakpoint),
                )
            },
        )
        self.mock = MockAddon(self.rule_store)
        self.throttle = ThrottleAddon(self.settings.throttle)
        self.maplocal = MapLocalAddon(
            map_local_entries(self.settings.map_rules)
        )
        # 用户脚本（路线图 #10）：~/.miteproxy/scripts/*.py，启用态在
        # settings.scripts。要在 _make_proxy 之前建——代理的 addon 列表
        # 里包含加载出来的脚本 addon
        self.scripts_mgr = ScriptsManager()

        self.proxy = self._make_proxy(self.settings.proxy_port)
        self.cert_server: CertServer | None = None
        # 整应用重启标记：置位后退出路径跳过系统代理还原（快照留给新实例，
        # 新实例启动时 recover_if_needed 先还原再接管，顺序才不会互相覆盖）
        self._restarting = False

        # ---- 重放并对比（DESIGN 3.6）：pending 等重放响应到达后关联弹框
        self._pending_compare: list[dict] = []
        #: 更新检测：checker 惰性创建（用到才建 QNetworkAccessManager）；
        #: _update_manual 标记本次是否用户手动触发（决定无更新/失败要不要提示）
        self._update_checker: UpdateChecker | None = None
        self._update_manual = False
        self._compare_dialogs: list[CompareDialog] = []
        #: 断点编辑器（非模态，多条会话可同时挂起 → 都留着引用，关掉时清）
        self._breakpoint_dialogs: list[BreakpointDialog] = []
        #: 会话对比对话框（非模态；开太多不关也不至于无限攒着）
        self._diff_dialogs: list[FlowDiffDialog] = []
        self._compare_timer = QTimer(self)
        self._compare_timer.setInterval(5000)
        self._compare_timer.timeout.connect(self._expire_pending_compare)

        # ---- 界面
        self._command_palette = None
        self._build_ui()
        self._build_menu()
        self._wire()

        # -- 主题：启动即应用保存的档位（默认跟随系统），
        #    并监听全局 PaletteChange（系统深浅切换 / 手动切档）广播给各面板
        theme.apply(getattr(self.settings, "theme", "system"))
        theme.add_listener(self._update_status)   # 切主题时状态栏重染色
        QApplication.instance().installEventFilter(self)

        self._apply_filter_config(self.settings.filter)
        # 栏位控件也要加载持久化配置：此前只推了代理模型，重启后过滤栏
        # 显示默认值（黑名单/空关键词/未勾选），与模型里的实际过滤条件
        # 不一致——用户一改动就会从错误的基础改起。load_config 内部
        # blockSignals，不会触发 changed 引起重复落盘。
        self.filter_bar.load_config(self.settings.filter)
        # 上次开着 MCP 就接着开（默认关，用户手动开过才记 True）
        if self.settings.mcp_enabled:
            self.mcp_btn.setChecked(True)
        self._apply_flow_limit(self.settings.max_flows)
        self._apply_list_order()
        self._restore_geometry()
        self._update_status()

        # 启动后询问是否恢复上次退出时的会话快照。
        # 用 singleShot(0) 而不是直接调用：等窗口先显示出来，模态框不会挡在空白窗口上；
        # restore_prompt=False 时不挂这个定时器，脚本环境不会有模态框阻塞。
        if self.restore_prompt:
            QTimer.singleShot(0, self._maybe_restore_autosave)

        # 启动时静默检查更新：延后几秒，避免和代理/证书初始化抢网络。
        # 只有确实发现新版本才弹窗，失败一律静默；测试环境（restore_prompt=False）
        # 不发起任何网络请求。
        if self.restore_prompt and self.settings.check_update_on_startup:
            QTimer.singleShot(3000, self._check_for_updates_silent)

    # ================================================================ 窗口状态

    def _on_theme_selected(self, mode: str) -> None:
        """外观菜单切档 / 设置对话框改主题：立即应用并落盘（下次启动保持）。"""
        if mode != self.settings.theme:
            self.settings.theme = mode
            save_settings(self.settings)
            theme.apply(mode)
        # 菜单勾选态同步（设置对话框改主题时菜单也要跟上）
        for m, act in self._theme_actions.items():
            act.setChecked(m == mode)

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
        self.minimap.setVisible(side)   # 上下布局时极小地图没意义，隐藏
        total = sum(sizes)
        length = (self.traffic_splitter.width() if side
                  else self.traffic_splitter.height())
        if total > 0 and length > 0:
            first = max(int(length * sizes[0] / total), 60)
            self.traffic_splitter.setSizes([first, max(length - first, 60)])
        self.settings.traffic_side_by_side = side
        save_settings(self.settings)

    # ===================================================== 命令面板 / 密度

    def _on_density_changed(self, _index: int) -> None:
        self._set_density(self.density_combo.currentData())

    def _set_density(self, mode: str) -> None:
        """切换流量列表行密度（舒适 / 紧凑），立即生效并落盘；同步工具栏下拉。"""
        if mode not in ("comfortable", "compact"):
            mode = "comfortable"
        self.traffic_table.set_row_density(mode)
        if self.settings.density != mode:
            self.settings.density = mode
            save_settings(self.settings)
        idx = self.density_combo.findData(mode)
        if idx >= 0 and self.density_combo.currentIndex() != idx:
            self.density_combo.setCurrentIndex(idx)

    def _set_layout(self, mode: str) -> None:
        """命令面板里切换流量页布局方向（左右 / 上下）。"""
        idx = self.layout_combo.findData(mode)
        if idx >= 0:
            self.layout_combo.setCurrentIndex(idx)  # 触发 _on_layout_changed

    def _open_command_palette(self) -> None:
        """唤起命令面板（Ctrl+K），构建随状态变化的命令列表。"""
        if self._command_palette is None:
            self._command_palette = CommandPalette(self)
        self._command_palette.set_commands(self._build_commands())
        self._command_palette.show()

    def _build_commands(self) -> list[dict]:
        """组装命令面板条目。标题用 self.tr(...) 在构建期翻译，运行期直接执行。"""
        proxy_on = bool(getattr(self.proxy, "running", False))
        cmds: list[dict] = [
            {
                "id": "proxy",
                "title": self.tr("停止代理") if proxy_on else self.tr("启动代理"),
                "keywords": "proxy start stop",
                "run": self._on_toggle_proxy,
            },
            {
                "id": "capture",
                "title": self.tr("开始 / 停止抓包"),
                "keywords": "capture",
                "run": self._on_capture_clicked,
            },
            {
                "id": "clear",
                "title": self.tr("清空流量列表"),
                "keywords": "clear",
                "run": self._on_clear,
            },
            {
                "id": "search",
                "title": self.tr("搜索会话"),
                "keywords": "search find",
                "run": lambda: self.search_btn.toggle(),
            },
            {
                "id": "replay",
                "title": self.tr("重放选中请求"),
                "keywords": "replay",
                "run": lambda: self._replay_selected(edit=False),
            },
            {
                "id": "edit_replay",
                "title": self.tr("编辑并重放选中请求"),
                "keywords": "edit replay",
                "run": lambda: self._replay_selected(edit=True),
            },
            {
                "id": "export",
                "title": self.tr("导出选中会话"),
                "keywords": "export",
                "run": self._export_selected,
            },
            {
                "id": "copy_curl",
                "title": self.tr("复制为 cURL"),
                "keywords": "curl copy",
                "run": lambda: self._copy_curl("posix"),
            },
            {
                "id": "copy_url",
                "title": self.tr("复制 URL"),
                "keywords": "url copy",
                "run": self._copy_url,
            },
            {
                "id": "breakpoint",
                "title": self.tr("切换断点调试"),
                "keywords": "breakpoint",
                "run": lambda: self._on_breakpoint_toggled(
                    not self.settings.breakpoint.enabled),
            },
            {
                "id": "mcp",
                "title": self.tr("切换 MCP 接口"),
                "keywords": "mcp",
                "run": lambda: self._on_mcp_toggled(not self.settings.mcp_enabled),
            },
            {
                "id": "sysproxy",
                "title": self.tr("切换系统代理接管"),
                "keywords": "system proxy",
                "run": lambda: self._on_sysproxy_toggled(
                    not self.settings.auto_system_proxy),
            },
            {
                "id": "cert",
                "title": self.tr("证书服务"),
                "keywords": "cert",
                "run": self._on_toggle_cert_server,
            },
            {
                "id": "settings",
                "title": self.tr("打开偏好设置"),
                "keywords": "settings",
                "run": self._open_settings,
            },
            {
                "id": "save_session",
                "title": self.tr("保存会话"),
                "keywords": "save session",
                "run": self._save_session_dialog,
            },
            {
                "id": "open_session",
                "title": self.tr("打开会话"),
                "keywords": "open session",
                "run": self._open_session_dialog,
            },
            {
                "id": "codec",
                "title": self.tr("编码转换"),
                "keywords": "codec",
                "run": lambda: self._goto_tool("codec"),
            },
            {
                "id": "json",
                "title": self.tr("JSON 格式化 / 提取"),
                "keywords": "json",
                "run": lambda: self._goto_tool("json"),
            },
            {
                "id": "compare",
                "title": self.tr("JSON 比对"),
                "keywords": "compare json",
                "run": lambda: self._goto_tool("compare"),
            },
            {
                "id": "fix",
                "title": self.tr("FIX 报文解析"),
                "keywords": "fix protocol",
                "run": lambda: self._goto_tool("fix"),
            },
            {
                "id": "update",
                "title": self.tr("检查更新"),
                "keywords": "update",
                "run": self._check_for_updates_manual,
            },
            {
                "id": "theme_light",
                "title": self.tr("主题：浅色"),
                "keywords": "theme light",
                "run": lambda: self._on_theme_selected("light"),
            },
            {
                "id": "theme_dark",
                "title": self.tr("主题：深色"),
                "keywords": "theme dark",
                "run": lambda: self._on_theme_selected("dark"),
            },
            {
                "id": "theme_system",
                "title": self.tr("主题：跟随系统"),
                "keywords": "theme system",
                "run": lambda: self._on_theme_selected("system"),
            },
            {
                "id": "lang_zh",
                "title": self.tr("语言：中文"),
                "keywords": "language zh",
                "run": lambda: self._on_language_selected("zh_CN"),
            },
            {
                "id": "lang_en",
                "title": self.tr("语言：English"),
                "keywords": "language en english",
                "run": lambda: self._on_language_selected("en"),
            },
            {
                "id": "tab_traffic",
                "title": self.tr("跳到 流量页"),
                "keywords": "tab traffic",
                "run": lambda: self.tabs.setCurrentWidget(self.traffic_page),
            },
            {
                "id": "tab_mock",
                "title": self.tr("跳到 Mock 规则页"),
                "keywords": "tab mock",
                "run": lambda: self.tabs.setCurrentWidget(self.rules_panel),
            },
            {
                "id": "tab_network",
                "title": self.tr("跳到 网络模拟页"),
                "keywords": "tab network",
                "run": lambda: self.tabs.setCurrentWidget(self.network_panel),
            },
            {
                "id": "tab_tools",
                "title": self.tr("跳到 工具页"),
                "keywords": "tab tools",
                "run": lambda: self.tabs.setCurrentWidget(self.tool_panel),
            },
            {
                "id": "tab_scripts",
                "title": self.tr("跳到 脚本页"),
                "keywords": "tab scripts",
                "run": lambda: self.tabs.setCurrentWidget(self.scripts_panel),
            },
            {
                "id": "tab_log",
                "title": self.tr("跳到 日志页"),
                "keywords": "tab log",
                "run": lambda: self.tabs.setCurrentWidget(self.log_panel),
            },
            {
                "id": "tab_stats",
                "title": self.tr("跳到 统计页"),
                "keywords": "tab stats",
                "run": lambda: self.tabs.setCurrentWidget(self.stats_panel),
            },
            {
                "id": "layout_h",
                "title": self.tr("布局：左右"),
                "keywords": "layout",
                "run": lambda: self._set_layout("h"),
            },
            {
                "id": "layout_v",
                "title": self.tr("布局：上下"),
                "keywords": "layout",
                "run": lambda: self._set_layout("v"),
            },
            {
                "id": "density_comfortable",
                "title": self.tr("行密度：舒适"),
                "keywords": "density comfortable",
                "run": lambda: self._set_density("comfortable"),
            },
            {
                "id": "density_compact",
                "title": self.tr("行密度：紧凑"),
                "keywords": "density compact",
                "run": lambda: self._set_density("compact"),
            },
        ]
        return cmds

    def _save_geometry(self) -> None:
        try:
            self.settings.window_geometry = bytes(self.saveGeometry())
            self.settings.splitter_state = bytes(self.traffic_splitter.saveState())
            save_settings(self.settings)
        except Exception:
            log.warning("窗口几何保存失败", exc_info=True)

    # ============================================================ 导航与图标

    def _add_tab(self, widget: QWidget, label: str, icon_name: str) -> None:
        """往 tabs 加一页，并登记图标名（切主题时统一重取色）。"""
        self.tabs.addTab(widget, icons.icon(icon_name), label)
        self._tab_icon_names.append(icon_name)

    def _refresh_icons(self) -> None:
        """主题切换后重取所有图标颜色（图标是内联 SVG，按前景色渲染）。

        本方法挂在 _update_status（每条流量到达都会调）上，所以必须按
        「前景色是否真的变了」短路——否则每次状态刷新都清缓存重渲染 12 个 SVG。
        """
        if not hasattr(self, "tabs") or self.tabs is None:
            return
        color = theme.css("fg")
        if color == getattr(self, "_icons_color", None):
            return
        self._icons_color = color
        icons.invalidate()
        for i, name in enumerate(self._tab_icon_names):
            self.tabs.setTabIcon(i, icons.icon(name))
        for btn, name in (
            (self.clear_btn, "trash"),
            (self.search_btn, "search"),
            (self.proxy_btn, "power"),
            (self.breakpoint_btn, "breakpoint"),
            (self.mcp_btn, "mcp"),
        ):
            if btn is not None:
                btn.setIcon(icons.icon(name))

    # ================================================================ UI 构建

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # -- 工具栏（排列：列表操作 | 抓包选项 | 代理控制 | 视图 | 低频功能）
        toolbar_row = QHBoxLayout()

        self.clear_btn = QPushButton(self.tr("清除列表"))
        toolbar_row.addWidget(self.clear_btn)

        # 搜索是高频动作，给个常驻入口——之前只有 Ctrl+F 才唤得出搜索栏，
        # 不知道快捷键的人根本发现不了这个功能。
        self.search_btn = QPushButton(self.tr("搜索"))
        self.search_btn.setCheckable(True)
        self.search_btn.setToolTip(
            self.tr("搜索会话（URL / Header / Body）  Ctrl+F")
        )
        self.search_btn.toggled.connect(self._on_search_toggled)
        toolbar_row.addWidget(self.search_btn)

        toolbar_row.addSpacing(12)
        toolbar_row.addWidget(QLabel(self.tr("保存数量:")))
        self.limit_combo = QComboBox()
        for n in FLOW_LIMIT_CHOICES:
            self.limit_combo.addItem(self.tr('{0} 条').format(n), n)
        self.limit_combo.setToolTip(
            self.tr("流量列表最多保留的会话数，超出后从最旧一条开始丢弃（上限 5000）")
        )
        idx = self.limit_combo.findData(self.settings.max_flows)
        self.limit_combo.setCurrentIndex(max(idx, 0))
        toolbar_row.addWidget(self.limit_combo)

        # URL 关键字高亮（v1.15）：实时生效，对新到的流量也生效——
        # 与「搜索」（只针对当时的历史请求）互补
        toolbar_row.addSpacing(12)
        toolbar_row.addWidget(QLabel(self.tr("高亮:")))
        self.highlight_edit = QLineEdit()
        self.highlight_edit.setPlaceholderText(self.tr("URL 关键字"))
        self.highlight_edit.setClearButtonEnabled(True)
        self.highlight_edit.setFixedWidth(150)
        self.highlight_edit.setToolTip(
            self.tr("URL 包含该关键字的请求整行黄色高亮。\n"
            "实时生效：正在显示的与之后新到的流量都会高亮；清空即关闭。")
        )
        toolbar_row.addWidget(self.highlight_edit)

        toolbar_row.addSpacing(12)
        self.auto_scroll_cb = QCheckBox(self.tr("自动滚动"))
        self.auto_scroll_cb.setChecked(self.settings.auto_scroll)
        self.auto_scroll_cb.setToolTip(
            self.tr("新会话到达时自动滚到最新一条。\n"
            "你手动翻到别处时不会来抢滚动条——只有停在最新端才跟着走。")
        )
        toolbar_row.addWidget(self.auto_scroll_cb)

        self.sysproxy_cb = QCheckBox(self.tr("设为系统代理"))
        self.sysproxy_cb.setChecked(self.settings.auto_system_proxy)
        self.sysproxy_cb.setToolTip(
            self.tr("启动代理时自动把系统 HTTP/HTTPS 代理指向本应用，停止或退出时自动还原\n"
            "（对齐 Fiddler「Act as System Proxy」）。\n"
            "macOS 首次接管会请求一次管理员授权；不想自动改系统设置就取消勾选。")
        )
        self.sysproxy_cb.toggled.connect(self._on_sysproxy_toggled)
        toolbar_row.addWidget(self.sysproxy_cb)

        toolbar_row.addSpacing(12)
        self.proxy_btn = QPushButton(self.tr("启动代理"))
        self.proxy_btn.setCheckable(True)
        self._refresh_proxy_btn_tooltip()
        toolbar_row.addWidget(self.proxy_btn)

        toolbar_row.addSpacing(12)
        toolbar_row.addWidget(QLabel(self.tr("顺序:")))
        self.order_combo = QComboBox()
        self.order_combo.addItem(self.tr("到达顺序（新在底部）"), False)
        self.order_combo.addItem(self.tr("新的在顶部"), True)
        self.order_combo.setToolTip(self.tr("倒序 = 按到达序号降序，最新的会话排在最上面"))
        self.order_combo.setCurrentIndex(1 if self.settings.newest_first else 0)
        toolbar_row.addWidget(self.order_combo)

        toolbar_row.addWidget(QLabel(self.tr("布局:")))
        self.layout_combo = QComboBox()
        self.layout_combo.addItem(self.tr("左右布局"), "h")
        self.layout_combo.addItem(self.tr("上下布局"), "v")
        self.layout_combo.setToolTip(
            self.tr("流量列表与详情区的排布方向。左右 = Fiddler 风格（列表在左、body 在右），\n"
            "上下 = 列表在上、body 在下。选择会记住，下次启动保持。")
        )
        self.layout_combo.setCurrentIndex(
            0 if getattr(self.settings, "traffic_side_by_side", True) else 1
        )
        self.layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        toolbar_row.addWidget(self.layout_combo)

        # 行密度：舒适 / 紧凑（高频视觉偏好，给个常驻入口）
        toolbar_row.addSpacing(12)
        toolbar_row.addWidget(QLabel(self.tr("密度:")))
        self.density_combo = QComboBox()
        self.density_combo.addItem(self.tr("舒适"), "comfortable")
        self.density_combo.addItem(self.tr("紧凑"), "compact")
        self.density_combo.setToolTip(
            self.tr("流量列表行密度：舒适更宽松，紧凑一屏容纳更多行（重启保持）")
        )
        idx = self.density_combo.findData(self.settings.density)
        self.density_combo.setCurrentIndex(max(idx, 0))
        self.density_combo.currentIndexChanged.connect(self._on_density_changed)
        toolbar_row.addWidget(self.density_combo)

        # 证书功能不常用，放到工具栏最后面（DESIGN：低频操作靠右）
        # （证书端口同代理端口，只在「设置 → 偏好设置 → 代理」里配置）
        toolbar_row.addSpacing(12)
        # 勾态仅表示「服务运行中」（不是启停开关）：点击始终打开二维码弹窗，
        # 停止服务走弹窗里的显式按钮——避免「点了没反应其实是静默停止」
        self.cert_btn = QPushButton(self.tr("证书服务"))
        self.cert_btn.setCheckable(True)
        self.cert_btn.setToolTip(self.tr("启动局域网证书下载服务（手机装 CA 用）"))
        toolbar_row.addWidget(self.cert_btn)

        self.export_ca_btn = QPushButton(self.tr("导出 CA 证书"))
        toolbar_row.addWidget(self.export_ca_btn)

        toolbar_row.addSpacing(12)
        self.breakpoint_btn = QPushButton(self.tr("断点"))
        self.breakpoint_btn.setCheckable(True)
        self.breakpoint_btn.setChecked(self.settings.breakpoint.enabled)
        self.breakpoint_btn.setToolTip(
            self.tr("断点调试：命中的会话会挂起，改完再放行（请求前 / 响应前在设置里配）")
        )
        self.breakpoint_btn.toggled.connect(self._on_breakpoint_toggled)
        toolbar_row.addWidget(self.breakpoint_btn)

        toolbar_row.addSpacing(12)
        self.mcp_btn = QPushButton(self.tr("MCP"))
        self.mcp_btn.setCheckable(True)
        self.mcp_btn.setToolTip(
            self.tr("MCP 接口：把最近抓包暴露给 AI 客户端（默认关）。\n"
                    "监听地址与端口在「设置 → 流量列表 → MCP 接口」里改：\n"
                    "默认 127.0.0.1 仅本机可连；改成 0.0.0.0 或网卡 IP 后"
                    "局域网内的设备也能读到完整抓包。")
        )
        self.mcp_btn.toggled.connect(self._on_mcp_toggled)
        toolbar_row.addWidget(self.mcp_btn)

        # 高频动作加图标（低频动作保持纯文字，避免工具栏过宽）；
        # 图标跟随深浅主题色，切主题时由 _refresh_icons 重取色
        self.clear_btn.setIcon(icons.icon("trash"))
        self.search_btn.setIcon(icons.icon("search"))
        self.proxy_btn.setIcon(icons.icon("power"))
        self.breakpoint_btn.setIcon(icons.icon("breakpoint"))
        self.mcp_btn.setIcon(icons.icon("mcp"))

        toolbar_row.addStretch(1)
        root.addLayout(toolbar_row)

        # -- 过滤栏 / 搜索栏
        self.filter_bar = FilterBar()
        root.addWidget(self.filter_bar)

        self.search_bar = SearchBar()
        self.search_bar.hide()
        root.addWidget(self.search_bar)

        # -- 标签页：流量 / Mock 规则（左侧 rail 导航：图标 + 文字，West 位置）
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West)
        self.tabs.setIconSize(QSize(18, 18))
        self._tab_icon_names: list[str] = []
        root.addWidget(self.tabs, stretch=1)

        # 流量页
        traffic_page = QWidget()
        self.traffic_page = traffic_page
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
        self.traffic_table.set_row_density(self.settings.density)
        self.proxy_model = FlowFilterProxyModel()
        self.proxy_model.setSourceModel(self.flow_store)
        self.proxy_model.flow_lookup = self.capture.get_flow
        self.traffic_table.setModel(self.proxy_model)
        # 列显隐必须在 setModel 之后应用：QHeaderView 换模型时会重置
        # 按列配置（含隐藏态）。默认隐藏内容类型/开始时刻/备注三个可选列
        self._apply_hidden_columns()
        self.detail_panel = DetailPanel(wrap_default=self.settings.body_wrap)
        # 水平方向 Ignored：详情面板不向 splitter 申报宽度意图。
        # 否则切换请求时（长 URL 摘要、表单列宽、图片页等 sizeHint 变化）会
        # 触发 splitter 重新分配，body 区域左右漂移；显式最小宽度防拖穿。
        self.detail_panel.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.detail_panel.setMinimumWidth(200)
        # 状态码 minimap：和表格包在同一个左栏容器里、紧贴表格右侧。
        # 不能塞进 splitter（_on_layout_changed 的 sizes 逻辑只认两项），
        # 也不能放 splitter 外面（会被挤到详情面板右边）。
        self.minimap = StatusMinimap(self.traffic_table, self.proxy_model, traffic_page)
        if not side_by_side:
            self.minimap.setVisible(False)
        self.proxy_model.rowsInserted.connect(self.minimap.update)
        self.proxy_model.rowsRemoved.connect(self.minimap.update)
        self.proxy_model.modelReset.connect(self.minimap.update)
        self.proxy_model.dataChanged.connect(self.minimap.update)
        self.traffic_table.verticalScrollBar().valueChanged.connect(self.minimap.update)

        table_pane = QWidget()
        table_lay = QHBoxLayout(table_pane)
        table_lay.setContentsMargins(0, 0, 0, 0)
        table_lay.setSpacing(0)
        table_lay.addWidget(self.traffic_table, stretch=1)
        table_lay.addWidget(self.minimap)
        self.traffic_splitter.addWidget(table_pane)
        self.traffic_splitter.addWidget(self.detail_panel)
        self.traffic_splitter.setSizes([420, 300])
        self.traffic_splitter.setChildrenCollapsible(False)
        traffic_layout.addWidget(self.traffic_splitter)
        self._add_tab(traffic_page, self.tr("流量"), "traffic")

        # Mock 规则页
        self.rules_panel = RulesPanel(self.rule_store)
        self._add_tab(self.rules_panel, self.tr("Mock 规则"), "mock")

        # 网络模拟页（弱网限速 + 域名映射）
        self.network_panel = NetworkPanel()
        self.network_panel.load_config(self.settings.throttle, self.settings.map_rules)
        self._add_tab(self.network_panel, self.tr("网络模拟"), "network")

        # 工具页（编码转换 + JSON 格式化/JSONPath，对齐 Fiddler TextWizard + json.cn）
        self.tool_panel = ToolPanel()
        self._add_tab(self.tool_panel, self.tr("工具"), "tools")

        # 脚本页（用户 Python 插件，挂 mitmproxy flow 钩子）
        self.scripts_panel = ScriptsPanel(
            self.scripts_mgr, enabled=self.settings.scripts
        )
        self._add_tab(self.scripts_panel, self.tr("脚本"), "scripts")

        # 日志页：实时显示运行日志（级别筛选 / 清空 / 打开磁盘日志文件）
        self.log_panel = LogPanel()
        self._add_tab(self.log_panel, self.tr("日志"), "log")

        # 统计页（对齐 Fiddler Statistics）：总览 + 域名/状态码/方法 + 慢请求
        # + 时间直方图。聚合逻辑在 app/stats.py，与 MCP 的 get_stats 共用
        self.stats_panel = StatsPanel(flow_provider=self._stats_flows)
        self._add_tab(self.stats_panel, self.tr("统计"), "stats")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        # 统计防抖：新流量可能成批到达（页面加载时一串请求），没必要每条都
        # 全量聚合；500ms 内的多条变化合并成一次重算
        self._stats_timer = QTimer(self)
        self._stats_timer.setSingleShot(True)
        self._stats_timer.setInterval(500)
        self._stats_timer.timeout.connect(self._refresh_stats)

        # -- 状态栏
        self.status_bar = self.statusBar()
        self.count_label = QLabel("")
        self.proxy_state_label = QLabel(self.tr("代理未启动"))
        self.cert_state_label = QLabel("")
        for w in (self.count_label, self.proxy_state_label, self.cert_state_label):
            self.status_bar.addPermanentWidget(w)
        # Fiddler 式左下角抓包状态：绿点=接管系统代理抓包中，点击切换
        self.capture_label = StatusDotLabel()
        self.capture_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.capture_label.setToolTip(
            self.tr("点击开始/停止抓包（接管或还原系统代理，与工具栏「设为系统代理」联动）")
        )
        self.capture_label.mousePressEvent = lambda _ev: self._on_capture_clicked()
        self.status_bar.insertWidget(0, self.capture_label)

        # Ctrl+F 归「工具 → 搜索会话」的 QAction 管（避免和 QShortcut 重复绑定
        # 触发 Qt 的 Ambiguous shortcut 警告）
        from PySide6.QtGui import QShortcut

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
        # Ctrl+X 清空流量列表（仅在请求列表获得焦点时生效，避免误删其它输入框文本）
        QShortcut(QKeySequence("Ctrl+X"), self.traffic_table, self._on_clear)
        # Del 删除选中会话（同样只在列表有焦点时生效）
        QShortcut(QKeySequence("Del"), self.traffic_table, self._delete_selected_flows)
        # Ctrl+K 命令面板（VS Code 风格的可搜索快捷动作启动器）
        QShortcut(QKeySequence("Ctrl+K"), self, self._open_command_palette)

        # 流量表格右键菜单
        self.traffic_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.traffic_table.customContextMenuRequested.connect(self._on_table_context_menu)
        # 表头右键：列显隐菜单（与「外观 → 流量列表列…」同一个构建函数）
        self.traffic_table.column_menu_requested.connect(self._on_column_menu_requested)
        # 键盘快捷键：R 重放、E 编辑后重放（选中某条请求时，见 traffic_table.py）
        self.traffic_table.replay_requested.connect(
            lambda: self._replay_selected(edit=False)
        )
        self.traffic_table.edit_replay_requested.connect(
            lambda: self._replay_selected(edit=True)
        )

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(self.tr("文件"))
        save_action = QAction(self.tr("保存会话…"), self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._save_session_dialog)
        file_menu.addAction(save_action)

        open_action = QAction(self.tr("打开会话…"), self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._open_session_dialog)
        file_menu.addAction(open_action)

        file_menu.addSeparator()
        clear_action = QAction(self.tr("清除列表"), self)
        clear_action.triggered.connect(self._on_clear)
        file_menu.addAction(clear_action)

        file_menu.addSeparator()
        auto_action = QAction(self.tr("退出时自动保存会话"), self)
        auto_action.setCheckable(True)
        auto_action.setChecked(self.settings.auto_save_session)
        auto_action.toggled.connect(self._on_toggle_autosave)
        file_menu.addAction(auto_action)
        self.autosave_action = auto_action

        file_menu.addSeparator()
        quit_action = QAction(self.tr("退出"), self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        tool_menu = self.menuBar().addMenu(self.tr("工具"))
        # 搜索会话：Ctrl+F 之外的显式入口（菜单栏 + 工具栏按钮各一个）
        search_action = QAction(self.tr("搜索会话…"), self)
        search_action.setShortcut(QKeySequence("Ctrl+F"))
        search_action.triggered.connect(self._on_find_shortcut)
        tool_menu.addAction(search_action)
        tool_menu.addSeparator()

        codec_action = QAction(self.tr("编码转换…"), self)
        codec_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        codec_action.triggered.connect(lambda: self._goto_tool("codec"))
        tool_menu.addAction(codec_action)

        json_action = QAction(self.tr("JSON 格式化 / 提取…"), self)
        json_action.setShortcut(QKeySequence("Ctrl+Shift+J"))
        json_action.triggered.connect(lambda: self._goto_tool("json"))
        tool_menu.addAction(json_action)

        compare_action = QAction(self.tr("JSON 比对…"), self)
        compare_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        compare_action.triggered.connect(lambda: self._goto_tool("compare"))
        tool_menu.addAction(compare_action)

        fix_action = QAction(self.tr("FIX 报文解析…"), self)
        fix_action.setShortcut(QKeySequence("Ctrl+Shift+F"))
        fix_action.triggered.connect(lambda: self._goto_tool("fix"))
        tool_menu.addAction(fix_action)

        # -- 设置：偏好设置对话框（收拢工具栏/菜单里散落的可配置项）
        settings_menu = self.menuBar().addMenu(self.tr("设置"))
        settings_action = QAction(self.tr("偏好设置…"), self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._open_settings)
        settings_menu.addAction(settings_action)

        # -- 外观：跟随系统 / 浅色 / 深色（默认跟随系统，选择随 settings 持久化）
        view_menu = self.menuBar().addMenu(self.tr("外观"))
        columns_action = QAction(self.tr("流量列表列…"), self)
        columns_action.setToolTip(
            self.tr("勾选/取消要显示的列（内容类型、开始时刻、备注默认隐藏）")
        )
        columns_action.triggered.connect(self._show_column_menu_from_menu_bar)
        view_menu.addAction(columns_action)
        view_menu.addSeparator()
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._theme_actions: dict[str, QAction] = {}
        for mode, label in (
            ("system", self.tr("跟随系统")),
            ("light", self.tr("浅色模式")),
            ("dark", self.tr("深色模式")),
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

        # -- 语言：中文 / English（切换后重启生效）
        lang_menu = self.menuBar().addMenu(self.tr("语言"))
        self._lang_group = QActionGroup(self)
        self._lang_group.setExclusive(True)
        self._lang_actions: dict[str, QAction] = {}
        from app.i18n import available_languages

        for code, label in available_languages().items():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(self.settings.language == code)
            action.triggered.connect(
                lambda _=False, c=code: self._on_language_selected(c)
            )
            self._lang_group.addAction(action)
            lang_menu.addAction(action)
            self._lang_actions[code] = action

        menu = self.menuBar().addMenu(self.tr("帮助"))
        update_action = QAction(self.tr("检查更新…"), self)
        update_action.triggered.connect(self._check_for_updates_manual)
        menu.addAction(update_action)
        feedback_action = QAction(self.tr("意见反馈…"), self)
        feedback_action.triggered.connect(self._show_feedback)
        menu.addAction(feedback_action)
        about = QAction(self.tr("关于"), self)
        about.triggered.connect(self._show_about)
        menu.addAction(about)

    def _on_language_selected(self, code: str) -> None:
        """语言切换：持久化到设置并提示重启生效（翻译器在下次启动时装载）。"""
        # 同步语言菜单项的勾选态（QActionGroup 的 radio 行为）
        for c, act in self._lang_actions.items():
            act.setChecked(c == code)
        if code == self.settings.language:
            return
        self.settings.language = code
        save_settings(self.settings)
        dialogs.information(
            self,
            self.tr("语言已切换"),
            self.tr("语言将在重启 MiteProxy 后生效。"),
        )

    def _open_settings(self) -> None:
        """打开偏好设置对话框；确认后逐项应用并同步工具栏/菜单。"""
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self._apply_settings(dlg.values())

    def _apply_settings(self, values: dict) -> None:
        """把设置对话框的值逐项落到 settings，并同步工具栏/菜单控件。

        同步一律走既有控件与处理器（setChecked / setCurrentIndex /
        _apply_*），不绕开界面直接改 settings——保持「单一写入口 +
        界面即真相」，工具栏与设置页永远指向同一份配置。
        """
        # -- 端口：唯一入口是设置对话框（工具栏不再放端口框），复用同一
        #    应用通路（含运行中重启询问 / 证书服务立即重启）
        proxy_port = int(values["proxy_port"])
        if proxy_port != self.settings.proxy_port:
            self._apply_proxy_port(proxy_port)
        cert_port = int(values["cert_port"])
        if cert_port != self.settings.cert_port:
            self._apply_cert_port(cert_port)

        # -- 有对应控件的项：setChecked/setCurrentIndex 的信号即保存通路
        self.sysproxy_cb.setChecked(bool(values["auto_system_proxy"]))
        max_flows = int(values["max_flows"])
        self._apply_flow_limit(max_flows)      # 只改内存与列表，不落盘
        save_settings(self.settings)           # 统一在这里落一次盘
        idx = self.limit_combo.findData(max_flows)
        if idx >= 0:
            self.limit_combo.setCurrentIndex(idx)
        self.auto_scroll_cb.setChecked(bool(values["auto_scroll"]))
        self.order_combo.setCurrentIndex(1 if values["newest_first"] else 0)
        # 详情页换行默认值（内部会同步各 Body 面板的「换行」勾选框）
        self.detail_panel.set_wrap_default(bool(values["body_wrap"]))
        self._on_theme_selected(values["theme"])
        self._on_language_selected(values["language"])
        self.autosave_action.setChecked(bool(values["auto_save_session"]))
        check_update = bool(values["check_update_on_startup"])
        if check_update != self.settings.check_update_on_startup:
            self.settings.check_update_on_startup = check_update
            save_settings(self.settings)
        # 断点：只回写阶段与命中范围（enabled 归工具栏按钮，避免互相打架）
        bp = values.get("breakpoint") or {}
        self.settings.breakpoint.on_request = bool(bp.get("on_request", True))
        self.settings.breakpoint.on_response = bool(bp.get("on_response", False))
        self.settings.breakpoint.url_keywords = list(bp.get("url_keywords") or [])
        save_settings(self.settings)
        # MCP：监听地址 / 端口（服务开着就重启到新地址，否则只更新配置）
        mcp_host = str(values.get("mcp_host") or DEFAULT_MCP_HOST).strip()
        mcp_host = mcp_host or DEFAULT_MCP_HOST
        mcp_port = int(values.get("mcp_port") or DEFAULT_MCP_PORT)
        if mcp_host != self.settings.mcp_host or mcp_port != self.settings.mcp_port:
            was_running = self.mcp.running
            if was_running:
                self.mcp.stop()
            self.settings.mcp_host = mcp_host
            self.settings.mcp_port = mcp_port
            save_settings(self.settings)
            if was_running and not self._start_mcp():
                # 新地址起不来（比如填了个本机没有的 IP）：别留个"开着"的假状态
                self.settings.mcp_enabled = False
                save_settings(self.settings)
        # MCP 写操作开关：只改门控（McpServer.write_enabled 可变），
        # 不需要重启服务——客户端重新 tools/list 即可看到变化
        mcp_write = bool(values.get("mcp_write_enabled", False))
        if mcp_write != self.settings.mcp_write_enabled:
            self.settings.mcp_write_enabled = mcp_write
            self.mcp.write_enabled = mcp_write
            save_settings(self.settings)

    def _goto_tool(self, page: str = "codec") -> None:
        """切到工具页的指定子页并把焦点给输入框。"""
        self.tabs.setCurrentWidget(self.tool_panel)
        self.tool_panel.show_page(page)
        if page == "json":
            editor = self.tool_panel.json_panel.input_edit
        elif page == "compare":
            editor = self.tool_panel.compare_panel.left_edit
        elif page == "fix":
            editor = self.tool_panel.fix_panel.input_edit
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
        self.bridge.flow_intercepted.connect(self._on_flow_intercepted)
        self.bridge.proxy_state_changed.connect(self._on_proxy_state_changed)
        self.filter_bar.changed.connect(self._on_filter_changed)
        self.filter_bar.preset_menu_about_to_show.connect(self._rebuild_preset_menu)
        self.scripts_panel.scripts_changed.connect(self._on_scripts_changed)
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
        # 双击流量列表某条请求 → 弹出上下结构的请求/响应详情（Fiddler 风格）
        self.traffic_table.doubleClicked.connect(self._on_flow_double_clicked)
        # 排序状态变化 → 状态栏显示「已排序」
        self.traffic_table.horizontalHeader().sortIndicatorChanged.connect(
            lambda *_: self._update_status()
        )

        self.network_panel.changed.connect(self._on_network_changed)
        # 统计页双击慢请求 → 跳到流量列表对应行
        self.stats_panel.flow_activated.connect(self._reveal_flow)

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
            # 顺序很重要（两个约束）：
            # ① throttle 必须排在会"造响应"的 mock / map-local 之后，这样在它的
            #    request 钩子里 flow.response 才已被注入，弱网延迟才能作用到
            #    mock 出来的接口上；
            # ② capture 必须排在 throttle 之后——capture 的 response 钩子总结
            #    耗时时要读 throttle 写入 metadata 的实际延迟（计入耗时列），
            #    排在前面就读不到，弱网延迟也体现不到耗时上；
            # ③ breakpoint 排在最前：它的钩子只"打标记"（flow.intercept），
            #    真正的等待由内核在钩子跑完后 await wait_for_resume 完成，
            #    所以放前面能让 mock / throttle 等照常先跑完，再统一挂起；
            # ④ 用户脚本排在最后：它们看到的是经过前面所有 addon 之后的
            #    最终 flow（含 mock / 弱网 / 捕获），写起来最符合直觉。
            #    单个脚本的加载错误在 build 时就拦掉，不影响别的 addon。
            addons=[self.breakpoint, self.mock, self.maplocal,
                    self.throttle, self.capture, *self._build_script_addons()],
            options={"map_remote": specs},
            # 代理线程的真实生死：DumpMaster 构造失败（证书损坏等）或
            # run() 中途异常时，靠它把 UI 从"运行中"拉回来——否则用户
            # 以为在抓包，实际一条都没记。回调在 asyncio 线程执行，
            # 这里只 emit 信号（跨线程 emit 由 Qt 排到主线程）
            on_state_change=lambda running, msg: (
                self.bridge.proxy_state_changed.emit(bool(running), str(msg or ""))
            ),
        )

    def _build_script_addons(self) -> list:
        """加载启用的用户脚本 → addon 列表（启动 / 热替换共用）。

        加载失败的脚本记进 ``scripts_mgr.load_errors``（脚本页状态列
        可见），不抛出——一个坏脚本不该让代理起不来。
        """
        try:
            return self.scripts_mgr.build_addons(self.settings.scripts)
        except Exception:
            log.exception("加载用户脚本失败")
            return []

    def _on_toggle_proxy(self) -> None:
        if self.proxy.running:
            self.stop_proxy()
        else:
            # verify=True：启动后 700ms 回查线程是否还活着。手动启动也要
            # 校验——按钮态在失败时并不会"自明"（DumpMaster 构造失败发生在
            # 子线程，UI 已经乐观置成"停止代理"了），不校验就是零反馈
            self.start_proxy(verify=True)
            
    def start_proxy(self, verify: bool = False) -> bool:
        """启动代理（幂等）。verify=True 时异步校验是否真正监听成功。

        入口 main() 用 verify=True：若端口被占用，代理线程会立刻退出，
        由 _verify_proxy_started 收尾复位按钮并提示，避免出现
        "界面显示运行中、实际没有代理" 的假象。
        请求端口被占用时 ProxyService 会自动顺延到下一个可用端口——
        实际端口在这里同步回设置/端口框，系统代理也指向真实端口。
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
        try:
            self.proxy.start()
        except OSError:
            # 从请求端口起连续 N 个端口都不可用（极端情况）
            log.warning("代理启动失败：无可用端口", exc_info=True)
            self._proxy_start_failed()
            return False
        # 端口被占用时自动顺延：把实际端口同步回设置与界面，
        # 系统代理接管读 self.proxy.port（已是真实端口），无需额外处理
        requested = self.settings.proxy_port
        actual = self.proxy.port
        if actual != requested:
            self.settings.proxy_port = actual
            save_settings(self.settings)
            # MockAddon 的重定向死循环校验按真实端口判断
            self.mock.proxy_addr = ("127.0.0.1", actual)
            self.status_bar.showMessage(
                self.tr('端口 {0} 被占用，代理已自动改用 {1}').format(requested, actual), 6000
            )
        self.proxy_btn.setText(self.tr("停止代理"))
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
        self.proxy_btn.setText(self.tr("启动代理"))
        self.proxy_btn.setChecked(False)
        self._update_status()
        if not self._restarting:        # 整应用重启时快照留给新实例处理
            self._restore_sysproxy_async()

    # ------------------------------------------------------------ 系统代理接管

    def _sysproxy_enabled(self) -> bool:
        return self.sysproxy_cb.isChecked()

    def _sysproxy_worker(self, name: str, fn) -> None:
        """后台跑系统代理操作（networksetup 逐服务执行，可能几秒，别卡 UI）。

        异常必须兜住并回报：networksetup 可能被 TCC/沙箱拦截，状态文件
        也可能写不进。不兜的话线程静默死亡、``sysproxy_done`` 永不 emit，
        用户看不到任何结果——更糟的是接管**已经改了系统代理**、状态文件
        却没落盘，之后退出时因找不到快照而还原不掉，把用户的系统代理
        永久留在死端口上。
        """
        def work():
            try:
                ok, msg = fn()
            except Exception as e:      # noqa: BLE001 - 兜住后转成状态栏提示
                log.exception("系统代理操作异常")
                ok, msg = False, f"{type(e).__name__}: {e}"
            self.bridge.sysproxy_done.emit(ok, msg)

        threading.Thread(target=work, daemon=True, name=name).start()

    def _takeover_sysproxy_async(self) -> None:
        if not self._sysproxy_enabled():
            return

        def do():
            with self._sysproxy_lock:
                return sysproxy.takeover(self.proxy.port)

        self._sysproxy_worker("sysproxy-takeover", do)

    def _restore_sysproxy_async(self) -> None:
        port = self.proxy.port

        def do():
            with self._sysproxy_lock:
                return sysproxy.restore(port=port)

        # 无接管记录时不必打扰用户（启动/停止都会走这里，绝大多数是 no-op）
        noop_msg = QCoreApplication.translate("MainWindow", "无接管记录")

        def work():
            try:
                ok, msg = do()
            except Exception as e:      # noqa: BLE001
                log.exception("还原系统代理异常")
                self.bridge.sysproxy_done.emit(False, f"{type(e).__name__}: {e}")
                return
            if msg != noop_msg:
                self.bridge.sysproxy_done.emit(ok, msg)

        threading.Thread(target=work, daemon=True, name="sysproxy-restore").start()

    def _restore_sysproxy_sync(self) -> None:
        """退出路径用同步还原：必须还原完再关窗口。"""
        try:
            with self._sysproxy_lock:
                ok, msg = sysproxy.restore(port=self.proxy.port)
        except Exception:               # noqa: BLE001 - 退出路径不能因它崩
            log.exception("退出时还原系统代理失败")
            return
        # 这里跑在退出线程，self.tr() 是 QWidget 的，跨线程调不安全
        if ok and msg != QCoreApplication.translate("MainWindow", "无接管记录"):
            log.info("系统代理已还原: %s", msg)

    def _on_sysproxy_done(self, ok: bool, msg: str) -> None:
        if ok:
            self.status_bar.showMessage(self.tr('{0}（停止代理或退出时自动还原）').format(msg), 6000)
            return
        self.status_bar.showMessage(
            self.tr('系统代理接管失败：{0}（可手动设置代理 127.0.0.1:{1}）').format(msg, self.proxy.port),
            8000,
        )
        # macOS 最常见失败原因是缺管理员权限 → 给一次提权重试（弹密码框）
        if (platform.system() == "darwin"
                and not getattr(self, "_sysproxy_elevate_asked", False)):
            self._sysproxy_elevate_asked = True  # 每次会话只问一次，别烦人
            answer = dialogs.question(
                self,
                self.tr("系统代理接管失败"),
                self.tr('{0}\n\n用管理员权限重试？（会弹出密码确认框，与 Charles 行为一致）').format(msg),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes and self.proxy.running:
                threading.Thread(
                    target=lambda: self._sysproxy_elevated_takeover(),
                    daemon=True,
                    name="sysproxy-takeover-elevated",
                ).start()

    def _sysproxy_elevated_takeover(self) -> None:
        """提权重试（弹 macOS 密码框）；失败也走 sysproxy_done 回报。"""
        try:
            with self._sysproxy_lock:
                ok, msg = sysproxy.takeover(self.proxy.port, elevate=True)
        except Exception as e:          # noqa: BLE001
            log.exception("提权接管系统代理异常")
            ok, msg = False, f"{type(e).__name__}: {e}"
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

    def _on_proxy_state_changed(self, running: bool, message: str) -> None:
        """代理线程的真实生死（asyncio 线程 emit，Qt 排到主线程执行）。

        False 且 UI 还以为在跑 → 这是最坏的失败模式：按钮停在"停止代理"、
        状态栏显示运行中，但一条流量都不会来。必须复位 + 明确告知。
        """
        if running:
            return
        if not self.proxy_btn.isChecked():
            return                      # 已经在停止态（用户主动停的），no-op
        log.error("代理线程已退出，UI 状态复位: %s", message or "（无附加信息）")
        self.proxy_btn.setText(self.tr("启动代理"))
        self.proxy_btn.setChecked(False)
        self._update_status()
        # 可能刚接管完系统代理就挂了，补还原，否则系统代理残留在死端口上
        self._restore_sysproxy_async()
        dialogs.critical(
            self,
            self.tr("代理已停止"),
            self.tr(
                "抓包进程意外退出，可能原因：\n"
                "- 端口被其他程序占用\n"
                "- CA 证书损坏或权限不足（可到「设置 → 证书」重建）\n"
                "- mitmproxy 内部错误\n\n{0}"
            ).format(message or self.tr("（无详细信息，见应用日志）")),
        )

    def _verify_proxy_started(self) -> None:
        if not self.proxy_btn.isChecked():
            return                    # 用户已手动停掉，不打扰
        if self.proxy.running:
            return                    # 正常监听中
        # 线程已退出 → 启动失败（端口占用等）
        self._proxy_start_failed()

    def _proxy_start_failed(self) -> None:
        """代理起不来的统一收尾：复位按钮态 + 还原系统代理 + 弹窗提示。"""
        self.proxy_btn.setText(self.tr("启动代理"))
        self.proxy_btn.setChecked(False)
        self._update_status()
        self._restore_sysproxy_async()   # 可能刚接管完代理就挂了，补还原
        dialogs.critical(
            self,
            self.tr("代理启动失败"),
            self.tr(
                "端口 {0} 可能已被占用，或权限不足。\n"
                "请在「设置 → 偏好设置 → 代理」里换一个端口后重试。"
            ).format(self.settings.proxy_port),
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

    def _apply_proxy_port(self, port: int) -> None:
        """端口变更（设置对话框确认 / 顺延同步）：保存设置；运行中弹窗询问
        是否立即重启。

        对齐 Fiddler 心智：改端口需要重启代理才生效，让用户自己决定——
        选「是」立即重启（系统代理同步切到新端口），选「否」下次启动生效。
        """
        port = int(port)
        if port == self.settings.proxy_port:
            return
        self.settings.proxy_port = port
        save_settings(self.settings)
        self._refresh_proxy_btn_tooltip()
        if not self.proxy.running:
            self.status_bar.showMessage(
                self.tr('代理端口已保存为 {0}（重启后生效）').format(port), 5000
            )
            return
        answer = dialogs.question(
            self,
            self.tr("端口已修改"),
            self.tr('代理端口已修改为 {0}，需要重启才能生效。\n\n是否立即重启应用？重启后系统代理会自动切换到新端口。').format(port),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._restart_app_for_port(port)
        else:
            self.status_bar.showMessage(
                self.tr('新端口 {0} 将在下次启动时生效').format(port), 6000
            )

    def _refresh_proxy_btn_tooltip(self) -> None:
        """代理按钮提示同步当前端口（端口只能在设置页改，按钮提示指路）。"""
        self.proxy_btn.setToolTip(
            self.tr("抓包代理开关。监听 127.0.0.1:{0}——端口在「设置 → 偏好设置 → 代理」里改。").format(
                self.settings.proxy_port
            )
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
        self.status_bar.showMessage(self.tr('正在重启应用，切换到端口 {0} …').format(port), 5000)
        # 先让出单实例锁：新实例起来时会被锁挡回去（发现「已在运行」
        # 就只唤醒旧窗口然后退出），重启就死了
        single_instance.release()
        try:
            subprocess.Popen(
                cmd,
                start_new_session=platform.system() != "Windows",
            )
        except Exception:
            log.exception("重启应用失败，退回仅重启代理")
            single_instance.acquire()   # 没重启成，继续以本实例运行：重新占锁
            self._restarting = False
            self._restart_proxy_on_port(port)
            return
        self.close()        # 走 closeEvent：停代理、保留快照、不还原系统代理

    def _restart_proxy_on_port(self, port: int) -> None:
        """运行中按新端口重启代理 + 系统代理重接管 + 证书服务静默重启。"""
        self.status_bar.showMessage(self.tr('正在重启代理，切换到 127.0.0.1:{0} …').format(port), 4000)
        self.proxy.stop(timeout=2.0)
        self.proxy = self._make_proxy(port)
        try:
            self.proxy.start()
        except OSError:
            # 请求端口起全被占用：线程根本没起，700ms 后 verify 统一弹窗
            log.warning("代理重启失败：无可用端口", exc_info=True)
            self._update_status()
            QTimer.singleShot(700, self._verify_proxy_started)
            return
        self._update_status()
        # 顺延可能改了实际端口：后续系统代理/证书服务都要按真实端口走
        actual = self.proxy.port
        if actual != port:
            self.settings.proxy_port = actual
            self._refresh_proxy_btn_tooltip()
            save_settings(self.settings)
            self.mock.proxy_addr = ("127.0.0.1", actual)
            self.status_bar.showMessage(
                self.tr('端口 {0} 被占用，代理已自动改用 {1}').format(port, actual), 6000
            )
        # 重启成功要有可见反馈：按钮文字不变、流量列表不清空，用户无从
        # 判断是否真的重启了（之前被当成「点了 Yes 没反应」）
        self.status_bar.showMessage(
            self.tr('代理已重启，监听 127.0.0.1:{0}；系统代理切换中…').format(actual), 8000
        )
        # 系统代理还挂在旧端口上：后台先还原再按新端口重接管。顺序不能反——
        # 直接重接管会把「127.0.0.1:旧端口」当成原始设置存进状态文件，还原就错了
        if self._sysproxy_enabled():
            self._retake_sysproxy(actual)
        # 证书服务页面上显示的代理端口也要跟上
        if self.cert_server is not None and self.cert_server.running:
            self._stop_cert_server()
            try:
                server = CertServer(
                    port=self.settings.cert_port, proxy_port=actual
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
        """点击证书按钮：未运行则启动，已运行则直接重开二维码弹窗。

        刻意不做成「再点一次停止」：停止是静默的，用户点了没感知，
        会以为按钮失效（真实反馈：要点两次才弹二维码）。停止服务改到
        弹窗里用显式按钮完成，按钮勾态只表示「服务运行中」。
        """
        if self.cert_server is not None and self.cert_server.running:
            # checkable 按钮被点时会自动翻勾态，先同步回「运行中」再弹窗，
            # 否则整个二维码对话期间按钮都显示成未运行的丑态
            self._sync_cert_button()
            self._show_cert_dialog(self.cert_server)
            return
        try:
            server = CertServer(
                port=self.settings.cert_port, proxy_port=self.settings.proxy_port
            )
            server.start()
            self.cert_server = server
            # 请求端口被占用时 CertServer 自动顺延：明确告知实际端口
            if server.port != self.settings.cert_port:
                self.status_bar.showMessage(
                    self.tr('端口 {0} 被占用，证书服务已自动改用 {1}').format(self.settings.cert_port, server.port),
                    6000,
                )
            self._sync_cert_button()
            self._show_cert_dialog(server)
        except FileNotFoundError:
            dialogs.critical(
                self,
                "未找到 CA 证书",
                f"请先启动一次代理以生成 CA 证书（{CA_PEM_PATH}）",
            )
        except ValueError as e:
            # CA 文件存在但内容为空/损坏：load_ca 解析时抛 ValueError
            dialogs.critical(
                self, "CA 证书损坏", f"证书文件无法解析，删除后重启可重新生成:\n{e}"
            )
        except OSError as e:
            dialogs.critical(
                self,
                "启动失败",
                f"从端口 {self.settings.cert_port} 起没有找到可用端口:\n{e}",
            )
        self._update_status()

    def _sync_cert_button(self) -> None:
        """证书按钮勾态 / tooltip 跟随服务运行状态（stop 是唯一收敛点）。"""
        running = self.cert_server is not None and self.cert_server.running
        self.cert_btn.blockSignals(True)
        self.cert_btn.setChecked(running)
        self.cert_btn.blockSignals(False)
        self.cert_btn.setToolTip(
            self.tr("证书服务运行中：{0}（点击查看二维码）").format(self.cert_server.url)
            if running
            else self.tr("启动局域网证书下载服务（手机装 CA 用）")
        )

    def _apply_cert_port(self, port: int) -> None:
        """证书端口变更（设置对话框确认）：保存设置；运行中立即用新端口重启。"""
        port = int(port)
        if port == self.settings.cert_port:
            return
        self.settings.cert_port = port
        save_settings(self.settings)
        if self.cert_server is None or not self.cert_server.running:
            self.status_bar.showMessage(
                self.tr('证书端口已保存为 {0}，下次启动证书服务时生效').format(port), 5000
            )
            return
        # 运行中改端口：立即重启到新端口（成功后弹二维码窗，和手动开启一致）
        self._stop_cert_server()
        try:
            server = CertServer(
                port=port, proxy_port=self.settings.proxy_port
            )
            server.start()
        except OSError as e:
            self.cert_server = None
            self._update_status()
            dialogs.critical(
                self,
                "启动失败",
                f"从端口 {port} 起没有找到可用端口:\n{e}",
            )
            return
        self.cert_server = server
        if server.port != port:
            self.status_bar.showMessage(
                self.tr('端口 {0} 被占用，证书服务已自动改用 {1}').format(port, server.port), 6000
            )
        self._sync_cert_button()
        self._show_cert_dialog(server)

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
        弹窗只给纯链接——手机还得先抄地址，体验对齐「打开就扫」）。

        「好」只关窗、服务保持运行（手机还要下载证书）；停止服务是显式按钮，
        关窗不等于停服，避免用户以为关掉弹窗服务就停了。
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("证书服务已启动"))
        lay = QVBoxLayout(dlg)
        hint = QLabel(
            self.tr("手机连上同一 Wi-Fi，用相机扫下方任一二维码（或浏览器打开地址），\n"
            "在打开的网页里下载并安装证书：")
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
            self.tr('安装证书后，手机 Wi-Fi 的代理请设为：电脑IP : {0}').format(self.settings.proxy_port)
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        def stop_and_close() -> None:
            self._stop_cert_server()
            self.status_bar.showMessage(self.tr("证书服务已停止"), 3000)
            dlg.accept()

        btn_row = QHBoxLayout()
        stop_btn = QPushButton(self.tr("停止服务"))
        stop_btn.setObjectName("cert_stop_btn")
        stop_btn.setToolTip(self.tr("停止局域网证书下载服务（手机已装好证书再停）"))
        stop_btn.clicked.connect(stop_and_close)
        btn_row.addWidget(stop_btn)
        btn_row.addStretch(1)
        btn = QPushButton(self.tr("好"))
        btn.setObjectName("cert_ok_btn")
        btn.setDefault(True)
        btn.clicked.connect(dlg.accept)
        btn_row.addWidget(btn)
        lay.addLayout(btn_row)
        dlg.exec()

    def _stop_cert_server(self) -> None:
        if self.cert_server is not None:
            self.cert_server.stop()
            self.cert_server = None
        self._sync_cert_button()
        self._update_status()

    def _on_export_ca(self) -> None:
        if not CA_PEM_PATH.exists():
            dialogs.critical(
                self, "未找到 CA 证书", _ca_export_hint(CA_PEM_PATH)
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("导出 CA 证书"), "mitmproxy-ca-cert.pem", self.tr("证书 (*.pem *.cer)")
        )
        if path:
            shutil.copy(CA_PEM_PATH, path)
            dialogs.information(
                self, self.tr("已导出"), _ca_export_hint(Path(path))
            )

    def _on_clear(self) -> None:
        self.flow_store.clear()
        self.capture.clear()
        self.detail_panel.clear()
        self._update_status()
        self._refresh_stats()

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
        if follow:
            self.traffic_table.scroll_to_newest(self.settings.newest_first)
        # 统计页防抖刷新（500ms 内的批量到达合并成一次重算）
        self._stats_timer.start()

    def _on_flow_updated(self, summary: dict) -> None:
        """已存在会话的增量更新（响应到达 / WebSocket 消息到达）。

        重放并对比的待比关联只在这里触发——必须等**响应**到达，副本才有 body 可对比；
        早期版本在 `_on_flow_arrived`（请求到达、响应尚为 None）就弹对比框，
        于是「重放的都是无响应」。is_replay 守卫保证只匹配重放副本。
        """
        self.flow_store.update(summary)
        self._match_pending_compare(summary)
        selected = self._selected_flow()
        if selected is not None and getattr(selected, "id", None) == summary.get("id"):
            self.detail_panel.update_flow(selected)
        self._update_status()
        # 响应到达后大小/耗时会变，统计同样要重算（防抖同上）
        self._stats_timer.start()

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

    def _on_flow_double_clicked(self, index) -> None:
        """双击流量列表 → 弹出上下结构的请求/响应详情对话框。

        ``doubleClicked`` 给的是代理模型（过滤/搜索）的索引，要先 mapToSource
        回到源模型，再经 flow_store 取 id、capture 取 flow 实体。
        """
        source_index = self.proxy_model.mapToSource(index)
        row = self.flow_store.row_data(source_index.row())
        if row is None:
            return
        flow = self.capture.get_flow(row["id"])
        if flow is None:
            return
        self._open_flow_detail(flow)

    def _open_flow_detail(self, flow) -> None:
        """给定一条 flow，弹出上下结构的请求/响应详情对话框（双击/右键共用）。"""
        from app.ui.flow_detail_dialog import FlowDetailDialog

        dlg = FlowDetailDialog(
            flow, self, wrap_default=self.settings.body_wrap
        )
        dlg.exec()

    # ================================================================ 过滤 / 搜索

    def _on_filter_changed(self) -> None:
        config = self.filter_bar.to_config()
        self.settings.filter = config
        # 手改过滤条件 = 偏离当前预设：清掉 active 标记（菜单里不再显示
        # 「已套用」勾选），但预设本身保留——改回去还能对上。
        if self.settings.active_preset and not self._matches_active_preset(config):
            self.settings.active_preset = ""
        save_settings(self.settings)
        self._apply_filter_config(config)

    def _matches_active_preset(self, config) -> bool:
        """当前过滤条件是否与 active_preset 保存的一致。"""
        for preset in self.settings.filter_presets:
            if preset.get("name") == self.settings.active_preset:
                return preset.get("config") == config.to_dict()
        return False

    def _apply_filter_config(self, config) -> None:
        self.proxy_model.set_filter_config(config)
        self._update_status()

    # ------------------------------------------------------------ 过滤预设（#7）

    def _rebuild_preset_menu(self) -> None:
        """「预设」菜单内容动态重建（aboutToShow 时调，数据永远是最新的）。"""
        menu = self.filter_bar.preset_menu
        menu.clear()
        presets = self.settings.filter_presets
        active = self.settings.active_preset
        dirty = bool(active) and not self._matches_active_preset(
            self.filter_bar.to_config()
        )

        if not presets:
            empty = menu.addAction(self.tr("（没有预设，保存一个吧）"))
            empty.setEnabled(False)
        for preset in presets:
            name = str(preset.get("name") or "")
            label = name + (self.tr("（已修改）") if name == active and dirty else "")
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(name == active)
            action.triggered.connect(
                lambda _checked=False, n=name: self._apply_preset(n)
            )
        menu.addSeparator()
        save_action = menu.addAction(self.tr("保存当前过滤为预设…"))
        save_action.triggered.connect(self._save_preset_prompt)
        if active:
            menu.addSeparator()
            update_action = menu.addAction(self.tr('更新预设「{0}」').format(active))
            update_action.triggered.connect(
                lambda: self._update_preset(active)
            )
            delete_action = menu.addAction(self.tr('删除预设「{0}」').format(active))
            delete_action.triggered.connect(
                lambda: self._delete_preset(active)
            )

    def _apply_preset(self, name: str) -> None:
        """套用命名预设：配置进 settings + 过滤栏 + 代理模型，一并落盘。"""
        for preset in self.settings.filter_presets:
            if preset.get("name") != name:
                continue
            config = FilterConfig.from_dict(preset.get("config") or {})
            self.settings.filter = config
            self.settings.active_preset = name
            save_settings(self.settings)
            self.filter_bar.load_config(config)
            self._apply_filter_config(config)
            self.status_bar.showMessage(
                self.tr('已套用过滤预设「{0}」').format(name), 3000
            )
            return

    def _save_preset_prompt(self) -> None:
        """弹框问名字 → 保存（重名覆盖，与「更新」等效）。"""
        name, ok = QInputDialog.getText(
            self,
            self.tr("保存过滤预设"),
            self.tr("预设名称："),
            text=self.tr("预设 {0}").format(len(self.settings.filter_presets) + 1),
        )
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return
        self._save_preset(name)

    def _save_preset(self, name: str) -> None:
        """把当前过滤条件存为预设（重名覆盖）。"""
        presets = [
            p for p in self.settings.filter_presets
            if p.get("name") != name
        ]
        presets.append({
            "name": name,
            "config": self.settings.filter.to_dict(),
        })
        self.settings.filter_presets = presets
        self.settings.active_preset = name
        save_settings(self.settings)
        self.status_bar.showMessage(
            self.tr('已保存过滤预设「{0}」').format(name), 3000
        )

    def _update_preset(self, name: str) -> None:
        """用当前过滤条件覆盖指定预设。"""
        for preset in self.settings.filter_presets:
            if preset.get("name") == name:
                preset["config"] = self.settings.filter.to_dict()
                save_settings(self.settings)
                self.status_bar.showMessage(
                    self.tr('已更新过滤预设「{0}」').format(name), 3000
                )
                return

    def _delete_preset(self, name: str) -> None:
        """删除预设；删的是当前套用的那套就顺带清掉 active 标记。"""
        self.settings.filter_presets = [
            p for p in self.settings.filter_presets if p.get("name") != name
        ]
        if self.settings.active_preset == name:
            self.settings.active_preset = ""
        save_settings(self.settings)
        self.status_bar.showMessage(
            self.tr('已删除过滤预设「{0}」').format(name), 3000
        )

    def _on_find_shortcut(self) -> None:
        self.search_bar.focus_input()
        # 快捷键唤出时同步按钮的按下态（blockSignals 避免再触发一次 toggled）
        self._set_search_btn_checked(True)

    def _on_search_toggled(self, on: bool) -> None:
        """工具栏按钮：开 = 显示并聚焦，关 = 收起并清空搜索条件。"""
        if on:
            self.search_bar.focus_input()
        else:
            self._on_search_closed()

    def _set_search_btn_checked(self, on: bool) -> None:
        self.search_btn.blockSignals(True)
        self.search_btn.setChecked(on)
        self.search_btn.blockSignals(False)

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
        # 收起时按钮要弹起来（Esc 关闭 / 按钮关闭走的是同一条路）
        self._set_search_btn_checked(False)

    def _cycle_match(self, delta: int) -> None:
        """Enter / 上下按钮：在匹配行间循环跳转（可见行即匹配行）。"""
        model = self.proxy_model
        if model.rowCount() == 0:
            return
        current = self.traffic_table.selectionModel().selectedRows()
        current_row = current[0].row() if current else -1
        next_row = (current_row + delta) % model.rowCount()
        # 用首个可见列定位：列 0（「#」）可被用户勾掉，隐藏列上 scrollTo
        # 是空操作，行选中了却不滚动，看着像跳转失灵
        col = self.traffic_table.first_visible_column()
        self.traffic_table.setCurrentIndex(model.index(next_row, col))
        self.traffic_table.scrollTo(model.index(next_row, col))

    # ================================================================ 重放

    def _on_table_context_menu(self, pos) -> None:
        flows = self._selected_flows()
        menu = self._build_table_context_menu(flows)
        menu.exec(self.traffic_table.viewport().mapToGlobal(pos))

    # ================================================================ 列显隐

    def _apply_hidden_columns(self) -> None:
        """按 settings.hidden_columns 应用列显隐（启动 / 恢复设置时调用）。"""
        hidden = set(self.settings.hidden_columns)
        for key in COLUMN_KEYS:
            self.traffic_table.hide_column_by_key(key, key in hidden)

    def _on_column_menu_requested(self, pos) -> None:
        """表头右键 → 在表头处弹列菜单（位置用表头局部坐标换算，防被裁剪）。"""
        menu = self._build_column_menu()
        menu.exec(self.traffic_table.horizontalHeader().mapToGlobal(pos))

    def _build_column_menu(self) -> "QMenu":
        """列显隐菜单（表头右键与「外观 → 流量列表列…」共用）。

        勾选态 = 显示；取消勾选 = 隐藏。只默认隐藏可选列，但任何列都能藏——
        窄屏下把 host / 路径藏掉只留状态和耗时是常见玩法。
        """
        menu = QMenu(self)
        hidden = set(self.settings.hidden_columns)
        for key, label in zip(COLUMN_KEYS, column_labels()):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key not in hidden)
            action.triggered.connect(
                lambda checked=False, k=key: self._toggle_column(k, checked)
            )
        return menu

    def _toggle_column(self, key: str, checked: bool) -> None:
        """勾选/取消一列：立即生效并持久化（key 存 settings，重启不丢）。"""
        if not self.traffic_table.hide_column_by_key(key, not checked):
            return
        hidden = set(self.settings.hidden_columns)
        if checked:
            hidden.discard(key)
        else:
            hidden.add(key)
        self.settings.hidden_columns = sorted(hidden)
        save_settings(self.settings)

    def _show_column_menu_from_menu_bar(self) -> None:
        """「外观 → 流量列表列…」入口：在表头位置弹出同一个菜单。"""
        header = self.traffic_table.horizontalHeader()
        menu = self._build_column_menu()
        menu.exec(header.mapToGlobal(header.rect().bottomLeft()))

    def _build_table_context_menu(self, flows) -> "QMenu":
        """构建流量列表右键菜单（抽出便于单元测试，不直接 exec）。"""
        has_selection = bool(flows)
        count = len(flows)
        batch = self.tr('（{0} 条）').format(count) if count > 1 else ""
        menu = QMenu(self)
        detail_action = menu.addAction(self.tr("查看详情…"))
        detail_action.setEnabled(count == 1)
        detail_action.triggered.connect(
            lambda: self._open_flow_detail(flows[0])
        )
        menu.addSeparator()
        replay_action = menu.addAction(self.tr("重放请求 (R / Ctrl+R)"))
        edit_replay_action = menu.addAction(self.tr("编辑并重放… (E)"))
        compare_action = menu.addAction(self.tr("重放并对比…"))
        # 两条会话对比：与「重放并对比」不同——它比的是任意两条独立会话
        # （线上 vs 测试同一个接口的返回差在哪），不需要重放
        diff_action = menu.addAction(self.tr("对比两条会话…"))
        menu.addSeparator()
        curl_action = menu.addAction(self.tr('复制为 cURL (bash){0}  Ctrl+Shift+C').format(batch))
        curl_cmd_action = menu.addAction(self.tr('复制为 cURL (Windows cmd){0}').format(batch))
        copy_url_action = menu.addAction(self.tr('仅复制 URL{0}  Ctrl+Shift+U').format(batch))
        menu.addSeparator()
        export_action = menu.addAction(self.tr('导出选中会话{0}…  Ctrl+E').format(batch))
        export_resp_action = menu.addAction(self.tr("导出完整响应（Headers+Body）…"))
        menu.addSeparator()
        delete_action = menu.addAction(self.tr('删除选中会话{0}  Del').format(batch))
        delete_action.setEnabled(has_selection)
        delete_action.triggered.connect(self._delete_selected_flows)
        menu.addSeparator()
        tool_body_action = menu.addAction(self.tr("在工具页中打开 body"))
        tool_body_action.setEnabled(count == 1)
        tool_body_action.triggered.connect(self._send_body_to_tool)
        api_action = menu.addAction(self.tr("发送到 API 调试"))
        api_action.setEnabled(count == 1)
        api_action.triggered.connect(self._send_request_to_api)
        menu.addSeparator()
        mark_action = menu.addAction(self.tr("标记/备注…"))
        mark_action.setEnabled(count == 1)
        mark_action.triggered.connect(self._mark_selected)
        clear_mark_action = menu.addAction(self.tr("清除备注"))
        clear_mark_action.setEnabled(
            count == 1 and bool(getattr(flows[0], "comment", "") if flows else "")
        )
        clear_mark_action.triggered.connect(self._clear_mark_selected)
        menu.addSeparator()
        mock_action = menu.addAction(self.tr("加入 Mock（用原响应做 Mock）"))
        mock_action.setEnabled(count == 1)
        mock_action.triggered.connect(self._add_selected_to_mock)

        for action in (replay_action, edit_replay_action, compare_action,
                       curl_action, curl_cmd_action, copy_url_action,
                       export_action, export_resp_action):
            action.setEnabled(has_selection)

        # 编辑/对比是单条语义：弹窗一次只能处理一条，多选时若照旧启用会
        # 只偷偷重放第一条（很反直觉），这里显式禁用并把原因写进 tooltip。
        if count > 1:
            for action in (edit_replay_action, compare_action):
                action.setEnabled(False)
                action.setToolTip(
                    self.tr("仅支持单条会话：编辑与对比弹窗一次只能处理一条")
                )
        # 两条会话对比：恰好选中两条才有意义
        if count != 2:
            diff_action.setEnabled(False)
            diff_action.setToolTip(self.tr("请选中两条会话（Ctrl 点选第二条）"))
        else:
            diff_action.triggered.connect(
                lambda: self._open_flow_diff(flows[0], flows[1])
            )

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
        return menu

    # ================================================================ 用户脚本（#10）

    def _on_scripts_changed(self) -> None:
        """脚本页变更（新建/编辑/删除/启停）：持久化启用态 + 重建 addon。

        代理在跑 → 热替换（ProxyService.reload_script_addons，走事件循环
        线程，不重启代理）；没在跑 → 下次启动经 _make_proxy 自动带上。
        """
        self.settings.scripts = self.scripts_panel.enabled_map()
        save_settings(self.settings)
        addons = self._build_script_addons()
        if self.proxy.running and self.proxy.reload_script_addons(addons):
            self.status_bar.showMessage(
                self.tr("用户脚本已热替换（{0} 个生效）").format(len(addons)), 3000
            )
        else:
            self.status_bar.showMessage(
                self.tr("用户脚本将在下次启动代理时生效"), 3000
            )

    # ================================================================ 两条会话对比

    def _open_flow_diff(self, flow_a, flow_b) -> None:
        """打开「两条会话对比」对话框（非模态，与 CompareDialog 一致）。

        场景：选中两条独立会话（如线上域名 vs 测试域名的同一接口），
        比请求行 / 请求头 / 响应状态行 / 响应头 / body 的差异。
        """
        dialog = FlowDiffDialog(flow_a, flow_b, parent=self,
                                wrap_default=self.settings.body_wrap)
        dialog.finished.connect(
            lambda _r, d=dialog: self._drop_diff_dialog(d)
        )
        self._diff_dialogs.append(dialog)
        dialog.show()
        dialog.raise_()

    def _drop_diff_dialog(self, dialog) -> None:
        try:
            self._diff_dialogs.remove(dialog)
        except ValueError:
            pass
        dialog.deleteLater()

    # ================================================================ 加入 Mock

    def _add_selected_to_mock(self) -> None:
        """右键「加入 Mock」：用抓到的请求 URL（精确匹配）+ 原响应预填一条 Mock 规则，
        打开「新增 Mock 规则」窗口让用户确认/微调；用户在窗口点「确定」后才真正加入列表。

        默认精确匹配该请求的 URL，响应 body 即原响应 body、状态码/Content-Type
        一并带过去；请求 body 也保留在规则里作参考（不参匹配）。
        """
        flows = self._selected_flows()
        if len(flows) != 1:
            return
        flow = flows[0]
        res = getattr(flow, "response", None)
        if res is None:
            self.status_bar.showMessage(self.tr("该请求还没有响应，无法生成 Mock"), 5000)
            return
        rule = self._build_mock_rule(flow)
        # 不直接落库：先打开新建窗口，自动带入 URL/请求 body/响应 body/状态码/Headers，
        # 用户检查或微调后点「确定」，由 RuleEditorDialog 负责加入 store。
        dialog = RuleEditorDialog(self.rule_store, rule, parent=self)
        if dialog.exec():
            self.tabs.setCurrentWidget(self.rules_panel)
            self.rules_panel.select_rule(rule.id)
            self.status_bar.showMessage(
                self.tr('已加入 Mock：{0}（精确匹配 URL，响应=原响应）').format(rule.name), 6000
            )
        # 取消则什么都不做，规则不会进入列表

    @staticmethod
    def _decode_bytes(data) -> str:
        """字节 → 文本（utf-8，失败处用替换字符）；None/空返回空串。"""
        if not data:
            return ""
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    @staticmethod
    def _mock_rule_name(req, url: str) -> str:
        """用 host + path 起个短名字，便于在规则列表里一眼认出。"""
        from urllib.parse import urlsplit

        try:
            parts = urlsplit(url)
            host = parts.netloc or "host"
            path = parts.path or "/"
            base = f"{getattr(req, 'method', '')} {host}{path}"
        except Exception:
            base = url
        return base[:80]

    def _build_mock_rule(self, flow) -> Rule:
        """从抓包 flow 构造 Mock 规则：精确匹配 URL，响应=原响应。"""
        req = getattr(flow, "request", None)
        res = flow.response
        url = req.pretty_url
        rule = Rule.create(name=self._mock_rule_name(req, url))
        rule.match = Match(type=EXACT, value=url, method="")
        rule.action = Action(
            status=res.status_code,
            headers={str(k): str(v) for k, v in dict(res.headers).items()},
            body_source="inline",
            body=self._decode_bytes(res.get_content(strict=False)),
            latency_ms=0,
        )
        rule.source = "captured"
        rule.request_body = self._decode_bytes(req.get_content(strict=False))
        return rule

    def _send_body_to_tool(self) -> None:
        """把选中会话的 body 送进工具页（有响应就用响应，否则用请求）。

        抓到一段 base64 参数或一段 JSON，直接送过去解/格式化，不用手选中再复制。
        送到哪个子页由用户当前停留在哪一页决定——但 API 调试页的输入框是
        「要发送的请求体」，不是用来查看抓包 body 的，落到那里用户会以为点了
        没反应，所以停在 API 页时改投 JSON / 编码转换，保证看得见内容。
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
            self.status_bar.showMessage(
                self.tr("该会话没有可查看的 body（响应为空或尚未捕获）"), 5000
            )
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
            note = self.tr("（二进制内容已按十六进制导入）")
        else:
            note = self.tr("（已截断到前 512KB）") if truncated else ""
        page = self.tool_panel.current_key
        # FIX 报文优先：8=FIX 开头的 body 没有歧义，直接进 FIX 页
        # （API 调试页的 body 框是「要发送的请求体」，不是看抓包 body 的地方，
        # 所以像 FIX 也不投 api）
        if is_fix_text(text):
            page = "fix"
        elif page == "api":
            page = "json" if self._body_looks_json(text, content_type) else "codec"
        self.tabs.setCurrentWidget(self.tool_panel)
        self.tool_panel.set_body_text(text, page)
        label = {
            "json": self.tr("JSON 工具"),
            "compare": self.tr("JSON 比对"),
            "api": self.tr("API 调试"),
            "fix": self.tr("FIX 解析"),
        }.get(page, self.tr("编码转换"))
        self.status_bar.showMessage(
            self.tr('已把该会话的 body 送入工具页 · {0}{1}').format(label, note), 5000
        )

    @staticmethod
    def _body_looks_json(text: str, content_type: str) -> bool:
        """粗略判断 body 像不像 JSON（决定投到哪个工具子页）。"""
        ct = (content_type or "").split(";")[0].strip().lower()
        if ct in ("application/json", "text/json") or ct.endswith("+json"):
            return True
        t = (text or "").strip()
        return bool(t) and t[:1] in ("{", "[")

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
            method=req.method, url=format_request_url(req), headers=headers, body=body_text
        )
        self.status_bar.showMessage(self.tr("已把该请求带入 API 调试页（改完点「发送」）"), 5000)

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
            self.tr("标记/备注"),
            self.tr("给这条会话写个备注（列表「标记」列显示）："),
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
            self.tr("已备注") if comment else self.tr("已清除备注"), 3000
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
        extra = self.tr('{0} 条 · ').format(len(flows)) if len(flows) > 1 else ""
        self.status_bar.showMessage(
            self.tr('已复制 cURL（{0}，{1}{2} 字符）: {3}…').format(label, extra, len(text), text[:80]), 5000
        )

    def _copy_url(self) -> None:
        flows = self._selected_flows()
        if not flows:
            return
        # 复制出来是要粘到浏览器/命令行里用的，IPv6 必须带方括号
        # （pretty_url 拼出 http://::1:8080/x 这种解析不了的串）
        urls = [format_request_url(f.request) for f in flows]
        urls = [u for u in urls if u]
        if not urls:
            return
        QApplication.clipboard().setText("\n".join(urls))
        shown = urls[0] if len(urls) == 1 else self.tr('{0} 条（首条 {1}）').format(len(urls), urls[0])
        self.status_bar.showMessage(self.tr('已复制 URL: {0}').format(shown), 5000)

    def _export_selected(self, preferred: str | None = None) -> None:
        flows = self._selected_flows()
        if not flows:
            dialogs.information(self, self.tr("提示"), self.tr("请先在流量列表里选中一条会话"))
            return
        if len(flows) > 1 and preferred in SINGLE_ONLY_FORMATS:
            dialogs.information(
                self,
                self.tr("该格式不支持多选"),
                self.tr("「仅响应 Body」一个文件只能装一条会话的 body。\n"
                "请只选一条，或改用 HAR / 原始报文 / 完整响应。"),
            )
            return
        missing = [f for f in flows if getattr(f, "response", None) is None]
        if missing and (preferred in REQUIRES_RESPONSE):
            dialogs.information(
                self,
                self.tr("暂无响应"),
                self.tr("所选会话里有还没响应的请求（请求进行中或连接已中断），无法导出。"),
            )
            return
        filters, mapping = name_filters()
        selected = next((label for label, f in mapping.items() if f == preferred), None)
        path, selected = QFileDialog.getSaveFileName(
            self,
            self.tr('导出选中会话（{0} 条）').format(len(flows)) if len(flows) > 1 else self.tr("导出选中会话"),
            default_filename(flows, preferred or FORMAT_HAR),
            filters,
            selected or "",
        )
        if not path:
            return
        fmt = mapping.get(selected, preferred or FORMAT_HAR)
        if len(flows) > 1 and fmt in SINGLE_ONLY_FORMATS:
            dialogs.information(
                self, self.tr("该格式不支持多选"), self.tr("「仅响应 Body」请只选一条会话。")
            )
            return
        if fmt in REQUIRES_RESPONSE and any(
            getattr(f, "response", None) is None for f in flows
        ):
            dialogs.information(self, self.tr("暂无响应"), self.tr("所选会话里有还没响应的请求，无法导出。"))
            return
        path = ensure_suffix(path, fmt, flows)
        try:
            Path(path).write_bytes(export_bytes(flows, fmt))
        except (OSError, ValueError) as e:
            dialogs.critical(self, "导出失败", f"写入 {path} 失败:\n{e}")
            return
        self.status_bar.showMessage(
            self.tr('已导出 {0} 条 → {1}').format(len(flows), path) if len(flows) > 1 else self.tr('已导出 → {0}').format(path),
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
            self.tr("退出时将自动保存会话快照") if checked else self.tr("已关闭退出自动保存"), 4000
        )

    def _save_session_dialog(self) -> None:
        flows = self._session_flows()
        if not flows:
            dialogs.information(self, self.tr("没有可保存的会话"), self.tr("当前列表是空的。"))
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        default = str(Path(self._session_start_dir()) / f"session-{stamp}{SESSION_EXT}")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr('保存会话（{0} 条）').format(len(flows)), default, self.tr('会话文件 (*{0})').format(SESSION_EXT)
        )
        if not path:
            return
        if not path.lower().endswith(SESSION_EXT):
            path += SESSION_EXT
        result = save_session(path, flows)
        if not result.ok:
            dialogs.critical(self, "保存失败", f"{path}\n\n{result.error}")
            return
        self._remember_session_dir(path)

        size = format_size(result.bytes_written)
        detail = ""
        if result.bodies_dropped:
            detail += (
                self.tr('\n\n注意：有 {0} 条会话的 body 未保存（超出单包体积预算）。').format(result.bodies_dropped)
            )
        elif result.bodies_truncated:
            detail += self.tr('\n\n注意：有 {0} 条会话的 body 被截断。').format(result.bodies_truncated)
        dialogs.information(
            self,
            self.tr("已保存"),
            self.tr('共 {0} 条会话 → {1}\n文件大小 {2}{3}').format(result.count, path, size, detail),
        )
        self.status_bar.showMessage(self.tr('已保存 {0} 条会话 → {1}').format(result.count, path), 5000)

    def _open_session_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("打开会话"), self._session_start_dir(), self.tr('会话文件 (*{0})').format(SESSION_EXT)
        )
        if not path:
            return
        self._load_session_file(path)

    def _load_session_file(self, path: str, confirm_clear: bool = True) -> bool:
        """把会话文件恢复到列表；返回是否真的恢复了。"""
        if confirm_clear and self.flow_store.rowCount() > 0:
            answer = dialogs.question(
                self,
                self.tr("打开会话"),
                self.tr('当前列表有 {0} 条会话，打开文件会先清空它们。\n是否继续？').format(self.flow_store.rowCount()),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        result = load_session(path)
        if not result.ok:
            dialogs.critical(self, "打开失败", f"{path}\n\n{result.error}")
            return False
        if not result.flows:
            dialogs.information(
                self, self.tr("没有可恢复的会话"), self.tr('{0}\n\n文件中没有有效会话。').format(path)
            )
            return False

        self._remember_session_dir(path)
        dropped = self._apply_loaded_session(result.flows, result.summaries)
        note = ""
        if result.skipped:
            note += self.tr('\n跳过无法解析的行：{0} 条。').format(result.skipped)
        if result.bodies_truncated:
            # 自动快照单条只留 64KB：不提示的话，用户点开大 JSON 只会看到
            # 「JSON 解析失败」，误以为是格式化能力问题。
            note += self.tr(
                '\n有 {0} 条会话的 body 被截断（超出快照单条上限），详情面板会标注。'
            ).format(result.bodies_truncated)
        if dropped:
            note += self.tr('\n超出保存条数上限，最早的 {0} 条未载入。').format(dropped)
        dialogs.information(
            self,
            self.tr("已恢复"),
            self.tr('共恢复 {0} 条会话。{1}').format(result.count - dropped, note),
        )
        self.status_bar.showMessage(self.tr('已打开会话 {0}').format(path), 5000)
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
        self._refresh_stats()
        return dropped

    def _maybe_restore_autosave(self) -> None:
        """启动时询问是否恢复上次退出时的快照（可在构造时关掉）。"""
        meta = read_autosave_meta()
        if not meta:
            return
        count = int(meta.get("count") or 0)
        saved_at = str(meta.get("saved_at") or "")
        answer = dialogs.question(
            self,
            self.tr("恢复上次会话"),
            self.tr('检测到上次退出时保存的 {0} 条会话').format(count)
            + (f"（{saved_at}）" if saved_at else "")
            + self.tr("。\n是否恢复到列表？"),
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
        state = self.tr("已立即生效") if applied_now else self.tr("代理启动后生效")

        parts = []
        if throttle_cfg.enabled:
            parts.append(self.tr('弱网 {0}ms / {1}kbps').format(throttle_cfg.latency_ms, throttle_cfg.rate_kbps))
        if specs:
            parts.append(self.tr('{0} 条域名映射').format(len(specs)))
        if local_count:
            parts.append(self.tr('{0} 条本地目录映射').format(local_count))
        message = "、".join(parts) if parts else self.tr("网络模拟已关闭")
        if skipped:
            message += self.tr('（{0} 条映射填写不完整，已跳过）').format(len(skipped))
        message = f"{message} · {state}"
        self.status_bar.showMessage(message, 5000)
        self.network_panel.set_status(message)
        self._update_status()

    # ================================================================ 重放

    def _replay_selected(self, edit: bool, compare: bool = False) -> None:
        flows = self._selected_flows()
        if not flows:
            return
        if not self.proxy.running:
            dialogs.information(self, self.tr("提示"), self.tr("请先启动代理再重放"))
            return
        if len(flows) == 1:
            self._replay_one(flows[0], edit=edit, compare=compare)
            return
        # 批量：逐条入队。编辑/对比是单条语义（弹窗一次只能处理一条），
        # 菜单已按条数禁用，这里只做「重放」。
        queued = 0
        failed = 0
        for flow in flows:
            copy = make_replay_copy(flow)
            if self.proxy.replay_flow(copy):
                queued += 1
            else:
                failed += 1
        if queued:
            message = self.tr('已加入重放队列（{0} 条）').format(queued)
            if failed:
                message += self.tr('，{0} 条入队失败').format(failed)
            self.status_bar.showMessage(message, 4000)
        else:
            self.status_bar.showMessage(self.tr("重放失败：没有请求进入队列"), 4000)

    def _replay_one(self, flow, edit: bool, compare: bool = False) -> None:
        """单条重放：支持先编辑、以及响应到达后自动对比。"""
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
            message = self.tr('已加入重放队列: {0} {1}').format(copy.request.method, copy.request.pretty_url)
            if compare:
                message += self.tr("（响应到达后自动打开对比）")
            self.status_bar.showMessage(message, 3000)

    def _delete_selected_flows(self) -> None:
        """把选中的会话从列表移除（只删显示，不影响 capture 缓存）。"""
        flows = self._selected_flows()
        if not flows:
            return
        removed = self.flow_store.remove_ids([f.id for f in flows])
        if not removed:
            return
        # 删掉的正好是详情面板当前显示的那条 → 清掉面板，避免显示幽灵内容
        shown = getattr(self.detail_panel, "_flow", None)
        if shown is not None and shown.id in {f.id for f in flows}:
            self.detail_panel.clear()
        self.traffic_table.clearSelection()
        self.status_bar.showMessage(
            self.tr('已删除 {0} 条会话').format(removed), 3000
        )
        self._update_status()
        self._refresh_stats()

    # ================================================================ 断点调试

    def _on_breakpoint_toggled(self, on: bool) -> None:
        """工具栏断点开关：写进配置，addon 每次钩子现读，无需重启代理。"""
        self.settings.breakpoint.enabled = bool(on)
        save_settings(self.settings)
        state = self.tr("已开启") if on else self.tr("已关闭")
        self.status_bar.showMessage(
            self.tr('断点调试{0}').format(state), 3000
        )

    def _on_flow_intercepted(self, flow, phase: str) -> None:
        """断点命中：弹编辑器。非模态——多条同时撞断点时要能并排处理。"""
        dialog = BreakpointDialog(
            flow, phase,
            on_resume=self._resume_breakpoint,
            on_kill=self._kill_breakpoint,
            parent=self,
        )
        # 关掉后清引用，否则一堆 dialog 常驻内存
        dialog.finished.connect(lambda _r, d=dialog: self._drop_breakpoint_dialog(d))
        self._breakpoint_dialogs.append(dialog)
        dialog.show()
        dialog.raise_()
        self.status_bar.showMessage(
            self.tr('断点命中（{0}）：会话已挂起，改完点「继续放行」').format(
                self.tr("请求前") if phase == "request" else self.tr("响应前")
            ),
            5000,
        )

    def _drop_breakpoint_dialog(self, dialog) -> None:
        try:
            self._breakpoint_dialogs.remove(dialog)
        except ValueError:
            pass
        dialog.deleteLater()

    def _resume_breakpoint(self, flow) -> None:
        """放行：先清 addon 的挂起标记，再经事件循环 resume（线程安全）。"""
        self.breakpoint.forget(flow)
        self.proxy.resume_flow(flow)

    def _kill_breakpoint(self, flow) -> None:
        self.breakpoint.forget(flow)
        self.proxy.kill_flow(flow)

    # ================================================================ MCP 接口

    def _mcp_flows(self) -> list:
        """给 MCP 的会话快照。

        capture.flows 由代理线程写入，这里在 HTTP 线程遍历 —— 迭代途中 dict
        被插入会抛 RuntimeError，重试一次即可（不必加锁，快照允许轻微偏差）。
        """
        for _ in range(2):
            try:
                return list(self.capture.flows.values())
            except RuntimeError:
                continue
        return []

    def _mcp_flow_by_id(self, flow_id: str):
        """按 id 取单条（详情工具用）：走 capture 自己的查表，与 UI 同一条路。"""
        try:
            return self.capture.get_flow(flow_id)
        except Exception:
            return None

    # ================================================================ MCP 写操作

    def _mcp_add_mock_rule(self, args: dict) -> dict:
        """MCP add_mock_rule：按参数建一条 Mock 规则并入库（即时生效）。

        规则模型与「新增 Mock 规则」窗口完全一致（Rule + Match + Action），
        经 RuleStore.add 落库——规则页 / MockAddon 走的都是这一份。
        """
        import re as _re

        url = str(args.get("url") or "").strip()
        if not url:
            return {"error": self.tr("缺少 url 参数")}
        match_type = str(args.get("match_type") or CONTAINS).strip().lower()
        if match_type not in MATCH_TYPES:
            return {"error": self.tr(
                "不支持的匹配方式：{0}（可用 {1}）").format(
                match_type, " / ".join(MATCH_TYPES))}
        if match_type == REGEX:
            try:
                _re.compile(url)
            except _re.error as e:
                return {"error": self.tr("正则无法编译：{0}").format(e)}
        try:
            status = int(args.get("status", 200))
        except (TypeError, ValueError):
            return {"error": self.tr("status 必须是整数")}
        if not (100 <= status <= 599):
            return {"error": self.tr("status 必须在 100~599 之间")}
        headers = args.get("headers") or {}
        if not isinstance(headers, dict):
            return {"error": self.tr("headers 必须是 JSON 对象")}

        rule = Rule.create(name=str(args.get("name") or "").strip() or url)
        rule.enabled = bool(args.get("enabled", True))
        rule.match = Match(
            type=match_type,
            value=url,
            method=str(args.get("method") or "").strip().upper(),
        )
        rule.action = Action(
            status=status,
            headers={str(k): str(v) for k, v in headers.items()},
            body=str(args.get("body") or ""),
        )
        self.rule_store.add(rule)
        return {
            "ok": True,
            "rule": {
                "id": rule.id,
                "name": rule.name,
                "enabled": rule.enabled,
                "match": rule.match.to_dict(),
                "action": rule.action.to_dict(),
            },
        }

    def _mcp_replay_flow(self, args: dict) -> dict:
        """MCP replay_flow：按 id 重放一条会话（副本重放，原会话不动）。"""
        flow, err = resolve_flow(
            self._mcp_flows(), args.get("id"), self._mcp_flow_by_id
        )
        if flow is None:
            return {"error": err}
        if not self.proxy.running:
            return {"error": self.tr("代理未运行，无法重放")}
        copy = make_replay_copy(flow)
        if not self.proxy.replay_flow(copy):
            return {"error": self.tr("重放入队失败")}
        return {
            "ok": True,
            "replayed_id": flow.id,
            "method": getattr(copy.request, "method", ""),
            "url": format_request_url(copy.request),
        }

    def _mcp_set_breakpoint(self, args: dict) -> dict:
        """MCP set_breakpoint：改断点开关 / 阶段 / 关键词（活对象，即时生效）。"""
        bp = self.settings.breakpoint
        keywords = args.get("url_keywords")
        if keywords is not None and not isinstance(keywords, list):
            return {"error": self.tr("url_keywords 必须是字符串数组")}

        if "enabled" in args:
            bp.enabled = bool(args.get("enabled"))
        if "on_request" in args:
            bp.on_request = bool(args.get("on_request"))
        if "on_response" in args:
            bp.on_response = bool(args.get("on_response"))
        if keywords is not None:
            bp.url_keywords = [str(k) for k in keywords]
        save_settings(self.settings)
        # 工具栏开关同步（blockSignals：不走 _on_breakpoint_toggled 的重复落盘）
        self.breakpoint_btn.blockSignals(True)
        self.breakpoint_btn.setChecked(bp.enabled)
        self.breakpoint_btn.blockSignals(False)
        return {"ok": True, "breakpoint": bp.to_dict()}

    # ================================================================ 统计页

    def _stats_flows(self) -> list:
        """统计页的会话列表：与流量列表保持一致（删除过的行不计入）。

        与 MCP 的 ``_mcp_flows``（capture 全量快照）刻意不同：统计页回答的是
        「我现在看的这些请求整体如何」，用户从列表删掉的行不该还留在统计里。
        聚合逻辑是同一份（``app/stats.py``），只是输入列表不同。
        """
        out = []
        for row in self.flow_store.rows:
            flow = self.capture.get_flow(row.get("id"))
            if flow is not None:
                out.append(flow)
        return out

    def _refresh_stats(self) -> None:
        """重算统计页。只在统计页是当前标签时算——别的页忙着时白算纯浪费，
        切回来由 ``_on_tab_changed`` 补一次，数据不会过期。"""
        if self.tabs.currentWidget() is not self.stats_panel:
            return
        # 先标范围再聚合：过滤生效时统计仍是全量口径（与 MCP get_stats
        # 同源），不注明的话用户会以为数字和状态栏对不上是算错了
        try:
            self.stats_panel.set_scope(
                len(self.flow_store.rows), self.proxy_model.rowCount()
            )
        except Exception:
            log.exception("更新统计范围说明失败")
        self.stats_panel.refresh()

    def _on_tab_changed(self, index) -> None:
        """切到统计页时补一次刷新（防抖定时器可能还没到点）。"""
        if self.tabs.widget(index) is self.stats_panel:
            self._refresh_stats()

    def _reveal_flow(self, flow_id: str) -> None:
        """统计页双击慢请求 → 跳到流量列表对应行并选中。

        Top N 看不到上下文就等于没用——能一步跳到原会话才有排查价值。
        被当前过滤条件藏起来的行给句提示，别让用户以为点击没反应。
        """
        row = None
        for i, r in enumerate(self.flow_store.rows):
            if r.get("id") == flow_id:
                row = i
                break
        if row is None:
            return
        self.tabs.setCurrentWidget(self.traffic_page)
        # mapFromSource 只能拿到逻辑列 0，隐藏时它不可见——换成首个可见列，
        # 否则 scrollTo 无效（行选中了但停在视口外）
        idx = self.proxy_model.mapFromSource(self.flow_store.index(row, 0))
        if idx.isValid():
            idx = idx.siblingAtColumn(self.traffic_table.first_visible_column())
        if not idx.isValid():
            self.status_bar.showMessage(
                self.tr("该会话被当前过滤条件隐藏，已切回流量页"), 3000
            )
            return
        self.traffic_table.clearSelection()
        self.traffic_table.setCurrentIndex(idx)
        self.traffic_table.scrollTo(idx)

    def _set_mcp_checked(self, on: bool) -> None:
        """改按钮态但不触发 toggled（失败回滚时用，避免递归）。"""
        self.mcp_btn.blockSignals(True)
        self.mcp_btn.setChecked(on)
        self.mcp_btn.blockSignals(False)

    def _start_mcp(self) -> bool:
        """按当前 settings 起服务并给出提示（局域网可见时语气不同）。"""
        self.mcp.port = self.settings.mcp_port
        self.mcp.host = self.settings.mcp_host
        if not self.mcp.start():
            self._set_mcp_checked(False)
            self.status_bar.showMessage(
                self.tr('MCP 服务启动失败：地址 {0} 的端口 {1} 起均不可用').format(
                    self.settings.mcp_host, self.settings.mcp_port
                ),
                8000,
            )
            return False
        if self.mcp.exposed:
            self.status_bar.showMessage(
                self.tr('MCP 服务已启动（局域网可见）：{0} —— '
                        '抓包含 Cookie / 鉴权头，用完记得关').format(self.mcp.url),
                10000,
            )
        else:
            self.status_bar.showMessage(
                self.tr('MCP 服务已启动：{0}').format(self.mcp.url), 8000
            )
        return True

    def _on_mcp_toggled(self, on: bool) -> None:
        if on:
            if not self._start_mcp():
                return
            self.settings.mcp_enabled = True
            save_settings(self.settings)
        else:
            self.mcp.stop()
            self.settings.mcp_enabled = False
            save_settings(self.settings)
            self.status_bar.showMessage(self.tr("MCP 服务已停止"), 3000)

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
                self.tr('重放对比等待超时（{0} 条）：未收到重放响应').format(expired), 6000
            )
        if not self._pending_compare:
            self._compare_timer.stop()

    def _open_compare(self, pending: dict) -> None:
        original = self.capture.get_flow(pending["origin_id"])
        new_flow = self.capture.get_flow(pending["copy_id"])
        if original is None or new_flow is None:
            self.status_bar.showMessage(
                self.tr("对比失败：原会话或重放会话已被淘汰出缓存"), 5000
            )
            return
        dialog = CompareDialog(
            original, new_flow, parent=self, wrap_default=self.settings.body_wrap
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        # 关掉就摘引用：每个 CompareDialog 都持有两条完整 flow（含 body），
        # 只靠下面的 KEEP 截断会一直强引用着最后 N 个已关闭的对话框，
        # 大响应场景下几百 MB 就这么常驻到进程退出
        dialog.finished.connect(
            lambda _r, d=dialog: self._drop_compare_dialog(d)
        )
        self._compare_dialogs.append(dialog)
        # 只保留最近几个，避免开太多不关慢慢攒内存
        for stale in self._compare_dialogs[:-COMPARE_DIALOG_KEEP]:
            stale.close()
        self._compare_dialogs = self._compare_dialogs[-COMPARE_DIALOG_KEEP:]

    def _drop_compare_dialog(self, dialog) -> None:
        try:
            self._compare_dialogs.remove(dialog)
        except ValueError:
            pass
        dialog.deleteLater()

    # ================================================================ 状态

    def _update_status(self) -> None:
        total = self.flow_store.rowCount()
        shown = self.proxy_model.rowCount()
        filtering = shown != total
        text = self.tr('共 {0} 条').format(total) + (self.tr(' · 显示 {0} 条').format(shown) if filtering else "")
        selected = len(self.traffic_table.selectionModel().selectedRows())
        if selected > 1:
            text += self.tr(' · 已选 {0} 条').format(selected)
        if self.search_bar.input.text():
            text += self.tr(' · 搜索「{0}」').format(self.search_bar.input.text())
        if self.traffic_table.is_sorted():
            text += self.tr(" · 已排序")
        if self.settings.throttle.enabled:
            text += self.tr(" · 弱网模拟中")
        self.count_label.setText(text)
        if filtering:
            self.count_label.setStyleSheet(
                f"color: {theme.css('warn')}; font-weight: bold;"
            )
        else:
            self.count_label.setStyleSheet("")

        if self.proxy.running:
            self.proxy_state_label.setText(
                self.tr('代理运行中 127.0.0.1:{0}').format(self.settings.proxy_port)
            )
            self.proxy_state_label.setStyleSheet(f"color: {theme.css('ok')};")
        else:
            self.proxy_state_label.setText(self.tr("代理未启动"))
            self.proxy_state_label.setStyleSheet(f"color: {theme.css('error')};")

        if self.cert_server is not None and self.cert_server.running:
            self.cert_state_label.setText(self.tr('证书服务 {0}').format(self.cert_server.url))
        else:
            self.cert_state_label.setText("")

        self._refresh_icons()
        self._update_capture_status()

    def _update_capture_status(self) -> None:
        """左下角抓包状态（对齐 Fiddler 左下 Capturing）：随代理与系统代理状态刷新。

        由 `_update_status` 统一调用——代理启停、主题切换（theme listener 指向
        `_update_status`）都会走到这里，颜色自动跟随主题。
        前面的圆点是画出来的（不是文案里的 ●/○ 字符——那种写法在不同字体
        下会变成方块或错位，见 visuals.StatusDotLabel）。
        """
        if self.proxy.running:
            if self._sysproxy_enabled():
                self.capture_label.setText(
                    self.tr('抓包中（系统代理 127.0.0.1:{0}）').format(self.settings.proxy_port)
                )
                self.capture_label.set_dot("ok")
                self.capture_label.setStyleSheet(
                    self.capture_label.dot_style("ok", "font-weight: bold;")
                )
            else:
                self.capture_label.setText(self.tr("抓包暂停（未接管系统代理）"))
                self.capture_label.set_dot("warn")
                self.capture_label.setStyleSheet(
                    self.capture_label.dot_style("warn")
                )
        else:
            self.capture_label.setText(self.tr("未抓包（代理未运行）"))
            self.capture_label.set_dot("hint")
            self.capture_label.setStyleSheet(
                self.capture_label.dot_style("hint")
            )

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
        """规则库变了 → 表格跟着变。

        不能是空实现：MCP 的 ``add_mock_rule`` 是从外部往库里加规则的，
        表格不刷新的话用户看到的还是旧列表，此时点「编辑/删除」会按
        **旧行号**映射到新列表的另一条规则上，静默改错。
        规则生效不靠这里（mock 引擎每请求实时读库），这里只管显示。

        走 singleShot(0) 而不是直接 refresh：避免在规则库自己的锁/回调
        链里重入表格重建，也顺带保证一定跑在主线程。
        """
        QTimer.singleShot(0, self.rules_panel.refresh)

    def _show_feedback(self) -> None:
        from app.ui.feedback_dialog import FeedbackDialog

        FeedbackDialog(self).exec()

    # ================================================================ 更新检测

    def _check_for_updates_manual(self) -> None:
        """帮助菜单「检查更新…」：无论结果如何都给反馈。"""
        self._start_update_check(manual=True)

    def _check_for_updates_silent(self) -> None:
        """启动时的静默检查：只在新版本时才弹窗，失败不打扰。"""
        self._start_update_check(manual=False)

    def _start_update_check(self, manual: bool) -> None:
        if self._update_checker is None:
            self._update_checker = UpdateChecker(self)
            self._update_checker.finished.connect(self._on_update_checked)
        self._update_manual = manual
        self._update_checker.check()

    def _on_update_checked(self, info, error: str) -> None:
        """检测完成：有新版本弹对话框；手动检查时无更新/失败也要说一声。"""
        from app.ui import dialogs
        from app.ui.update_dialog import UpdateDialog

        manual = self._update_manual
        self._update_manual = False

        if info is None:
            if manual:
                dialogs.information(
                    self,
                    self.tr("检查更新"),
                    self.tr("暂时无法获取版本信息：{0}").format(
                        error or self.tr("未知错误")
                    ),
                )
            return
        if not is_newer(info.version, CURRENT_VERSION):
            if manual:
                dialogs.information(
                    self,
                    self.tr("检查更新"),
                    self.tr("当前已是最新版本（{0}）。").format(CURRENT_VERSION),
                )
            return
        UpdateDialog(info, self, lang=self.settings.language).exec()

    def _show_about(self) -> None:
        from app import feedback as _fb

        QMessageBox.about(
            self,
            self.tr("关于"),
            self.tr('MiteProxy {0}\n\n基于 mitmproxy + PySide6 的抓包 / Mock 工具。\n支持 HTTP/HTTPS 抓包、Mock 规则、Fiddler 规则导入。').format(_fb.APP_VERSION),
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
        self.mcp.stop()                      # MCP 服务同样是进程内 HTTP
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
