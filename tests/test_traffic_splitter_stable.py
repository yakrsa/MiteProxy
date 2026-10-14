"""左右布局下切换请求，右侧详情面板不得左右漂移（splitter 稳定性）。

根因：QSplitter 会因子项 sizeHint / minimumSizeHint 变化触发重新分配。
详情面板内部的宽度意图随内容变化（长 URL 摘要、表单列宽 ResizeToContents、
图片/文本页签切换），导致 body 数据区域左右跳动。

修复：detail_panel 水平 sizePolicy = Ignored（不向 splitter 申报宽度意图），
配合显式最小宽度 200 防拖穿、childrenCollapsible=False 防折叠。
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QSizePolicy,
)


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    from app.ui.main_window import MainWindow

    w = MainWindow(restore_prompt=False)
    w.resize(1200, 800)
    w.show()
    yield w
    w.close()


def _flow_json():
    from mitmproxy.test import tflow

    f = tflow.tflow(resp=True)
    f.request.url = "http://x.test/api/json"
    f.response.headers["content-type"] = "application/json"
    f.response.content = b'{"status": 0, "data": {"list": [1, 2, 3]}}'
    return f


def _flow_long_url_form():
    from mitmproxy.test import tflow

    f = tflow.tflow(resp=True)
    f.request.url = (
        "http://x.test/api/form?token="
        + "a" * 40
        + "&sig=" + "b" * 30 + "&redirect_uri=https%3A%2F%2Fexample.com%2Fcb"
    )
    f.request.headers["content-type"] = "application/x-www-form-urlencoded"
    f.request.content = b"username=verylongusernamevalue&password=123456"
    f.response.headers["content-type"] = "text/html"
    f.response.content = b"<html><body>ok</body></html>"
    return f


def _flow_long_form_body():
    from mitmproxy.test import tflow

    f = tflow.tflow(resp=True)
    f.request.url = "http://x.test/api/post"
    f.request.headers["content-type"] = "application/x-www-form-urlencoded"
    f.request.content = b"field=" + b"z" * 300
    f.response.headers["content-type"] = "application/json"
    f.response.content = b'{"ok": true}'
    return f


def _flow_plain():
    from mitmproxy.test import tflow

    f = tflow.tflow(resp=True)
    f.request.url = "http://x.test/api/plain"
    f.response.headers["content-type"] = "text/plain"
    f.response.content = b"plain text body"
    return f


class TestSplitterStable:
    def test_horizontal_policy_ignored(self, win):
        policy = win.detail_panel.sizePolicy().horizontalPolicy()
        assert policy == QSizePolicy.Policy.Ignored

    def test_children_not_collapsible(self, win):
        assert win.traffic_splitter.childrenCollapsible() is False

    def test_detail_min_width(self, win):
        assert win.detail_panel.minimumWidth() >= 200

    def test_handle_stable_across_flows(self, win):
        """选不同请求（JSON / 长 URL 表单 / 长 form body / 纯文本），handle 不动。"""
        from PySide6.QtWidgets import QApplication

        win.traffic_splitter.setSizes([640, 500])
        QApplication.processEvents()
        baseline = win.traffic_splitter.sizes()
        assert baseline[0] > 0 and baseline[1] > 0

        for f in (
            _flow_json(),
            _flow_long_url_form(),
            _flow_long_form_body(),
            _flow_plain(),
        ):
            win.flow_store.append(win.capture.summarize(f))
            win.detail_panel.show_flow(f)
            QApplication.processEvents()
            assert win.traffic_splitter.sizes() == baseline, (
                f"切换到 {f.request.url[:40]} 时 splitter 被推动"
            )
