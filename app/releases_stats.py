"""GitHub Releases API 使用人数统计。

设计要点：

- **零依赖、免费**: 直接调用 GitHub Releases API，无需第三方服务；
- **静默上报**: 应用启动时自动上报一次，不打扰用户；
- **轻量级**: 仅记录「是否已上报」和「最后一次上报时间」到 settings.json；
- **复用现有网络栈**: 使用 QNetworkAccessManager，与更新检测、反馈功能同源。

统计口径：
- 首次启动时上报一次（视为一个活跃用户）；
- 每次大版本升级后的首次启动单独计数；
- GitHub Releases API 的 download_count 作为下载量参考。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from app.version import __version__
from app.settings import load_settings, save_settings, Settings

log = logging.getLogger(__name__)

# ==================================================================== 常量

GITHUB_REPO = "yakrsa/MiteProxy"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
STATS_REPORT_ENV = "MITEPROXY_STATS_REPORT"  # 环境变量控制上报行为

#: 单次网络请求超时（毫秒）
REQUEST_TIMEOUT_MS = 15_000

#: 统计状态在 settings.json 中的 key 前缀
STATS_SETTINGS_KEY = "release_stats"


# ==================================================================== 数据模型

class StatsReport:
    """统计上报数据载体。"""

    def __init__(
        self,
        version: str = "",
        platform: str = "",
        is_first_run: bool = False,
        download_count: int = 0,
    ):
        self.version = version or f"v{__version__}"
        self.platform = platform or self._detect_platform()
        self.is_first_run = is_first_run
        self.download_count = download_count
        self.reported_at = datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _detect_platform() -> str:
        """检测运行平台。"""
        import sys
        import platform as plat

        system = plat.system()
        machine = plat.machine()
        frozen = getattr(sys, "frozen", False)

        if system == "Darwin":
            return f"macOS-{machine}{' (bundled)' if frozen else ''}"
        elif system == "Windows":
            return f"Windows-{machine}{' (bundled)' if frozen else ''}"
        elif system == "Linux":
            distro = plat.linux_distribution(best=True)[0] if hasattr(plat, 'linux_distribution') else "Unknown"
            return f"Linux-{distro}-{machine}{' (bundled)' if frozen else ''}"
        else:
            return f"{system}-{machine}{' (bundled)' if frozen else ''}"


class StatsChecker(QObject):
    """异步检查版本下载量并触发上报。

    ``finished(current_version, download_count, error)``：
    - current_version: 当前版本号
    - download_count: 该版本的下载次数
    - error: 错误信息（成功为空串）
    """

    finished = Signal(str, int, str)

    def __init__(
        self,
        parent: QObject | None = None,
        url: str = RELEASES_API_URL,
        timeout_ms: int = REQUEST_TIMEOUT_MS,
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

    def check(self, current_version: str) -> bool:
        """发起一次检查；已在检测中则直接返回 False。"""
        if self._busy:
            return False
        self._busy = True

        request = QNetworkRequest(QUrl(self._url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setRawHeader(b"User-Agent", f"MiteProxy-Stats/{current_version}".encode())
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
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
            self._finish("", 0, "")
            return

        if reply.error() != QNetworkReply.NetworkError.NoError:
            message = reply.errorString()
            reply.deleteLater()
            self._finish("", 0, message)
            return

        raw = bytes(reply.readAll())
        reply.deleteLater()

        data = self._parse_response(raw)
        if data is None:
            self._finish("", 0, "releases API 响应格式异常")
            return

        # 查找当前版本的下载量
        version = f"v{__version__}"
        download_count = 0
        for release in data:
            tag = release.get("tag_name", "")
            if tag.lstrip("vV") == __version__:
                download_count = release.get("download_count", 0)
                break

        self._finish(version, int(download_count), "")

    def _parse_response(self, raw: bytes) -> list | None:
        """解析 GitHub Releases API 响应。"""
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            return None
        except (ValueError, TypeError):
            return None

    def _on_timeout(self) -> None:
        if self._reply is not None:
            self._reply.abort()
            return
        self._finish("", 0, "请求超时")

    def _finish(self, current_version: str, download_count: int, error: str) -> None:
        self._busy = False
        self.finished.emit(current_version, download_count, error)


# ==================================================================== 统计逻辑

def is_stats_enabled() -> bool:
    """检查是否启用了统计上报。"""
    # 环境变量覆盖（方便测试）
    env_val = STATS_REPORT_ENV.strip().lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True

    # 读取 settings.json
    try:
        settings = load_settings()
        stats_cfg = settings.to_dict().get(STATS_SETTINGS_KEY, {})
        return bool(stats_cfg.get("enabled", True))
    except Exception:
        return True


def should_report() -> bool:
    """判断是否需要上报。

    判定规则：
    - 统计功能未启用 → 不上报；
    - 从未上报过 → 上报；
    - 距离上次上报超过 24 小时 → 上报（避免频繁重复）；
    - 版本号变化 → 上报（大版本升级）。
    """
    if not is_stats_enabled():
        return False

    try:
        settings = load_settings()
        stats_cfg = settings.to_dict().get(STATS_SETTINGS_KEY, {})

        last_reported = stats_cfg.get("last_reported_at", "")
        current_version = f"v{__version__}"
        last_version = stats_cfg.get("version", "")

        # 版本号变化 → 上报
        if last_version != current_version:
            return True

        # 从未上报过 → 上报
        if not last_reported:
            return True

        # 距离上次上报超过 24 小时 → 上报
        try:
            last_dt = datetime.fromisoformat(last_reported)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            return elapsed > 86400  # 24 小时
        except (TypeError, ValueError):
            return True

    except Exception:
        return True


def get_current_stats() -> dict:
    """获取当前统计状态。"""
    try:
        settings = load_settings()
        stats_cfg = settings.to_dict().get(STATS_SETTINGS_KEY, {})
        return {
            "enabled": bool(stats_cfg.get("enabled", True)),
            "version": stats_cfg.get("version", f"v{__version__}"),
            "last_reported_at": stats_cfg.get("last_reported_at", ""),
            "total_reports": int(stats_cfg.get("total_reports", 0)),
            "download_count": int(stats_cfg.get("download_count", 0)),
        }
    except Exception:
        return {
            "enabled": True,
            "version": f"v{__version__}",
            "last_reported_at": "",
            "total_reports": 0,
            "download_count": 0,
        }


def record_report(download_count: int = 0) -> bool:
    """记录一次上报。

    Args:
        download_count: GitHub Releases 当前版本的下载次数

    Returns:
        bool: 是否成功
    """
    try:
        settings = load_settings()
        stats_cfg = settings.to_dict().get(STATS_SETTINGS_KEY, {})

        current_version = f"v{__version__}"
        stats_cfg["version"] = current_version
        stats_cfg["last_reported_at"] = datetime.now(timezone.utc).isoformat()
        stats_cfg["download_count"] = download_count
        stats_cfg["total_reports"] = int(stats_cfg.get("total_reports", 0)) + 1

        if not settings.to_dict().get(STATS_SETTINGS_KEY):
            settings_to_update = settings.to_dict()
            settings_to_update[STATS_SETTINGS_KEY] = stats_cfg
            settings_from_dict = Settings.__new__(Settings)
            settings_from_dict.__dict__ = settings_to_update
            return save_settings(settings_from_dict)

        # 更新配置
        existing = settings.to_dict()
        existing[STATS_SETTINGS_KEY] = stats_cfg

        # 重建 Settings 对象并保存
        from app.settings import Settings as SettingsCls
        new_settings = SettingsCls.from_dict(existing)
        return save_settings(new_settings)

    except Exception:
        log.exception("记录统计上报失败")
        return False


def record_report_v2(download_count: int = 0) -> bool:
    """记录一次上报（改进版）。"""
    try:
        settings = load_settings()
        d = settings.to_dict()

        # 初始化 stats_cfg
        if not d.get(STATS_SETTINGS_KEY):
            d[STATS_SETTINGS_KEY] = {}
        stats_cfg = d[STATS_SETTINGS_KEY]

        current_version = f"v{__version__}"
        stats_cfg["version"] = current_version
        stats_cfg["last_reported_at"] = datetime.now(timezone.utc).isoformat()
        stats_cfg["download_count"] = download_count
        stats_cfg["total_reports"] = int(stats_cfg.get("total_reports", 0)) + 1

        # 更新回 d
        d[STATS_SETTINGS_KEY] = stats_cfg

        # 直接更新 settings 对象的 __dict__ 并保存
        settings.__dict__.update(d)
        return save_settings(settings)

    except Exception:
        log.exception("记录统计上报失败")
        return False


# ==================================================================== 上报动作

def report_usage(download_count: int = 0, platform: str | None = None) -> tuple[bool, str]:
    """执行一次使用上报。

    Args:
        download_count: GitHub Releases 当前版本的下载次数
        platform: 运行平台（自动检测如果为 None）

    Returns:
        (success, message): 是否成功及提示信息
    """
    if not should_report():
        return True, "统计功能已启用，但本次无需上报"

    report = StatsReport(
        version=f"v{__version__}",
        platform=platform or StatsReport._detect_platform(),
        is_first_run=(get_current_stats().get("last_reported_at") == ""),
        download_count=download_count,
    )

    # 记录上报
    if record_report_v2(download_count):
        msg = f"使用统计已上报（版本 {report.version}，下载量 {download_count}）"
        return True, msg
    else:
        log.warning("统计上报数据记录失败，但不影响正常使用")
        return False, "统计上报数据记录失败"


def async_report(
    parent: QObject | None = None,
    nam: QNetworkAccessManager | None = None,
) -> StatsChecker:
    """异步检查并上报。

    Args:
        parent: 父对象
        nam: 网络管理器（可注入用于测试）

    Returns:
        StatsChecker 实例，其 finished 信号携带 (version, download_count, error)
    """
    checker = StatsChecker(parent=parent, nam=nam)
    checker.finished.connect(lambda ver, count, err: _on_stats_checked(ver, count, err))
    checker.check(f"v{__version__}")
    return checker


def _on_stats_checked(version: str, download_count: int, error: str) -> None:
    """统计检查完成后的回调。"""
    if error:
        log.info("统计检查完成（有网络错误，稍后重试）：%s", error)
    else:
        record_report_v2(download_count)
        log.info("统计检查完成：版本 %s，下载量 %d", version, download_count)


# ==================================================================== 控制接口

def enable_stats() -> bool:
    """启用统计上报。"""
    try:
        settings = load_settings()
        d = settings.to_dict()
        if not d.get(STATS_SETTINGS_KEY):
            d[STATS_SETTINGS_KEY] = {}
        d[STATS_SETTINGS_KEY]["enabled"] = True

        new_settings = Settings.from_dict(d)
        return save_settings(new_settings)
    except Exception:
        log.exception("启用统计失败")
        return False


def disable_stats() -> bool:
    """禁用统计上报。"""
    try:
        settings = load_settings()
        d = settings.to_dict()
        if not d.get(STATS_SETTINGS_KEY):
            d[STATS_SETTINGS_KEY] = {}
        d[STATS_SETTINGS_KEY]["enabled"] = False

        new_settings = Settings.from_dict(d)
        return save_settings(new_settings)
    except Exception:
        log.exception("禁用统计失败")
        return False


# ==================================================================== 测试用公开 API

def reset_stats() -> bool:
    """重置统计状态（用于测试或用户手动重置）。"""
    try:
        settings = load_settings()
        d = settings.to_dict()
        d[STATS_SETTINGS_KEY] = {
            "enabled": True,
            "version": f"v{__version__}",
            "last_reported_at": "",
            "total_reports": 0,
            "download_count": 0,
        }

        new_settings = Settings.from_dict(d)
        return save_settings(new_settings)
    except Exception:
        log.exception("重置统计状态失败")
        return False


if __name__ == "__main__":
    # 独立测试
    print(f"当前版本: v{__version__}")
    print(f"统计是否启用: {is_stats_enabled()}")
    print(f"是否需要上报: {should_report()}")
    print(f"当前统计状态: {get_current_stats()}")
