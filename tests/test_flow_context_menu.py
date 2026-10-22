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


def _action(menu, keyword):
    return next(a for a in menu.actions() if keyword in a.text())


def test_edit_and_compare_disabled_when_multi(window, monkeypatch):
    """编辑/对比弹窗一次只能处理一条 → 多选时禁用，否则会只偷偷重放第一条。"""
    from mitmproxy.test import tflow

    flows = [tflow.tflow(resp=True), tflow.tflow(resp=True)]
    monkeypatch.setattr(window, "_selected_flows", lambda: flows)

    menu = window._build_table_context_menu(flows)
    assert not _action(menu, "编辑并重放").isEnabled()
    assert not _action(menu, "重放并对比").isEnabled()
    # 纯重放（不弹窗）批量仍然可用
    assert _action(menu, "重放请求").isEnabled()


def test_batch_replay_queues_all_selected(window, monkeypatch):
    from mitmproxy.test import tflow

    flows = [tflow.tflow(resp=True), tflow.tflow(resp=True), tflow.tflow(resp=True)]
    monkeypatch.setattr(window, "_selected_flows", lambda: flows)

    # running 是只读属性（背后读 _thread.is_alive()）。这里在类上用普通属性遮蔽
    # property（monkeypatch 自动还原），比伪造线程安全——伪造线程会让 teardown 的
    # proxy.stop() 去 join 一个假线程。
    monkeypatch.setattr(type(window.proxy), "running", True)

    queued = []
    monkeypatch.setattr(
        window.proxy, "replay_flow", lambda copy: queued.append(copy) or True
    )

    window._replay_selected(edit=False)
    assert len(queued) == 3


def test_delete_selected_removes_rows(window, monkeypatch):
    from mitmproxy.test import tflow

    flows = [tflow.tflow(resp=True), tflow.tflow(resp=True)]
    for f in flows:
        window.flow_store.append(window.capture.summarize(f))
    monkeypatch.setattr(window, "_selected_flows", lambda: flows)
    before = window.flow_store.rowCount()

    menu = window._build_table_context_menu(flows)
    action = _action(menu, "删除选中会话")
    assert action.isEnabled()

    action.triggered.emit()
    assert window.flow_store.rowCount() == before - 2


def test_delete_selected_keeps_others(window, monkeypatch):
    """删除只影响选中项，未选中的会话仍在列表里。"""
    from mitmproxy.test import tflow

    keep, drop = tflow.tflow(resp=True), tflow.tflow(resp=True)
    window.flow_store.append(window.capture.summarize(keep))
    window.flow_store.append(window.capture.summarize(drop))
    monkeypatch.setattr(window, "_selected_flows", lambda: [drop])

    window._delete_selected_flows()
    remaining = {r["id"] for r in window.flow_store.all_rows()}
    assert keep.id in remaining
    assert drop.id not in remaining
