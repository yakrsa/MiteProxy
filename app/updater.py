"""更新检测：从 GitHub 仓库根目录的 `version.info` 读取最新版本信息。

设计要点：

- **单一事实源在仓库里**：仓库根放一份 ``version.info``（JSON），记录最新版本号
  与该版本的变更说明。客户端只读这个文件，不需要 GitHub API、不需要 token，
  也不会触发 API 速率限制。
- **版本号单点定义**：本模块从 ``app.feedback.APP_VERSION`` 派生当前版本，
  避免与「关于」对话框、打包 spec 里的版本各写一份而漂移。发版时改那一处即可。
- **异步 + 超时**：用 ``QNetworkAccessManager``（与反馈功能同一套路），
  不阻塞 UI；另配 QTimer 超时保护，避免网络挂死时一直转圈。
- **失败静默**：检测更新是锦上添花的功能，网络不通 / 文件损坏都不能影响主流程，
  因此解析与网络全部做容错，失败只返回错误信息交由调用方决定如何提示。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)

from app import feedback as _fb

#: 仓库与版本信息文件地址（raw 直读，无需 token / 不受 API 限流）
GITHUB_REPO = "yakrsa/MiteProxy"
VERSION_INFO_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.info"
)
#: 兜底的下载地址：version.info 没给 download_url 时跳 Release 首页
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"

#: 当前版本。来源唯一：app.feedback.APP_VERSION（形如 "v2.0.0"），这里去掉 v 前缀。
CURRENT_VERSION = _fb.APP_VERSION.lstrip("vV")

#: 单次检测的网络超时（毫秒）
CHECK_TIMEOUT_MS = 15_000


@dataclass(frozen=True)
class ChangeItem:
    """单条变更说明的双语载体。

    zh / en 分别为中文 / 英文文案；``localized()`` 按当前语言取对应文案，
    缺一门时回落到另一门，保证更新弹窗永远有内容可显示。
    """

    zh: str = ""
    en: str = ""

    def localized(self, lang: str) -> str:
        if lang == "en":
            return self.en or self.zh
        return self.zh or self.en


@dataclass(frozen=True)
class VersionInfo:
    """远端 version.info 解析结果。

    version 为必填；changes 允许为空（只发版本号不写变更也照样能提示）。
    changes 中的每条都是 :class:`ChangeItem`，同时携带中英文案。
    """

    version: str
    changes: list[ChangeItem] = field(default_factory=list)
    published_at: str = ""
    download_url: str = RELEASES_URL


# ---------------------------------------------------------------- 版本比较


def parse_version(text: str) -> tuple[int, ...]:
    """把版本号字符串拆成可用于比较的整数元组。

    只取数字段，因此 "v2.0.0" / "2.0.0" / "2.0.0-beta" 都能正确处理。
    解析不出任何数字时返回 ``(0,)``，保证比较不抛异常。
    """
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums) if nums else (0,)


def is_newer(remote: str, current: str) -> bool:
    """远端版本是否比当前版本新。

    位数不齐时按 0 补齐（"2.1" 与 "2.1.0" 视为相等），所以只有严格大于才算新版本。
    """
    a = parse_version(remote)
    b = parse_version(current)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


# ---------------------------------------------------------------- 解析


def parse_version_info(raw: bytes | str) -> VersionInfo | None:
    """解析 version.info 的内容；任何异常/缺字段都返回 None（交给调用方静默处理）。"""
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    version = str(data.get("version", "")).strip()
    if not version:  # 没有版本号就没法比较，视为无效
        return None

    raw_changes = data.get("changes") or []
    if isinstance(raw_changes, str):  # 容错：写作单个字符串也接受
        raw_changes = [raw_changes]
    changes = [_as_change_item(c) for c in raw_changes]
    # 中英文案都为空的条目直接丢弃，避免更新弹窗出现空行
    changes = [c for c in changes if c.zh or c.en]

    download = str(data.get("download_url", "")).strip() or RELEASES_URL
    return VersionInfo(
        version=version,
        changes=changes,
        published_at=str(data.get("published_at", "")).strip(),
        download_url=download,
    )


def _as_change_item(c) -> ChangeItem:
    """把 version.info 里的单条变更归一化为 ChangeItem。

    - 纯字符串：zh / en 同值（兼容旧版格式）。
    - 对象：分别取 zh / en；任一缺失时回落到另一门，避免空行。
    """
    if isinstance(c, str):
        text = c.strip()
        return ChangeItem(zh=text, en=text)
    if isinstance(c, dict):
        zh = str(c.get("zh", "")).strip()
        en = str(c.get("en", "")).strip()
        if not en:
            en = zh
        if not zh:
            zh = en
        return ChangeItem(zh=zh, en=en)
    return ChangeItem()


def localized_changes(info: VersionInfo, lang: str) -> list[str]:
    """按语言取出每条变更的展示文案（zh / en 自动选）。"""
    return [c.localized(lang) for c in info.changes]


# ---------------------------------------------------------------- 异步检测


class UpdateChecker(QObject):
    """异步拉取 version.info 并在 ``finished`` 信号里给出结果。

    ``finished(VersionInfo | None, str)``：第一个参数是解析结果（失败为 None），
    第二个是错误描述（成功为空串）。

    与反馈对话框同一套路：网络走 QNetworkAccessManager，不阻塞 UI。
    ``nam`` 可注入，便于测试用假的 manager 替代真实网络。
    """

    finished = Signal(object, str)

    def __init__(
        self,
        parent: QObject | None = None,
        url: str = VERSION_INFO_URL,
        timeout_ms: int = CHECK_TIMEOUT_MS,
        nam: QNetworkAccessManager | None = None,
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._timeout_ms = timeout_ms
        self._nam = nam if nam is not None else QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._busy = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    @property
    def busy(self) -> bool:
        return self._busy

    def check(self) -> bool:
        """发起一次检测；已在检测中则直接返回 False（不重复发请求）。"""
        if self._busy:
            return False
        self._busy = True

        request = QNetworkRequest(QUrl(self._url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setRawHeader(b"User-Agent", f"MiteProxy/{CURRENT_VERSION}".encode())
        # raw.githubusercontent 有缓存；显式绕开，保证改了 version.info 立刻生效
        request.setRawHeader(b"Cache-Control", b"no-cache")

        self._reply = self._nam.get(request)
        self._reply.finished.connect(self._on_finished)
        self._timer.start(self._timeout_ms)
        return True

    def _on_finished(self) -> None:
        self._timer.stop()
        reply = self._reply
        self._reply = None
        if reply is None:
            self._finish(None, "")
            return

        if reply.error() != QNetworkReply.NetworkError.NoError:
            message = reply.errorString()
            reply.deleteLater()
            self._finish(None, message)
            return

        raw = bytes(reply.readAll())
        reply.deleteLater()
        info = parse_version_info(raw)
        if info is None:
            self._finish(None, "version.info 格式无法解析")
            return
        self._finish(info, "")

    def _on_timeout(self) -> None:
        if self._reply is not None:
            self._reply.abort()  # 触发 finished，接着走 _on_finished 的错误分支
            return
        self._finish(None, "请求超时")

    def _finish(self, info: VersionInfo | None, error: str) -> None:
        self._busy = False
        self.finished.emit(info, error)
