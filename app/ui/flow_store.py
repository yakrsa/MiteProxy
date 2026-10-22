"""流量数据模型：QAbstractTableModel，持有 flow 摘要列表（UI 线程独占）。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QCoreApplication, Qt, QModelIndex
from PySide6.QtGui import QColor, QFont, QBrush

from app.ui import theme

#: 全部列（含可选列）。**列顺序即逻辑列号**，COL_* 常量与之一一对应；
#: 新增列只能追加到末尾——插中间会让存量设置（hidden_columns 用 key 存，
#: 不受影响）与测试里写死的列号全部错位。
COLUMNS = [
    "#",
    "方法",
    "host",
    "服务器 IP",
    "路径",
    "状态",
    "请求体",
    "响应",
    "耗时(ms)",
    "标记",
    # -- 可选列（默认隐藏，右键表头勾选显示，见 main_window._show_column_menu）
    "内容类型",
    "开始时刻",
    "备注",
]
COL_ID, COL_METHOD, COL_HOST, COL_SERVER_IP = 0, 1, 2, 3
COL_PATH, COL_STATUS = 4, 5
COL_REQ_SIZE, COL_RESP_SIZE = 6, 7
COL_DURATION, COL_MARK = 8, 9
COL_CONTENT_TYPE, COL_STARTED, COL_COMMENT = 10, 11, 12

#: 列的稳定 key（持久化 settings.hidden_columns 用）。**不能用列号**——
#: 以后加列时列号会漂移，key 不会。顺序与 COLUMNS 一致。
COLUMN_KEYS = (
    "num", "method", "host", "server_ip", "path", "status",
    "req_size", "resp_size", "duration", "mark",
    "content_type", "started", "comment",
)

#: 默认隐藏的可选列（内容类型 / 开始时刻 / 备注）：抓包主场景用不到，
#: 默认全开会让列表一下子宽三列；需要的人在表头右键里勾。
DEFAULT_HIDDEN_COLUMNS = ("content_type", "started", "comment")


def column_index(key: str) -> int | None:
    """列 key → 逻辑列号（未知 key 返回 None）。"""
    try:
        return COLUMN_KEYS.index(key)
    except ValueError:
        return None

#: 列头的翻译文案。**必须懒执行**：翻译器是在 app/main.py 里 QApplication
#: 创建之后才装载的，若在 import 时求值会永远拿到中文原文。
#: 字面量写死在这里（而不是 self.tr(变量)）是为了让 pyside6-lupdate 能抽到。
_column_labels_cache: list[str] | None = None


def column_labels() -> list[str]:
    """返回已翻译的列头文案（首次调用时求值并缓存）。"""
    global _column_labels_cache
    if _column_labels_cache is None:
        _column_labels_cache = [
            "#",
            QCoreApplication.translate("FlowStore", "方法"),
            "host",
            QCoreApplication.translate("FlowStore", "服务器 IP"),
            QCoreApplication.translate("FlowStore", "路径"),
            QCoreApplication.translate("FlowStore", "状态"),
            QCoreApplication.translate("FlowStore", "请求体"),
            QCoreApplication.translate("FlowStore", "响应"),
            QCoreApplication.translate("FlowStore", "耗时(ms)"),
            QCoreApplication.translate("FlowStore", "标记"),
            QCoreApplication.translate("FlowStore", "内容类型"),
            QCoreApplication.translate("FlowStore", "开始时刻"),
            QCoreApplication.translate("FlowStore", "备注"),
        ]
    return _column_labels_cache

#: 排序专用 role。DisplayRole 里「大小」是 `4.2 KB`、「耗时」是格式化过的字符串，
#: 直接按显示文本排会出现 `1.3 MB` 排在 `812 B` 前面的笑话——所以排序一律走这个
#: role 取**原始数值**（见 FlowFilterProxyModel.lessThan）。
SORT_ROLE = Qt.ItemDataRole.UserRole + 1

MAX_ROWS = 5000  # 硬上限（Fiddler 对齐：最大 5000 条）
DEFAULT_MAX_ROWS = 5000

# mock 命中行整行着色（除「标记」列文字外，背景与文字都变）——浅绿底 + 绿字，
# 深浅主题各一套（theme.dynamic：主题切换时这两个 QColor 就地更新，
# 模型 data() 每次重绘重新取值，天然生效）。
# 只认 MOCK 前缀（v1.15 徽标改为 MOCK#N:名称，两种都要认）：
# MapLocal 也会写 flow.marked（LOCAL:xxx），那不是 mock，不该染成同一个
# 颜色——否则"哪些是造数据"一眼看不出来。
MOCK_ROW_BG = theme.dynamic("mock_row_bg")
MOCK_ROW_FG = theme.dynamic("mock_row_fg")
MOCK_MARK_PREFIXES = ("MOCK:", "MOCK#")

# URL 关键字高亮行整行底色（顶部「高亮」框实时命中，v1.15）。
# 黄色：与 mock 浅绿底色相不同，深浅主题下都能分开；
# theme.dynamic 随主题切换就地更新。
HL_ROW_BG = theme.dynamic("hl_row_bg")
# 错误行（HTTP 4xx/5xx）整行红色——出问题的请求一眼定位。
ERR_ROW_BG = theme.dynamic("err_row_bg")
ERR_ROW_FG = theme.dynamic("err_row_fg")
# 斑马纹：全局 QSS 不再设 alternate-background-color（会压制模型背景），
# 改由模型在奇数行返回 alt_row 色，与旧 QSS 斑马纹视觉一致。
ALT_ROW_BG = theme.dynamic("alt_row")


def _is_mock_row(row: dict) -> bool:
    return (row.get("marked") or "").startswith(MOCK_MARK_PREFIXES)


def _is_error_row(row: dict) -> bool:
    """HTTP 错误行：4xx（客户端错误）+ 5xx（服务端错误）都算。

    连接层失败（status 为空/0）不着色——那更像「没响应」而不是「错误
    响应」，真失败时详情面板有明确提示，列表里全染红反而干扰。
    """
    try:
        return int(row.get("status") or 0) >= 400
    except (TypeError, ValueError):
        return False


def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def format_clock(ts) -> str:
    """epoch 秒 → 本地 `HH:MM:SS.mmm`（「开始时刻」列）。

    与详情页耗时页的绝对时刻同源（都是 time.time() 域的时间戳），
    毫秒截断而不是四舍五入——对账时要能和服务端日志逐位对上。
    无时间戳（0 / None）给 `-`，与「服务器 IP」列的无值显示一致。
    """
    if not ts:
        return "-"
    try:
        dt = datetime.fromtimestamp(float(ts))
    except (TypeError, ValueError, OSError, OverflowError):
        return "-"
    return dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


def status_color(status: int) -> QColor | None:
    if 200 <= status < 300:
        return theme.color("ok")      # 绿
    if 300 <= status < 400:
        return theme.color("info")    # 蓝
    if 400 <= status < 500:
        return theme.color("warn")    # 橙
    if status >= 500:
        return theme.color("error")   # 红
    return None


class FlowStore(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []
        self.max_rows = DEFAULT_MAX_ROWS
        self.highlight_keyword: str = ""  # URL 关键字高亮（命中行整行着色）

    # ------------------------------------------------------------ 高亮

    def set_highlight(self, keyword: str) -> None:
        """设置/清空 URL 关键字高亮（大小写不敏感的子串匹配）。

        空串 = 关闭高亮。实时生效：已显示的行走 dataChanged 重绘，
        新到达的流量在 data() 里即时比对（append 后无需任何额外处理）。
        """
        keyword = (keyword or "").strip()
        if keyword == self.highlight_keyword:
            return
        self.highlight_keyword = keyword
        if self.rows:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self.rows) - 1, len(COLUMNS) - 1)
            self.dataChanged.emit(top_left, bottom_right)

    def _is_highlighted(self, row: dict) -> bool:
        kw = self.highlight_keyword
        if not kw:
            return False
        return kw.lower() in (row.get("url") or "").lower()

    # ------------------------------------------------------------ Qt 模型接口

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(COLUMNS)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.rows)):
            return None
        row = self.rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_ID:
                return index.row() + 1
            if col == COL_METHOD:
                return row["method"]
            if col == COL_HOST:
                return row["host"]
            if col == COL_SERVER_IP:
                # 服务端 IP：CONNECT 隧道 / 未建连（mock 短路）时显示 -
                return row.get("server_ip") or "-"
            if col == COL_PATH:
                return row["path"]
            if col == COL_STATUS:
                return row["status"] or "-"
            if col == COL_REQ_SIZE:
                return format_size(row.get("req_size") or 0)
            if col == COL_RESP_SIZE:
                return format_size(row["size"])
            if col == COL_DURATION:
                return row["duration_ms"]
            if col == COL_CONTENT_TYPE:
                # 响应 content-type；无响应（pending / 连接失败）给 -
                return row.get("content_type") or "-"
            if col == COL_STARTED:
                # 请求开始的本地时钟（毫秒），与服务端日志对账用
                return format_clock(row.get("timestamp"))
            if col == COL_COMMENT:
                return row.get("comment") or ""
            if col == COL_MARK:
                # 用户备注优先（自己写的比系统徽标更想看见）；
                # MOCK 徽标次之；WebSocket 会话显示 WS；重放会话显示 REPLAY。
                # 备注与徽标同时存在时，徽标进 tooltip（见 ToolTipRole）。
                # 弱网延迟流量追加「弱网Xms」徽标（throttle 实际睡眠毫秒数）
                if row.get("comment"):
                    base = row["comment"]
                elif row["marked"]:
                    base = row["marked"]
                elif row.get("is_websocket"):
                    base = f"WS {row.get('ws_messages', 0)}"
                else:
                    base = "REPLAY" if row.get("is_replay") else ""
                throttle_ms = row.get("throttle_ms") or 0
                if throttle_ms:
                    tag = self.tr('弱网{0}ms').format(int(throttle_ms))
                    return f"{base} · {tag}" if base else tag
                return base
            return None

        if role == Qt.ItemDataRole.BackgroundRole:
            # 注意：BackgroundRole 必须返回 QBrush——直接给 QColor 时 Qt
            # 静默不上色（高亮/mock 行底色整个消失的根因）。每次调用现包
            # 一层 QBrush：theme.dynamic 的 QColor 就地更新也能取到新值。
            # 优先级：URL 高亮(黄) > 错误(红) > mock(浅绿) > 斑马纹
            if self._is_highlighted(row):
                return QBrush(HL_ROW_BG)
            if _is_error_row(row):
                return QBrush(ERR_ROW_BG)
            if _is_mock_row(row):
                # mock 命中的整行底色（含未选中态；选中时由系统选择色覆盖）
                return QBrush(MOCK_ROW_BG)
            if index.row() % 2 == 1:
                return QBrush(ALT_ROW_BG)

        if role == Qt.ItemDataRole.ForegroundRole:
            # 状态列保留语义色（绿/蓝/橙/红），优先于行色（同样必须 QBrush）
            if col == COL_STATUS:
                color = status_color(row["status"])
                if color is not None:
                    return QBrush(color)
            # 错误行整行红字（状态列除外，那列有自己语义色）
            if _is_error_row(row):
                return QBrush(ERR_ROW_FG)
            if _is_mock_row(row):
                return QBrush(MOCK_ROW_FG)

        if (
            role == Qt.ItemDataRole.FontRole
            and col == COL_MARK
            and _is_mock_row(row)
        ):
            font = QFont()
            font.setBold(True)
            return font

        if role == SORT_ROLE:
            # 排序键：数值列给数值，文本列给小写串（大小写不敏感）。
            # 数值列统一给数字，文本列统一给小写串——绝不混类型，否则
            # Python 里 int < str 会直接抛 TypeError（lessThan 里有兜底，但别依赖它）。
            if col == COL_ID:
                return index.row() + 1
            if col == COL_METHOD:
                return (row["method"] or "").lower()
            if col == COL_HOST:
                return (row["host"] or "").lower()
            if col == COL_SERVER_IP:
                return (row.get("server_ip") or "").lower()
            if col == COL_PATH:
                return (row["path"] or "").lower()
            if col == COL_STATUS:
                return int(row["status"] or 0)
            if col == COL_REQ_SIZE:
                return int(row.get("req_size") or 0)
            if col == COL_RESP_SIZE:
                return int(row["size"] or 0)
            if col == COL_DURATION:
                return float(row["duration_ms"] or 0.0)
            if col == COL_CONTENT_TYPE:
                return (row.get("content_type") or "").lower()
            if col == COL_STARTED:
                return float(row.get("timestamp") or 0.0)
            if col == COL_COMMENT:
                return (row.get("comment") or "").lower()
            if col == COL_MARK:
                key = row.get("comment") or row["marked"] or (
                    "REPLAY" if row.get("is_replay") else ""
                )
                return key.lower()
            return ""

        if role == Qt.ItemDataRole.ToolTipRole:
            tip = f"{row['method']} {row['url']}"
            ip = row.get("server_ip")
            if ip:
                tip += self.tr('\n服务器 IP: {0}').format(ip)
            if row.get("comment"):
                tip += self.tr("\n备注: {0}").format(row["comment"])
            if row["marked"]:
                tip += f"\n{row['marked']}"
            if row.get("throttle_ms"):
                tip += self.tr("\n弱网延迟: {0} ms").format(round(row["throttle_ms"], 1))
            if row.get("is_websocket"):
                tip += (
                    self.tr("\nWebSocket：{0} 条消息").format(row.get("ws_messages", 0))
                    + (self.tr("（已关闭）") if row.get("ws_closed") else self.tr("（连接中）"))
                )
            return tip

        if role == Qt.ItemDataRole.UserRole:
            return row  # 供 filter/search 取原始数据
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return column_labels()[section]
        return None

    # ------------------------------------------------------------ 数据操作（UI 线程调用）

    def append(self, summary: dict) -> None:
        first = len(self.rows)
        self.beginInsertRows(QModelIndex(), first, first)
        self.rows.append(summary)
        self.endInsertRows()
        self._evict_if_needed()

    def update(self, summary: dict) -> bool:
        """原地替换同一条会话的摘要（WebSocket 消息到达时用）。

        整行替换而不是逐格改：摘要里 size / duration / 消息数 是一起变的，
        用 dataChanged 打整行，代理模型的排序也会一并重算。
        """
        flow_id = summary.get("id")
        for i, row in enumerate(self.rows):
            if row.get("id") == flow_id:
                self.rows[i] = summary
                top_left = self.index(i, 0)
                bottom_right = self.index(i, len(COLUMNS) - 1)
                self.dataChanged.emit(top_left, bottom_right)
                return True
        return False

    def clear(self) -> None:
        self.beginResetModel()
        self.rows.clear()
        self.endResetModel()

    def remove_ids(self, flow_ids) -> int:
        """按 id 删除若干行，返回实际删除条数。

        只动列表显示——不动 capture 缓存：缓存是按容量自淘汰的查询缓存，
        留着不影响界面，也让「删除后仍想看详情/对比」不至于立刻失效。
        整段替换（begin/endResetModel）而不是逐行 removeRow：删除通常是
        批量动作，逐行发号会让排序/过滤连着重算 N 遍。
        """
        ids = set(flow_ids)
        if not ids:
            return 0
        keep = [r for r in self.rows if r.get("id") not in ids]
        removed = len(self.rows) - len(keep)
        if not removed:
            return 0
        self.beginResetModel()
        self.rows = keep
        self.endResetModel()
        return removed

    def set_comment(self, flow_id: str, comment: str) -> bool:
        """给一条会话写/清用户备注（只动「标记」列，不重建整行）。

        走 dataChanged 而不是整体替换：备注是纯显示信息，动整行会让排序
        白重算一遍，还打断用户正在做的选择。
        """
        for i, row in enumerate(self.rows):
            if row.get("id") == flow_id:
                if row.get("comment") == comment:
                    return True
                row["comment"] = comment
                idx = self.index(i, COL_MARK)
                self.dataChanged.emit(idx, idx)
                return True
        return False

    def row_data(self, row: int) -> dict | None:
        if 0 <= row < len(self.rows):
            return self.rows[row]
        return None

    def all_rows(self) -> list[dict]:
        return list(self.rows)

    # ------------------------------------------------------------ 容量（保存条数）

    def set_max_rows(self, limit: int) -> None:
        """改保存条数上限（100~5000）；立即从最旧一端裁到新上限。

        只在 UI 线程调用——rows 是 UI 线程独占数据，无跨线程问题。
        """
        self.max_rows = max(1, min(int(limit), MAX_ROWS))
        self._trim_to_limit()

    # ------------------------------------------------------------ 内部

    def _trim_to_limit(self) -> None:
        over = len(self.rows) - self.max_rows
        if over <= 0:
            return
        self.beginRemoveRows(QModelIndex(), 0, over - 1)
        del self.rows[:over]
        self.endRemoveRows()

    def _evict_if_needed(self) -> None:
        # 精确裁到上限：列表上限 5000 条，del 头部一次的内存移动成本可忽略，
        # 换来「保存条数」语义精确（旧实现批量淘汰 10% 会掉到上限以下）
        self._trim_to_limit()
