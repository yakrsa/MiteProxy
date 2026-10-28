"""T2：API 集合（保存/管理/加载）与 GraphQL 请求组装。

覆盖：
- store 层：增删改查、损坏文件容错、旧版 dict headers 兼容；
- CollectionDialog：列表刷新、加载回调、重命名/删除（模态框 monkeypatch）；
- ApiPanel：保存到集合、从集合回灌、GraphQL 模式切换与 body 组装校验。
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from app import api_collections as store
from app.ui.api_panel import ApiPanel
from app.ui.collection_dialog import CollectionDialog


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def isolate_home(tmp_path, monkeypatch):
    """集合文件落 CONFIG_DIR，用 MITEPROXY_HOME 隔离不碰真实配置。"""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MITEPROXY_HOME", str(home))
    # CONFIG_DIR 在 import 期求值，测试里按当前环境变量重算
    monkeypatch.setattr(store, "CONFIG_DIR", home)
    monkeypatch.setattr(store, "COLLECTIONS_PATH", home / "api_collections.json")
    yield home


# ---------------------------------------------------------------- store 层


def test_add_and_load_roundtrip():
    item = store.add_collection(
        name="获取用户", method="POST", url="https://api.test/u",
        headers=[["Authorization", "Bearer x"], ["", "ignored"]], body='{"a":1}',
    )
    assert item["id"] and item["name"] == "获取用户"
    assert item["headers"] == [["Authorization", "Bearer x"]]  # 空 key 被剔除
    items = store.load_collections()
    assert len(items) == 1
    assert items[0]["url"] == "https://api.test/u"
    assert items[0]["body"] == '{"a":1}'


def test_add_keeps_empty_name_for_ui_fallback():
    # 存储层不放展示文案：空 name 存空串，由 UI 层本地化兜底
    item = store.add_collection(name="  ", url="https://api.test/only-url")
    assert item["name"] == ""
    items = store.load_collections()
    assert items[0]["name"] == ""


def test_delete_and_rename():
    item = store.add_collection(name="t", url="https://x.test")
    assert store.delete_collection(item["id"]) is True
    assert store.load_collections() == []
    # 删不存在的 id 返回 False
    assert store.delete_collection("nope") is False
    item = store.add_collection(name="old", url="https://x.test")
    assert store.rename_collection(item["id"], "new") is True
    assert store.find_collection(item["id"])["name"] == "new"
    assert store.rename_collection("nope", "x") is False


def test_load_tolerates_corrupt_file(isolate_home):
    (isolate_home / "api_collections.json").write_text("{not json", encoding="utf-8")
    assert store.load_collections() == []
    # 非 list 的合法 JSON 也当空处理
    (isolate_home / "api_collections.json").write_text('{"a":1}', encoding="utf-8")
    assert store.load_collections() == []


def test_load_migrates_legacy_dict_headers(isolate_home):
    legacy = [{
        "id": "x1", "name": "旧版", "method": "GET",
        "url": "https://x.test", "headers": {"K": "V", "": "drop"},
        "body": "", "created_at": 1,
    }]
    (isolate_home / "api_collections.json").write_text(
        json.dumps(legacy), encoding="utf-8")
    items = store.load_collections()
    assert items[0]["headers"] == [["K", "V"]]
    # 未知多余字段被白名单过滤
    assert "unknown_field" not in items[0]


# ---------------------------------------------------------------- 对话框


def test_collection_dialog_lists_and_loads(qapp, monkeypatch):
    store.add_collection(name="n1", method="GET", url="https://x.test/1")
    loaded = []
    dlg = CollectionDialog(on_load=loaded.append)
    assert dlg.list_widget.count() == 1
    dlg.list_widget.setCurrentRow(0)
    dlg._load_selected()
    assert len(loaded) == 1
    assert loaded[0]["url"] == "https://x.test/1"


def test_collection_dialog_empty_state(qapp):
    dlg = CollectionDialog(on_load=lambda it: None)
    assert dlg.list_widget.count() == 0
    assert not dlg.empty_label.isHidden()
    assert dlg.list_widget.isHidden()
    assert not dlg.load_btn.isEnabled()  # 无选中时按钮禁用


def _patch_input_dialog(monkeypatch, text: str, ok: bool = True) -> None:
    """拦掉取名弹窗（输入法：QInputDialog 实例 + exec）。

    原来用静态 ``QInputDialog.getText``，改成实例 + ``exec()`` 是为了能设
    windowModality（静态版默认是应用模态，会把整个应用锁死）。所以这里
    patch 的目标也得跟着换：拦 ``exec`` 定「确认 / 取消」，拦 ``textValue``
    定输入内容。
    """
    monkeypatch.setattr(QInputDialog, "exec", lambda self: ok)
    monkeypatch.setattr(QInputDialog, "textValue", lambda self: text)


def test_collection_dialog_rename(qapp, monkeypatch):
    item = store.add_collection(name="old", url="https://x.test")
    _patch_input_dialog(monkeypatch, "renamed")
    dlg = CollectionDialog(on_load=lambda it: None)
    dlg.list_widget.setCurrentRow(0)
    dlg._rename_selected()
    assert store.find_collection(item["id"])["name"] == "renamed"
    # 用户取消（ok=False）不改名
    _patch_input_dialog(monkeypatch, "zzz", ok=False)
    dlg._rename_selected()
    assert store.find_collection(item["id"])["name"] == "renamed"


def test_collection_dialog_delete(qapp, monkeypatch):
    """删除确认走 app.ui.dialogs.question（窗口模态，非静态 QMessageBox）。"""
    item = store.add_collection(name="todel", url="https://x.test")
    monkeypatch.setattr(
        "app.ui.dialogs.question",
        lambda *a, **k: QMessageBox.StandardButton.Yes)
    dlg = CollectionDialog(on_load=lambda it: None)
    dlg.list_widget.setCurrentRow(0)
    dlg._delete_selected()
    assert store.find_collection(item["id"]) is None
    # 选 No 时不删
    item2 = store.add_collection(name="keep", url="https://x.test")
    monkeypatch.setattr(
        "app.ui.dialogs.question",
        lambda *a, **k: QMessageBox.StandardButton.No)
    dlg2 = CollectionDialog(on_load=lambda it: None)
    dlg2.list_widget.setCurrentRow(0)
    dlg2._delete_selected()
    assert store.find_collection(item2["id"]) is not None


# ---------------------------------------------------------------- ApiPanel


def test_save_to_collection_via_panel(qapp, monkeypatch):
    p = ApiPanel()
    p.load_request("POST", "https://api.test/save", {"K": "V"}, "body-text")
    _patch_input_dialog(monkeypatch, "我的请求")
    p._save_to_collection()
    items = store.load_collections()
    assert len(items) == 1
    assert items[0]["name"] == "我的请求"
    assert items[0]["method"] == "POST"
    assert items[0]["headers"] == [["K", "V"]]
    assert items[0]["body"] == "body-text"
    assert "已保存" in p.resp_label.text()


def test_save_cancelled_saves_nothing(qapp, monkeypatch):
    p = ApiPanel()
    p.load_request("GET", "https://api.test/x")
    _patch_input_dialog(monkeypatch, "", ok=False)
    p._save_to_collection()
    assert store.load_collections() == []


def test_load_from_collection_restores_everything(qapp):
    item = store.add_collection(
        name="gql", method="POST", url="https://api.test/g",
        headers=[["Authorization", "Bearer t"]], body="query { a }",
        graphql=True, variables='{"id": 1}',
    )
    p = ApiPanel()
    p._load_from_collection(item)
    assert p.body_kind_combo.currentData() == "graphql"
    assert p.method_combo.currentData() == "POST"
    assert p.url_edit.text() == "https://api.test/g"
    assert p.body_edit.toPlainText() == "query { a }"
    assert p.variables_edit.toPlainText() == '{"id": 1}'
    # headers 表恢复
    assert p.headers_table.rowCount() == 1
    assert p.headers_table.item(0, 0).text() == "Authorization"


def test_graphql_mode_toggles_variables(qapp):
    p = ApiPanel()
    assert p.variables_edit.isHidden()
    p.body_kind_combo.setCurrentIndex(1)  # GraphQL
    assert not p.variables_edit.isHidden()
    assert p.method_combo.currentData() == "POST"  # GraphQL 强制 POST
    p.body_kind_combo.setCurrentIndex(0)
    assert p.variables_edit.isHidden()
    assert p.method_combo.currentData() == "POST"  # 切回不擅自改方法


def test_build_graphql_body_ok(qapp):
    p = ApiPanel()
    p.body_kind_combo.setCurrentIndex(1)
    p.body_edit.setPlainText("query { user(id: 1) { name } }")
    p.variables_edit.setPlainText('{"id": 1}')
    body, err = p._build_graphql_body()
    assert err == ""
    payload = json.loads(body)
    assert payload["query"] == "query { user(id: 1) { name } }"
    assert payload["variables"] == {"id": 1}


def test_build_graphql_body_rejects_bad_variables(qapp):
    p = ApiPanel()
    p.body_kind_combo.setCurrentIndex(1)
    p.body_edit.setPlainText("query { a }")
    # 空 variables 合法 -> {}
    body, err = p._build_graphql_body()
    assert err == "" and json.loads(body)["variables"] == {}
    # 非法 JSON
    p.variables_edit.setPlainText("{oops")
    body, err = p._build_graphql_body()
    assert body == "" and "JSON" in err
    # 合法 JSON 但不是对象
    p.variables_edit.setPlainText("[1, 2]")
    body, err = p._build_graphql_body()
    assert body == "" and "对象" in err


def test_build_graphql_body_requires_query(qapp):
    p = ApiPanel()
    p.body_kind_combo.setCurrentIndex(1)
    p.body_edit.setPlainText("   ")
    body, err = p._build_graphql_body()
    assert body == "" and "Query" in err
