import pytest
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    win = MainWindow(restore_prompt=False)
    yield win
    win.close()


def _flow():
    from mitmproxy.test import tflow

    flow = tflow.tflow(resp=True)
    flow.request.url = "http://x.test/api/detail"
    return flow


def _detail_action(menu):
    return next(a for a in menu.actions() if "查看详情" in a.text())


def test_context_menu_has_view_detail(window, monkeypatch):
    flow = _flow()
    window.flow_store.append(window.capture.summarize(flow))
    monkeypatch.setattr(window, "_selected_flows", lambda: [flow])

    menu = window._build_table_context_menu([flow])
    assert any("查看详情" in a.text() for a in menu.actions())


def test_context_menu_detail_opens_dialog(window, monkeypatch):
    flow = _flow()
    window.flow_store.append(window.capture.summarize(flow))
    monkeypatch.setattr(window, "_selected_flows", lambda: [flow])

    called = {}
    monkeypatch.setattr(
        window, "_open_flow_detail",
        lambda f: called.setdefault("flow", f),
    )

    menu = window._build_table_context_menu([flow])
    action = _detail_action(menu)
    assert action.isEnabled()
    action.triggered.emit()
    assert called.get("flow") is flow


def test_context_menu_detail_disabled_when_multi(window, monkeypatch):
    from mitmproxy.test import tflow

    flows = [tflow.tflow(resp=True), tflow.tflow(resp=True)]
    window.flow_store.append(window.capture.summarize(flows[0]))
    window.flow_store.append(window.capture.summarize(flows[1]))
    monkeypatch.setattr(window, "_selected_flows", lambda: flows)

    menu = window._build_table_context_menu(flows)
    assert not _detail_action(menu).isEnabled()
