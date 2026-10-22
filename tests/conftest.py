"""测试公共配置：隔离配置目录，避免污染真实 ~/.miteproxy。"""

import os
import sys
from pathlib import Path

import pytest

# 让测试可以 import app / addons 包
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 在 import app.rules 之前设置隔离目录
os.environ.setdefault("MITEPROXY_HOME", "/tmp/miteproxy-test-home")

from app import rules as rules_mod  # noqa: E402
from app import settings as settings_mod  # noqa: E402


@pytest.fixture()
def store(tmp_path):
    """指向临时文件的空 RuleStore。"""
    s = rules_mod.RuleStore(path=tmp_path / "rules.json")
    return s


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """每个测试用例隔离 CONFIG_DIR（导入器二进制缓存用）。

    RULES_PATH 也要一起隔离：它在 import 时按 CONFIG_DIR 算好并冻结，
    只 patch CONFIG_DIR 的话，`RuleStore()`（无参构造，MainWindow 就是这么用的）
    仍然会读写同一个共享文件——多个窗口用例互相污染，行号断言会随机失败。

    SETTINGS_PATH 同理：`load_settings()/save_settings()` 读的是 import 期
    冻结的模块全局。不隔离的话 settings.json 会在多次 pytest 运行之间共享
    （列显隐、过滤预设这类"跑一次改一次"的状态会泄漏到后续运行，
    让断言随机失败）。另注意 MITEPROXY_HOME 在 import 之后才 setenv 是
    没用的——CONFIG_DIR 已冻结，必须像这样直接 patch 模块属性。
    """
    home = tmp_path / "config-home"
    monkeypatch.setattr(rules_mod, "CONFIG_DIR", home)
    monkeypatch.setattr(rules_mod, "RULES_PATH", home / "rules.json")
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", home / "settings.json")
    home.mkdir(exist_ok=True)
