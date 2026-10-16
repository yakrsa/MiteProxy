"""导入 Fiddler 规则预览对话框：布局回归。

盯一个真实 bug：表格所有列用 ResizeToContents 时，超长 URL 会把「匹配」列
撑到极宽，把第 0 列复选框和「名称」列一起挤没（用户截图里的"选择区域消失"）。
回归点：选择列固定宽度、URL 列可拖动而非按内容撑爆。
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-importdlg-test-home")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QHeaderView  # noqa: E402

from app.rules import EXACT, Action, Match, Rule  # noqa: E402
from app.ui.import_dialog import ImportPreviewDialog  # noqa: E402

_app = None


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _long_rule() -> Rule:
    r = Rule.create(name="超长URL规则")
    r.match = Match(
        type=EXACT,
        value=(
            "https://jy.umartsg.com/user-account-server-dolphin/api/ad/trad/"
            "very/long/path/segment/that/keeps/going/on/and/on?query=1&x=2"
        ),
        method="",
    )
    r.action = Action(status=200, headers={}, body_source="inline", body="ok")
    return r


def test_select_column_fixed_not_compressed(qapp):
    dlg = ImportPreviewDialog(
        [_long_rule()], [("跳过的", "仅延迟传递，MiteProxy 暂不支持")], "test.farx"
    )
    header = dlg.table.horizontalHeader()
    # 选择列固定宽度、resizeMode=Fixed：不随长 URL 被 ResizeToContents 吃掉
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Fixed
    assert dlg.table.columnWidth(0) >= 24
    # URL/动作列可拖动而非按内容撑爆
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(3) == QHeaderView.ResizeMode.Interactive


def test_selected_rules_roundtrip(qapp):
    dlg = ImportPreviewDialog([_long_rule()], [], "t")
    assert len(dlg.selected_rules()) == 1
    dlg._set_all_checked(False)
    assert dlg.selected_rules() == []


def test_skip_list_collapsed_by_default(qapp):
    """选择区域（规则表格）不能被长长的跳过清单挤压/盖没。"""
    from PySide6.QtWidgets import QScrollArea

    skipped = [
        (f"rule-{i}", "仅延迟传递，MiteProxy 暂不支持（需配合 mock/重定向动作）")
        for i in range(26)
    ]
    dlg = ImportPreviewDialog([_long_rule()], skipped, "t")
    lay = dlg.layout()
    # 规则表格占 stretch，优先拿垂直空间
    assert lay.stretch(lay.indexOf(dlg.table)) >= 1
    # 跳过清单默认收起（isHidden），不占选择区域高度
    scrolls = dlg.findChildren(QScrollArea)
    assert scrolls and all(s.isHidden() for s in scrolls)
    # 展开后才显示，再收起又隐藏
    dlg.skip_toggle.setChecked(True)
    assert not any(s.isHidden() for s in scrolls)
    dlg.skip_toggle.setChecked(False)
    assert all(s.isHidden() for s in scrolls)
