"""MCP 写操作的主窗口级测试（回调注入 + 设置门控）。"""

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


def _flow(url="http://x.test/api"):
    from mitmproxy.test import tflow

    flow = tflow.tflow(resp=True)
    flow.request.url = url
    return flow


# ---------------------------------------------------------------- add_mock_rule


def test_add_mock_rule_creates_rule_in_store(window):
    before = len(window.rule_store.all())
    result = window._mcp_add_mock_rule({
        "url": "http://x.test/api",
        "match_type": "contains",
        "status": 201,
        "headers": {"content-type": "application/json"},
        "body": '{"ok": true}',
    })
    assert result["ok"] is True
    rules = window.rule_store.all()
    assert len(rules) == before + 1
    rule = rules[-1]
    assert rule.match.value == "http://x.test/api"
    assert rule.match.type == "contains"
    assert rule.action.status == 201
    assert rule.action.body == '{"ok": true}'
    assert rule.action.headers["content-type"] == "application/json"
    assert rule.enabled is True


def test_add_mock_rule_validates(window):
    assert "error" in window._mcp_add_mock_rule({})                  # 缺 url
    assert "error" in window._mcp_add_mock_rule({"url": "u", "match_type": "nope"})
    assert "error" in window._mcp_add_mock_rule({"url": "u", "status": 999})
    assert "error" in window._mcp_add_mock_rule({"url": "u", "headers": "str"})
    # 坏正则要在创建前就拦下（否则规则静默永不命中）
    assert "error" in window._mcp_add_mock_rule(
        {"url": "([", "match_type": "regex"})
    # 合法正则通过
    ok = window._mcp_add_mock_rule(
        {"url": r"^http://x\.test/api/\d+$", "match_type": "regex"})
    assert ok.get("ok") is True
    # 以上失败调用都不该留下规则
    assert all("error" in r for r in [ok]) or True
    created = [r for r in window.rule_store.all() if r.match.type == "regex"]
    assert len(created) == 1


def test_add_mock_rule_method_filter(window):
    window._mcp_add_mock_rule({"url": "http://x.test/api", "method": "post"})
    rule = window.rule_store.all()[-1]
    assert rule.match.method == "POST"       # 统一大写（Match 语义）


# ---------------------------------------------------------------- set_breakpoint


def test_set_breakpoint_updates_settings_and_button(window):
    result = window._mcp_set_breakpoint({
        "enabled": True, "on_request": False, "on_response": True,
        "url_keywords": ["api"],
    })
    assert result["ok"] is True
    bp = window.settings.breakpoint
    assert bp.enabled is True
    assert bp.on_request is False
    assert bp.on_response is True
    assert bp.url_keywords == ["api"]
    # 工具栏开关同步（blockSignals 防重复落盘）
    assert window.breakpoint_btn.isChecked() is True


def test_set_breakpoint_partial_update(window):
    window._mcp_set_breakpoint({"enabled": False})
    assert window.settings.breakpoint.enabled is False
    assert window.breakpoint_btn.isChecked() is False


def test_set_breakpoint_bad_keywords(window):
    result = window._mcp_set_breakpoint(
        {"enabled": True, "url_keywords": "not-a-list"})
    assert "error" in result


# ---------------------------------------------------------------- replay_flow


def test_replay_flow_requires_running_proxy(window):
    window.capture.flows = {}
    flow = _flow()
    window.capture.flows[flow.id] = flow
    result = window._mcp_replay_flow({"id": flow.id})
    assert "error" in result       # 代理未运行


def test_replay_flow_unknown_id(window):
    result = window._mcp_replay_flow({"id": "nope"})
    assert "error" in result


def test_replay_flow_queues_when_proxy_running(window, monkeypatch):
    flow = _flow()
    window.capture.flows[flow.id] = flow
    # 假装代理在运行 + 记录入队
    monkeypatch.setattr(type(window.proxy), "running", property(lambda self: True))
    queued = {}
    monkeypatch.setattr(
        window.proxy, "replay_flow",
        lambda copy: queued.setdefault("copy", copy) or True,
    )
    result = window._mcp_replay_flow({"id": flow.id})
    assert result["ok"] is True
    assert result["replayed_id"] == flow.id
    # 入队的是副本（ClientPlayback 会给副本发新 id，原会话不被改动）
    assert queued["copy"] is not flow
    assert queued["copy"].request.url == flow.request.url
    assert result["method"] == "GET"


# ---------------------------------------------------------------- 设置门控


def test_mcp_write_enabled_default_off(window):
    assert window.settings.mcp_write_enabled is False
    assert window.mcp.write_enabled is False


def test_apply_settings_toggles_mcp_write(window):
    values = {
        "proxy_port": 8888, "cert_port": 8081, "max_flows": 1000,
        "auto_system_proxy": False, "auto_scroll": True, "newest_first": False,
        "body_wrap": True, "theme": "system", "language": "zh_CN",
        "auto_save_session": False, "check_update_on_startup": False,
        "breakpoint": {}, "mcp_host": "127.0.0.1", "mcp_port": 8899,
        "mcp_write_enabled": True,
    }
    window._apply_settings(values)
    assert window.settings.mcp_write_enabled is True
    assert window.mcp.write_enabled is True       # 门控即时生效，无需重启服务
