"""更新检测（app/updater.py）的单元测试。

网络部分用可注入的假 QNetworkAccessManager 替代真实请求：
UpdateChecker 的 ``nam`` 参数就是为此留的口子（与反馈对话框的 transport 同思路）。
"""

from __future__ import annotations

import json
import time

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkReply

from app.ui.update_dialog import UpdateDialog
from app.updater import (
    CURRENT_VERSION,
    RELEASES_URL,
    ChangeItem,
    VersionInfo,
    UpdateChecker,
    is_newer,
    localized_changes,
    parse_version,
    parse_version_info,
)


@pytest.fixture()
def qapp():
    """QApplication 实例（各测试文件自带，本项目没有全局 conftest 提供）。"""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------- 假网络层


class _FakeReply(QObject):
    """最小的 QNetworkReply 替身：只需实现 UpdateChecker 用到的那几个方法。"""

    finished = Signal()

    def __init__(self, payload: bytes = b"", error=None, error_string: str = ""):
        super().__init__()
        self._payload = payload
        self._error = error or QNetworkReply.NetworkError.NoError
        self._error_string = error_string

    def error(self):
        return self._error

    def errorString(self):
        return self._error_string

    def readAll(self):
        return self._payload

    def deleteLater(self):
        pass

    def abort(self):
        self.finished.emit()


class _FakeNAM:
    def __init__(self, reply: _FakeReply):
        self._reply = reply
        self.requests: list = []

    def get(self, request):
        self.requests.append(request)
        return self._reply


def _payload(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------- 版本比较


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2.0.0", (2, 0, 0)),
        ("v2.0.0", (2, 0, 0)),
        ("2.0.0-beta", (2, 0, 0)),
        ("", (0,)),
        ("abc", (0,)),
    ],
)
def test_parse_version(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize(
    "remote, current, expected",
    [
        ("2.0.1", "2.0.0", True),
        ("2.1.0", "2.0.0", True),
        ("3.0.0", "2.9.9", True),
        ("2.0.0", "2.0.0", False),   # 相同不算新
        ("1.9.9", "2.0.0", False),   # 更旧不算新
        ("2.0", "2.0.0", False),     # 位数不齐按 0 补齐 -> 相等
        ("v2.0.1", "2.0.0", True),   # 容错 v 前缀
    ],
)
def test_is_newer(remote, current, expected):
    assert is_newer(remote, current) is expected


# ---------------------------------------------------------------- 解析


def test_parse_version_info_full():
    info = parse_version_info(
        _payload(
            {
                "version": "2.1.0",
                "published_at": "2026-10-20",
                "download_url": "https://example.com/dl",
                "changes": [
                    {"zh": "新增 A", "en": "Added A"},
                    {"zh": "修复 B", "en": "Fixed B"},
                ],
            }
        )
    )
    assert info is not None
    assert info.version == "2.1.0"
    assert info.changes == [
        ChangeItem(zh="新增 A", en="Added A"),
        ChangeItem(zh="修复 B", en="Fixed B"),
    ]
    assert info.published_at == "2026-10-20"
    assert info.download_url == "https://example.com/dl"


def test_parse_version_info_change_missing_en_falls_back():
    """changes 里缺 en 时回落到 zh，英文界面不会空白。"""
    info = parse_version_info(
        _payload(
            {
                "version": "2.1.0",
                "changes": [{"zh": "只有中文"}, {"en": "only english"}],
            }
        )
    )
    assert info is not None
    assert info.changes == [
        ChangeItem(zh="只有中文", en="只有中文"),
        ChangeItem(zh="only english", en="only english"),
    ]


def test_localized_changes_picks_language():
    info = VersionInfo(
        version="2.1.0",
        changes=[
            ChangeItem(zh="中文甲", en="English A"),
            ChangeItem(zh="中文乙", en="English B"),
        ],
    )
    assert localized_changes(info, "zh_CN") == ["中文甲", "中文乙"]
    assert localized_changes(info, "en") == ["English A", "English B"]
    # 缺 en 时回落到 zh
    only_zh = VersionInfo(version="2.1.0", changes=[ChangeItem(zh="仅中文")])
    assert localized_changes(only_zh, "en") == ["仅中文"]


def test_parse_version_info_defaults_download_url():
    """没给 download_url 时兜底到 Release 首页，保证「前往下载」总有去处。"""
    info = parse_version_info(_payload({"version": "2.1.0"}))
    assert info is not None
    assert info.changes == []
    assert info.download_url == RELEASES_URL


def test_parse_version_info_changes_as_single_string():
    info = parse_version_info(_payload({"version": "2.1.0", "changes": "只有一条"}))
    assert info is not None
    assert info.changes == [ChangeItem(zh="只有一条", en="只有一条")]


@pytest.mark.parametrize(
    "raw",
    [
        b"not json at all",
        b"",
        b"[1, 2, 3]",              # 是 JSON 但不是对象
        b'{"changes": ["x"]}',     # 缺 version：没法比较，视为无效
        b'{"version": ""}',
        b"\xff\xfe\x00bad",        # 非 UTF-8
    ],
)
def test_parse_version_info_invalid(raw):
    assert parse_version_info(raw) is None


def test_parse_version_info_accepts_str():
    assert parse_version_info('{"version": "2.1.0"}').version == "2.1.0"


# ---------------------------------------------------------------- 异步检测


def test_check_emits_info_on_success(qapp):
    reply = _FakeReply(payload=_payload({"version": "9.9.9", "changes": ["x"]}))
    nam = _FakeNAM(reply)
    checker = UpdateChecker(nam=nam)

    seen: list = []
    checker.finished.connect(lambda info, err: seen.append((info, err)))
    assert checker.check() is True
    reply.finished.emit()

    assert len(seen) == 1
    info, err = seen[0]
    assert err == ""
    assert info.version == "9.9.9"
    assert checker.busy is False


def test_check_reports_network_error(qapp):
    reply = _FakeReply(
        error=QNetworkReply.NetworkError.HostNotFoundError,
        error_string="Host not found",
    )
    checker = UpdateChecker(nam=_FakeNAM(reply))

    seen: list = []
    checker.finished.connect(lambda info, err: seen.append((info, err)))
    checker.check()
    reply.finished.emit()

    assert seen[0][0] is None
    assert "Host not found" in seen[0][1]


def test_check_reports_unparsable_payload(qapp):
    reply = _FakeReply(payload=b"<html>404</html>")
    checker = UpdateChecker(nam=_FakeNAM(reply))

    seen: list = []
    checker.finished.connect(lambda info, err: seen.append((info, err)))
    checker.check()
    reply.finished.emit()

    assert seen[0][0] is None
    assert seen[0][1]


def test_check_is_not_reentrant(qapp):
    """一次检测未完成时再调 check() 应被拒绝，避免重复发请求。"""
    reply = _FakeReply(payload=_payload({"version": "9.9.9"}))
    checker = UpdateChecker(nam=_FakeNAM(reply))
    checker.finished.connect(lambda info, err: None)

    assert checker.check() is True
    assert checker.check() is False
    reply.finished.emit()
    assert checker.check() is True   # 完成后可以再发


def test_check_timeout_emits_error(qapp):
    """网络挂死时超时分支要给出错误，而不是永远静默。"""
    reply = _FakeReply()
    checker = UpdateChecker(nam=_FakeNAM(reply), timeout_ms=1)

    seen: list = []
    checker.finished.connect(lambda info, err: seen.append((info, err)))
    checker.check()

    # 等超时定时器触发（QTimer 需要事件循环；最多等约 2 秒避免测试挂死）
    for _ in range(200):
        qapp.processEvents()
        if seen:
            break
        time.sleep(0.01)

    assert seen, "超时后应触发 finished"
    assert seen[0][0] is None


# ---------------------------------------------------------------- 对话框


def test_update_dialog_shows_changes(qapp):
    info = VersionInfo(
        version="2.1.0",
        changes=[
            ChangeItem(zh="新增 A", en="Added A"),
            ChangeItem(zh="修复 B", en="Fixed B"),
        ],
        published_at="2026-10-20",
    )
    dlg = UpdateDialog(info)
    assert dlg.windowTitle() == "发现新版本"

    # 变更条目应逐条展示（带 • 前缀），默认中文
    from PySide6.QtWidgets import QListWidget

    texts = []
    lst = dlg.findChild(QListWidget)
    assert lst is not None
    for i in range(lst.count()):
        texts.append(lst.item(i).text())
    assert any("新增 A" in t for t in texts)
    assert any("修复 B" in t for t in texts)


def test_update_dialog_shows_changes_in_english(qapp):
    """传入 lang="en" 时变更列表应显示英文文案，而非中文。"""
    info = VersionInfo(
        version="2.1.0",
        changes=[
            ChangeItem(zh="新增 A", en="Added A"),
            ChangeItem(zh="修复 B", en="Fixed B"),
        ],
    )
    dlg = UpdateDialog(info, lang="en")
    from PySide6.QtWidgets import QListWidget

    lst = dlg.findChild(QListWidget)
    assert lst is not None
    texts = [lst.item(i).text() for i in range(lst.count())]
    assert any("Added A" in t for t in texts)
    assert any("Fixed B" in t for t in texts)
    assert not any("新增 A" in t for t in texts)


def test_update_dialog_handles_empty_changes(qapp):
    """远端没写 changes 时也要有占位文案，不能是一片空白。"""
    dlg = UpdateDialog(VersionInfo(version="2.1.0"))
    from PySide6.QtWidgets import QListWidget

    lst = dlg.findChild(QListWidget)
    assert lst.count() == 1
    assert lst.item(0).text()


def test_current_version_matches_repo_file():
    """仓库根的 version.info 应与当前版本一致（发版时同步改这两处）。"""
    import pathlib

    raw = (pathlib.Path(__file__).resolve().parent.parent / "version.info").read_bytes()
    info = parse_version_info(raw)
    assert info is not None
    assert info.version == CURRENT_VERSION
    assert info.changes, "version.info 应至少写一条变更说明"
