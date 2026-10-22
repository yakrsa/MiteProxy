"""应用设置持久化（DESIGN.md 4.3）：~/.miteproxy/settings.json。

与 rules.json 分离：规则是可迁移资产（可导出分享），设置是本机偏好。
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from app.i18n import DEFAULT_LANG, SUPPORTED, normalize
from app.network import MapRule, ThrottleConfig, rules_from_dicts, rules_to_dicts
from app.rules import CONFIG_DIR
from app.mcpserver import DEFAULT_MCP_HOST, DEFAULT_MCP_PORT
from app.ui.filter_model import FilterConfig
from app.ui.flow_store import COLUMN_KEYS, DEFAULT_HIDDEN_COLUMNS

SETTINGS_PATH = CONFIG_DIR / "settings.json"

DEFAULT_PROXY_PORT = 8888   # 对齐 Fiddler 默认端口
DEFAULT_CERT_PORT = 8081

# 流量列表「保存条数」可选项（对齐 Fiddler 的会话上限设置，上限 5000）
FLOW_LIMIT_CHOICES = (100, 200, 500, 1000, 2000, 3000, 5000)
DEFAULT_MAX_FLOWS = 5000


def _host(value) -> str:
    """规范化监听地址：手改 settings.json 写坏（空串 / 带空格 / 非字符串）
    时回落默认，别让服务启动时才炸。"""
    text = str(value or "").strip()
    return text or DEFAULT_MCP_HOST


def sanitize_max_flows(value) -> int:
    """把配置里的保存条数收敛到允许档位；无法解析时用默认上限。

    手改 settings.json 写了个中间值（如 800）时按就近档位取值，
    而不是静默丢弃 → 用户改完能看到生效。
    """
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_FLOWS
    if n in FLOW_LIMIT_CHOICES:
        return n
    return min(FLOW_LIMIT_CHOICES, key=lambda c: (abs(c - n), c))


@dataclass
class BreakpointConfig:
    """断点调试开关（Fiddler 的 Before Requests / After Responses）。

    - ``on_request``：请求发往服务器前暂停（可改 URL / headers / body）；
    - ``on_response``：响应返回客户端前暂停（可改状态码 / headers / body）；
    - ``url_keywords``：只拦截 URL 含任一关键词的会话，留空 = 全部拦截。
    """
    enabled: bool = False
    on_request: bool = True
    on_response: bool = False
    url_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "on_request": self.on_request,
            "on_response": self.on_response,
            "url_keywords": list(self.url_keywords),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "BreakpointConfig":
        d = data or {}
        return cls(
            enabled=bool(d.get("enabled", False)),
            on_request=bool(d.get("on_request", True)),
            on_response=bool(d.get("on_response", False)),
            url_keywords=[str(k) for k in (d.get("url_keywords") or [])],
        )

    def matches(self, url: str) -> bool:
        """URL 是否命中拦截范围（未启用关键词 = 全拦）。"""
        if not self.url_keywords:
            return True
        low = (url or "").lower()
        return any(k.lower() in low for k in self.url_keywords if k)


@dataclass
class Settings:
    proxy_port: int = DEFAULT_PROXY_PORT
    cert_port: int = DEFAULT_CERT_PORT
    max_flows: int = DEFAULT_MAX_FLOWS
    filter: FilterConfig = field(default_factory=FilterConfig)
    #: 过滤预设（路线图 #7）：命名保存多套过滤条件，切换场景不用重填。
    #: 每个元素 `{"name": str, "config": FilterConfig.to_dict()}`。
    #: `active_preset` 记录当前套用的预设名（"" = 当前过滤不来自任何预设，
    #: 用户手改过之后也是 ""——手改即视为偏离预设）。
    filter_presets: list[dict] = field(default_factory=list)
    active_preset: str = ""
    #: 弱网模拟档位（延迟 + 限速）
    throttle: ThrottleConfig = field(default_factory=ThrottleConfig)
    #: 断点调试（请求前 / 响应前暂停会话，改完再放行）
    breakpoint: BreakpointConfig = field(default_factory=BreakpointConfig)
    #: MCP 接口：把最近抓包暴露给 AI 客户端（默认关）
    mcp_enabled: bool = False
    mcp_port: int = DEFAULT_MCP_PORT
    #: 监听地址：默认 127.0.0.1（仅本机）；改 0.0.0.0 或具体网卡 IP 才对局域网开放
    mcp_host: str = DEFAULT_MCP_HOST
    #: MCP 写操作（add_mock_rule / replay_flow / set_breakpoint）。默认关：
    #     能把改写流量行为的能力交给外部客户端，必须用户显式授权
    mcp_write_enabled: bool = False
    #: 域名映射规则（把线上域名转发到本地服务）
    map_rules: list[MapRule] = field(default_factory=list)
    #: 退出时自动把本次会话快照到 last-session.jsonl（下次启动可一键恢复）。
    #: 默认关闭：会话始终在内存，只有退出时才异步落盘（避免大流量时写盘拖慢 UI）；
    #: 需要持久化时在「设置 → 自动保存会话」打开，仍是内存优先、退出/手动时落盘。
    auto_save_session: bool = False
    #: 会话文件对话框的起始目录（记住上次位置，省得每次找）
    last_session_dir: str = ""
    #: 流量列表自动滚动：新会话到达时滚到"最新端"。
    #: 只在用户本来就停在最新端时才滚——否则会把人手动翻的位置抢走。
    auto_scroll: bool = True
    #: 新的会话显示在顶部（倒序）；False = 到达顺序，新的在底部
    newest_first: bool = False
    #: body 默认自动换行（超长单行会被闸门临时关掉，见 app/bodyview）
    body_wrap: bool = True
    #: 启动代理时自动把系统代理指向本应用、停止/退出时还原
    #: （对齐 Fiddler「Act as System Proxy」；macOS 需一次管理员授权）
    auto_system_proxy: bool = True
    #: 流量页布局方向：True = 左右（Fiddler 风格，列表在左）；False = 上下
    traffic_side_by_side: bool = True
    #: 主题档位：system（跟随系统）/ light / dark（app/ui/theme.py THEME_MODES）
    theme: str = "system"
    #: 界面语言：zh_CN（源语言，默认）/ en（app/i18n.SUPPORTED）。
    #: 切换后重启生效（入口在创建 MainWindow 前装好翻译器）。
    language: str = DEFAULT_LANG
    #: 启动时静默检查更新（读仓库根 version.info）；只在确实有新版时才弹窗，
    #: 网络不通/文件损坏一律静默，不打扰抓包主流程。手动检查不受此项影响。
    check_update_on_startup: bool = True
    #: 流量页分隔条位置（QSplitter.saveState()，base64 落盘）
    splitter_state: bytes | None = None
    window_geometry: bytes | None = None
    #: 用户脚本启用态 {脚本名: 是否启用}（app/scripts.py）。缺省视为启用——
    #: 文件在 scripts/ 目录里、用户没显式关过就该跑
    scripts: dict[str, bool] = field(default_factory=dict)
    #: 流量列表隐藏的列（列 key，见 flow_store.COLUMN_KEYS）。
    #: 用 key 不用列号：以后加列时列号会漂移，key 不会。
    #: 默认隐藏内容类型 / 开始时刻 / 备注三个可选列（见 DEFAULT_HIDDEN_COLUMNS）。
    hidden_columns: list[str] = field(
        default_factory=lambda: list(DEFAULT_HIDDEN_COLUMNS)
    )

    def to_dict(self) -> dict:
        return {
            "proxy_port": self.proxy_port,
            "cert_port": self.cert_port,
            "max_flows": self.max_flows,
            "filter": self.filter.to_dict(),
            "filter_presets": [dict(p) for p in self.filter_presets],
            "active_preset": self.active_preset,
            "throttle": self.throttle.to_dict(),
            "breakpoint": self.breakpoint.to_dict(),
            "mcp_enabled": self.mcp_enabled,
            "mcp_port": self.mcp_port,
            "mcp_host": self.mcp_host,
            "mcp_write_enabled": self.mcp_write_enabled,
            "map_remote": rules_to_dicts(self.map_rules),
            "auto_save_session": self.auto_save_session,
            "last_session_dir": self.last_session_dir,
            "auto_scroll": self.auto_scroll,
            "newest_first": self.newest_first,
            "body_wrap": self.body_wrap,
            "auto_system_proxy": self.auto_system_proxy,
            "traffic_side_by_side": self.traffic_side_by_side,
            "theme": self.theme,
            "language": self.language,
            "check_update_on_startup": self.check_update_on_startup,
            # splitter_state / geometry 是 QByteArray，base64 成文本落盘
            "splitter_state": (
                base64.b64encode(self.splitter_state).decode("ascii")
                if self.splitter_state
                else None
            ),
            # geometry 是 QByteArray，base64 成文本落盘（启动时恢复窗口位置）
            "window_geometry": (
                base64.b64encode(self.window_geometry).decode("ascii")
                if self.window_geometry
                else None
            ),
            "hidden_columns": list(self.hidden_columns),
            "scripts": dict(self.scripts),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        def _int(value, default: int) -> int:
            # 手工编辑 settings.json 写坏数字时回落默认值，不能让启动崩掉
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        port = _int(data.get("proxy_port", DEFAULT_PROXY_PORT), DEFAULT_PROXY_PORT)
        cert_port = _int(data.get("cert_port", DEFAULT_CERT_PORT), DEFAULT_CERT_PORT)
        return cls(
            proxy_port=port,
            cert_port=cert_port,
            max_flows=sanitize_max_flows(data.get("max_flows", DEFAULT_MAX_FLOWS)),
            filter=FilterConfig.from_dict(data.get("filter") or {}),
            filter_presets=cls._sanitize_presets(data.get("filter_presets")),
            active_preset=str(data.get("active_preset") or ""),
            throttle=ThrottleConfig.from_dict(data.get("throttle") or {}),
            breakpoint=BreakpointConfig.from_dict(data.get("breakpoint")),
            mcp_enabled=bool(data.get("mcp_enabled", False)),
            mcp_port=_int(data.get("mcp_port", DEFAULT_MCP_PORT), DEFAULT_MCP_PORT),
            mcp_host=_host(data.get("mcp_host", DEFAULT_MCP_HOST)),
            mcp_write_enabled=bool(data.get("mcp_write_enabled", False)),
            map_rules=rules_from_dicts(data.get("map_remote")),
            auto_save_session=bool(data.get("auto_save_session", True)),
            last_session_dir=str(data.get("last_session_dir") or ""),
            auto_scroll=bool(data.get("auto_scroll", True)),
            newest_first=bool(data.get("newest_first", False)),
            body_wrap=bool(data.get("body_wrap", True)),
            auto_system_proxy=bool(data.get("auto_system_proxy", True)),
            traffic_side_by_side=bool(data.get("traffic_side_by_side", True)),
            theme=(
                data["theme"] if data.get("theme") in ("system", "light", "dark")
                else "system"
            ),
            language=normalize(data.get("language", DEFAULT_LANG)),
            check_update_on_startup=bool(data.get("check_update_on_startup", True)),
            splitter_state=cls._decode_b64(data.get("splitter_state")),
            window_geometry=cls._decode_geometry(data.get("window_geometry")),
            hidden_columns=cls._sanitize_columns(data.get("hidden_columns")),
            scripts=cls._sanitize_scripts(data.get("scripts")),
        )

    @staticmethod
    def _sanitize_scripts(value) -> dict:
        """清洗脚本启用态：键名限字符串、值限布尔（手改坏的不崩）。"""
        if not isinstance(value, dict):
            return {}
        return {str(k): bool(v) for k, v in value.items() if str(k)}

    @staticmethod
    def _sanitize_columns(value) -> list[str]:
        """过滤出合法的列 key（手改 settings.json 写错时不崩，忽略未知项）。"""
        if not isinstance(value, list):
            return list(DEFAULT_HIDDEN_COLUMNS)
        keys = [str(k) for k in value if str(k) in COLUMN_KEYS]
        return keys

    @staticmethod
    def _sanitize_presets(value) -> list[dict]:
        """清洗过滤预设：丢坏条目、去重名（保留先出现的），config 逐字段收敛。

        手改 settings.json 写出 `{"name": 123}` 这类条目时不能让它把
        启动搞崩——预设是增强功能，坏一份就丢一份。
        """
        if not isinstance(value, list):
            return []
        presets: list[dict] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            try:
                config = FilterConfig.from_dict(item.get("config") or {})
            except Exception:
                continue
            seen.add(name)
            presets.append({"name": name, "config": config.to_dict()})
        return presets

    @staticmethod
    def _decode_b64(value) -> bytes | None:
        """base64 文本 → bytes（geometry / splitter_state 共用）；坏数据回落 None。"""
        if not value:
            return None
        try:
            return base64.b64decode(str(value))
        except (ValueError, TypeError):
            return None

    @classmethod
    def _decode_geometry(cls, value) -> bytes | None:
        return cls._decode_b64(value)


def load_settings() -> Settings:
    if not SETTINGS_PATH.exists():
        return Settings()
    try:
        return Settings.from_dict(
            json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, OSError):
        return Settings()


def save_settings(settings: Settings) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, SETTINGS_PATH)
    except OSError:
        pass  # 设置写入失败不致命
