"""流量数据模型：QAbstractTableModel，持有 flow 摘要列表（UI 线程独占）。"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex
from PySide6.QtGui import QColor, QFont

from app.ui import theme

COLUMNS = [
    "#",
    "方法",
    "主机",
    "服务器 IP",
    "路径",
    "状态",
    "请求体",
    "响应",
    "耗时(ms)",
    "标记",
]
COL_ID, COL_METHOD, COL_HOST, COL_SERVER_IP = 0, 1, 2, 3
COL_PATH, COL_STATUS = 4, 5
COL_REQ_SIZE, COL_RESP_SIZE = 6, 7
COL_DURATION, COL_MARK = 8, 9

#: 排序专用 role。DisplayRole 里「大小」是 `4.2 KB`、「耗时」是格式化过的字符串，
#: 直接按显示文本排会出现 `1.3 MB` 排在 `812 B` 前面的笑话——所以排序一律走这个
#: role 取**原始数值**（见 FlowFilterProxyModel.lessThan）。
SORT_ROLE = Qt.ItemDataRole.UserRole + 1

MAX_ROWS = 5000  # 硬上限（Fiddler 对齐：最大 5000 条）
DEFAULT_MAX_ROWS = 5000

# mock 命中行整行着色（除「标记」列文字外，背景与文字都变）——琥珀底 + 琥珀字，
# 深浅主题各一套（theme.dynamic：主题切换时这两个 QColor 就地更新，
# 模型 data() 每次重绘重新取值，天然生效）。
# 只认 MOCK: 前缀：MapLocal 也会写 flow.marked（LOCAL:xxx），那不是 mock，
# 不该染成同一个颜色——否则"哪些是造数据"一眼看不出来。
MOCK_ROW_BG = theme.dynamic("mock_row_bg")
MOCK_ROW_FG = theme.dynamic("mock_row_fg")
MOCK_MARK_PREFIX = "MOCK:"

# URL 关键字高亮行整行底色（顶部「高亮」框实时命中，v1.15）。
# 青蓝底与 mock 琥珀、搜索黄、选中蓝区分；theme.dynamic 随主题切换就地更新。
HL_ROW_BG = theme.dynamic("hl_row_bg")


def _is_mock_row(row: dict) -> bool:
    return (row.get("marked") or "").startswith(MOCK_MARK_PREFIX)


def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


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
            if col == COL_MARK:
                # 用户备注优先（自己写的比系统徽标更想看见）；
                # MOCK 徽标次之；WebSocket 会话显示 WS；重放会话显示 REPLAY。
                # 备注与徽标同时存在时，徽标进 tooltip（见 ToolTipRole）。
                if row.get("comment"):
                    return row["comment"]
                if row["marked"]:
                    return row["marked"]
                if row.get("is_websocket"):
                    return f"WS {row.get('ws_messages', 0)}"
                return "REPLAY" if row.get("is_replay") else ""
            return None

        if role == Qt.ItemDataRole.BackgroundRole:
            # URL 关键字高亮优先于 mock 底色（用户主动指定的关注点更醒目）
            if self._is_highlighted(row):
                return HL_ROW_BG
            if _is_mock_row(row):
                # mock 命中的整行底色（含未选中态；选中时由系统选择色覆盖）
                return MOCK_ROW_BG

        if role == Qt.ItemDataRole.ForegroundRole:
            # 状态列保留语义色（绿/蓝/橙/红），优先于 mock 行色
            if col == COL_STATUS:
                color = status_color(row["status"])
                if color is not None:
                    return color
            if _is_mock_row(row):
                return MOCK_ROW_FG

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
                tip += f"\n服务器 IP: {ip}"
            if row.get("comment"):
                tip += f"\n备注: {row['comment']}"
            if row["marked"]:
                tip += f"\n{row['marked']}"
            if row.get("is_websocket"):
                tip += (
                    f"\nWebSocket：{row.get('ws_messages', 0)} 条消息"
                    + ("（已关闭）" if row.get("ws_closed") else "（连接中）")
                )
            return tip

        if role == Qt.ItemDataRole.UserRole:
            return row  # 供 filter/search 取原始数据
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
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
