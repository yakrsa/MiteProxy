"""用户脚本（插件）测试（路线图 #10）：manager 纯逻辑 + 面板 + 主窗口接线。"""

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from app import scripts as scripts_mod
from app.scripts import ScriptsManager, valid_name


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def scripts_dir(tmp_path):
    d = tmp_path / "scripts"
    d.mkdir()
    return d


@pytest.fixture
def manager(scripts_dir):
    return ScriptsManager(scripts_dir=scripts_dir)


# ---------------------------------------------------------------- 名字与文件


def test_valid_name():
    assert valid_name("my_script.py")
    assert valid_name("a-b_1.2.py")
    assert not valid_name("../evil.py")
    assert not not_valid_name_guard("sub/dir.py")
    assert not valid_name("/abs/path.py")
    assert not valid_name("noext")
    assert not valid_name("")


def not_valid_name_guard(name):
    return valid_name(name)


def test_write_read_delete_roundtrip(manager):
    assert manager.write_script("a.py", "x = 1\n") is None
    assert manager.read_script("a.py") == "x = 1\n"
    infos = manager.list_scripts()
    assert [i.name for i in infos] == ["a.py"]
    assert manager.delete_script("a.py")
    assert manager.read_script("a.py") is None


def test_write_rejects_invalid_names(manager):
    assert manager.write_script("../evil.py", "x = 1") == "invalid name"
    assert manager.write_script("noext", "x = 1") == "invalid name"


def test_write_rejects_syntax_errors(manager):
    err = manager.write_script("bad.py", "def broken(:\n")
    assert err and "syntax error" in err
    assert manager.read_script("bad.py") is None       # 不落盘


# ---------------------------------------------------------------- 加载


GOOD_SCRIPT = '''
def request(flow):
    flow.request.headers["x-script"] = "req"


def response(flow):
    flow.response.headers["x-script"] = "resp"
'''

CLASS_SCRIPT = '''
class Addon:
    def response(self, flow):
        flow.response.headers["x-class"] = "1"
'''

CTX_SCRIPT = '''
def response(ctx, flow):
    flow.response.headers["x-ctx"] = ctx["script"]
'''

BOOM_SCRIPT = '''
def response(flow):
    raise RuntimeError("boom")
'''

BAD_SYNTAX = "def broken(:\n"

#: 编译期语法错误：write_script 会在落盘前拦下，不会进入 load_errors。
#: 下面这条是「语法 OK、但导入期即报错」——会被写进磁盘、加载时记录到
#: load_errors（这正是「坏脚本被隔离、不拖垮其他脚本」要测的场景）。
BAD_IMPORT = "import a_module_that_does_not_exist_xyz\n"

NO_HOOKS = "x = 1\n"


def test_build_addons_function_hooks(manager):
    manager.write_script("f.py", GOOD_SCRIPT)
    addons = manager.build_addons({})
    assert len(addons) == 1
    addon = addons[0]
    assert addon.name == "script_f"                  # 唯一名（AddonManager 去重）

    from mitmproxy.test import tflow

    flow = tflow.tflow(resp=True)
    addon.request(flow)
    addon.response(flow)
    assert flow.request.headers["x-script"] == "req"
    assert flow.response.headers["x-script"] == "resp"


def test_build_addons_class_hooks(manager):
    manager.write_script("c.py", CLASS_SCRIPT)
    addons = manager.build_addons({})
    assert len(addons) == 1

    from mitmproxy.test import tflow

    flow = tflow.tflow(resp=True)
    addons[0].response(flow)
    assert flow.response.headers["x-class"] == "1"


def test_build_addons_ctx_param(manager):
    manager.write_script("ctx.py", CTX_SCRIPT)
    addons = manager.build_addons({})

    from mitmproxy.test import tflow

    flow = tflow.tflow(resp=True)
    addons[0].response(flow)
    assert flow.response.headers["x-ctx"] == "ctx"


def test_hook_exception_isolated(manager):
    """钩子抛异常：不传播、不影响代理主流程（只记日志）。"""
    manager.write_script("boom.py", BOOM_SCRIPT)
    addons = manager.build_addons({})
    assert len(addons) == 1

    from mitmproxy.test import tflow

    flow = tflow.tflow(resp=True)
    addons[0].response(flow)          # 不抛即通过
    assert flow.response.status_code == 200


def test_bad_script_does_not_block_others(manager):
    # 注意：用 BAD_IMPORT（导入期报错）而非 BAD_SYNTAX——语法错误会被
    # write_script 在落盘前拦下，压根进不了 load_errors
    manager.write_script("bad.py", BAD_IMPORT)
    manager.write_script("good.py", GOOD_SCRIPT)
    addons = manager.build_addons({})
    assert len(addons) == 1                       # 坏的跳过
    assert "bad.py" in manager.load_errors        # 错误记录下来
    assert manager.load_errors["bad.py"]          # 非空即可，具体文案随异常类型
    # 面板状态列能显示错误
    infos = {i.name: i for i in manager.list_scripts()}
    assert infos["bad.py"].error


def test_no_hooks_script_reported(manager):
    manager.write_script("empty.py", NO_HOOKS)
    addons = manager.build_addons({})
    assert addons == []
    assert "no hooks" in manager.load_errors["empty.py"]


def test_disabled_script_not_loaded(manager):
    manager.write_script("f.py", GOOD_SCRIPT)
    assert len(manager.build_addons({})) == 1
    assert manager.build_addons({"f.py": False}) == []


def test_load_errors_cleared_on_rebuild(manager):
    # 用 BAD_IMPORT（导入期报错）而非 BAD_SYNTAX——语法错误不会落盘，
    # 也就不会出现在 load_errors 里，测不到「清空」语义
    manager.write_script("bad.py", BAD_IMPORT)
    manager.build_addons({})
    assert manager.load_errors
    manager.delete_script("bad.py")
    manager.build_addons({})
    assert manager.load_errors == {}


# ---------------------------------------------------------------- 面板


def _panel(manager, enabled=None):
    from app.ui.scripts_panel import ScriptsPanel

    return ScriptsPanel(manager, enabled=enabled)


def test_panel_lists_scripts(manager, qapp):
    manager.write_script("a.py", GOOD_SCRIPT)
    panel = _panel(manager, {"a.py": False})
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 0).text() == "a.py"
    # 停用态：复选框未勾选 + 状态文案
    from PySide6.QtCore import Qt

    assert panel.table.item(0, 1).checkState().value == Qt.CheckState.Unchecked.value
    assert "已停用" in panel.table.item(0, 4).text()


def test_panel_toggle_emits_and_updates_map(manager, qapp):
    manager.write_script("a.py", GOOD_SCRIPT)
    panel = _panel(manager)
    fired = []
    panel.scripts_changed.connect(lambda: fired.append(1))

    from PySide6.QtCore import Qt

    item = panel.table.item(0, 1)
    item.setCheckState(Qt.CheckState.Unchecked)
    assert fired == [1]
    assert panel.enabled_map() == {"a.py": False}


def test_panel_new_script_dialog_saves(manager, qapp):
    from app.ui.scripts_panel import ScriptEditDialog

    dlg = ScriptEditDialog(manager, content="def response(flow):\n    pass\n")
    dlg.name_edit.setText("new.py")
    dlg._on_save()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert manager.read_script("new.py") is not None


def test_panel_edit_dialog_rejects_bad_syntax(manager, qapp):
    from app.ui.scripts_panel import ScriptEditDialog

    manager.write_script("a.py", GOOD_SCRIPT)
    dlg = ScriptEditDialog(manager, name="a.py", content=GOOD_SCRIPT)
    dlg.code_edit.setPlainText("def broken(:\n")
    dlg._on_save()
    assert dlg.result() != QDialog.DialogCode.Accepted
    assert not dlg.error_label.isHidden()
    # 原文件未被破坏
    assert "def response" in manager.read_script("a.py")


def test_panel_delete_confirmed(manager, qapp, monkeypatch):
    from app.ui import dialogs
    from app.ui.scripts_panel import ScriptsPanel
    from PySide6.QtWidgets import QMessageBox

    manager.write_script("a.py", GOOD_SCRIPT)
    panel = ScriptsPanel(manager)
    panel.table.selectRow(0)
    monkeypatch.setattr(
        dialogs, "question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    fired = []
    panel.scripts_changed.connect(lambda: fired.append(1))
    panel._on_delete()
    assert manager.read_script("a.py") is None
    assert fired == [1]


def test_panel_delete_cancelled(manager, qapp, monkeypatch):
    from app.ui import dialogs
    from app.ui.scripts_panel import ScriptsPanel
    from PySide6.QtWidgets import QMessageBox

    manager.write_script("a.py", GOOD_SCRIPT)
    panel = ScriptsPanel(manager)
    panel.table.selectRow(0)
    monkeypatch.setattr(
        dialogs, "question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )
    panel._on_delete()
    assert manager.read_script("a.py") is not None


# ---------------------------------------------------------------- 主窗口接线


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "scripts").mkdir(parents=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    monkeypatch.setattr(scripts_mod, "SCRIPTS_DIR", home / "scripts")
    from app.ui.main_window import MainWindow

    win = MainWindow(restore_prompt=False)
    yield win
    win.close()


def test_window_has_scripts_tab(window):
    texts = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert "脚本" in texts
    assert window.tabs.indexOf(window.scripts_panel) >= 0


def test_window_loads_scripts_into_proxy_addons(window):
    window.scripts_mgr.write_script("s.py", GOOD_SCRIPT)
    addons = window._build_script_addons()
    assert len(addons) == 1
    assert addons[0].name == "script_s"
    # 代理构造时就带上（_make_proxy 的 addons 列表里）
    window.proxy = window._make_proxy(8899)
    assert any(getattr(a, "name", "") == "script_s"
               for a in window.proxy._addons)


def test_window_scripts_changed_persists_and_hot_reloads(window, monkeypatch):
    window.scripts_mgr.write_script("s.py", GOOD_SCRIPT)
    window.scripts_panel._enabled = {"s.py": True}
    # 代理未运行 → 只持久化 + 提示下次启动生效
    window._on_scripts_changed()
    assert window.settings.scripts == {"s.py": True}

    from app.settings import load_settings

    assert load_settings().scripts == {"s.py": True}

    # 代理在跑 → 热替换（记录调用）
    calls = {}
    monkeypatch.setattr(type(window.proxy), "running",
                        property(lambda self: True))
    monkeypatch.setattr(
        window.proxy, "reload_script_addons",
        lambda addons: calls.setdefault("addons", list(addons)) or True,
    )
    window._on_scripts_changed()
    assert [a.name for a in calls["addons"]] == ["script_s"]


def test_window_script_disabled_after_change(window):
    window.scripts_mgr.write_script("s.py", GOOD_SCRIPT)
    window.scripts_panel._enabled = {"s.py": False}
    window._on_scripts_changed()
    assert window._build_script_addons() == []


def test_proxy_reload_script_addons_without_master():
    """代理没在跑：reload 返回 False（调用方据此走"下次启动生效"）。"""
    from app.proxy import ProxyService

    svc = ProxyService()
    assert svc.reload_script_addons([]) is False
