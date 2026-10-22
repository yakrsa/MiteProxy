"""用户脚本（插件）：让用户写 Python 挂 mitmproxy 的 flow 钩子（路线图 #10）。

对标 FiddlerScript / mitmproxy 的 `-s script.py`，但面向本应用的场景：

- 脚本放 ``~/.miteproxy/scripts/*.py``，在「脚本」页里增删改、启停；
- 支持两种写法：**模块级函数**（``def request(flow): ...``）或一个
  **``Addon`` 类**（``class Addon: def response(self, flow): ...``）；
- 每个脚本包一层 ``_ScriptAddon``：钩子异常就地捕获并记日志，
  **一个脚本坏掉不影响其他脚本和代理主流程**；
- 代理运行中保存/启停 → 热替换（``ProxyService.reload_script_addons``），
  不用重启代理；没在运行就下次启动自动带上。

安全边界（如实说明，不假装沙箱）：脚本在**本进程内**运行，与主程序同等
权限——能读抓包内容、改流量、动文件。只把脚本目录交给可信的人；
应用能保证的只有「单个脚本报错被隔离」这一条。
"""

from __future__ import annotations

import importlib.util
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.rules import CONFIG_DIR

log = logging.getLogger(__name__)

#: 脚本目录（测试可经构造函数覆盖）
SCRIPTS_DIR = CONFIG_DIR / "scripts"

#: 支持的钩子（mitmproxy addon API 的子集）。刻意不含 load/configure：
#     选项系统由主程序掌管，脚本只碰 flow
SUPPORTED_HOOKS = (
    "requestheaders",
    "request",
    "responseheaders",
    "response",
    "error",
    "websocket_message",
    "websocket_end",
)

#: 新建脚本的模板（中文注释：脚本是给用户看的，i18n 不适用）
SCRIPT_TEMPLATE = '''"""MiteProxy 用户脚本。

支持的钩子（任选其一，写函数或类的方法都行）：

    def request(flow): ...          # 请求到达（改 flow.request 即可改写请求）
    def response(flow): ...         # 响应到达（改 flow.response）
    def error(flow): ...            # 出错

或写成类（约定叫 Addon）：

    class Addon:
        def response(self, flow): ...

ctx 是可选的第一参数：写上 ``ctx`` 的钩子会收到一个 dict（含 script 名），
方便在日志里区分是哪个脚本。异常只会影响本脚本，不会拖垮代理。
"""


def response(flow):
    # 示例：给所有 JSON 响应加一个头
    if flow.response and "json" in (flow.response.headers.get("content-type") or ""):
        flow.response.headers["x-my-script"] = "1"
'''

#: 文件名规则：只允许安全字符，必须 .py 结尾（防路径穿越写别处）
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*\.py$")


@dataclass
class ScriptInfo:
    """一个脚本文件的静态信息（启用态由调用方的 settings.scripts 决定）。"""

    name: str
    size: int = 0
    modified: str = ""          # 本地时间 ISO（秒精度）
    error: str = ""             # 上次加载/编译的错误（空 = 正常）


def valid_name(name: str) -> bool:
    """脚本名是否合法（防 `../../etc/passwd.py` 这类穿越）。"""
    return bool(_NAME_RE.match(name or ""))


class ScriptsManager:
    """脚本目录的管理 + 加载。加载错误**记录不抛出**——UI 要能显示
    「哪个脚本坏了、为什么」，同时其他脚本照常工作。"""

    def __init__(self, scripts_dir=None):
        self.scripts_dir = Path(scripts_dir or SCRIPTS_DIR)
        #: {脚本名: 上次加载错误}，build_addons 后刷新
        self.load_errors: dict[str, str] = {}

    # ------------------------------------------------------------ 目录操作

    def list_scripts(self) -> list[ScriptInfo]:
        """扫描脚本目录（只列 .py；坏名字的文件忽略并说明）。"""
        if not self.scripts_dir.exists():
            return []
        infos: list[ScriptInfo] = []
        try:
            entries = sorted(self.scripts_dir.iterdir())
        except OSError as e:
            log.warning("读取脚本目录失败: %s", e)
            return []
        for path in entries:
            if not path.is_file() or path.suffix != ".py":
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            from datetime import datetime

            infos.append(ScriptInfo(
                name=path.name,
                size=st.st_size,
                modified=datetime.fromtimestamp(st.st_mtime).isoformat(
                    timespec="seconds"),
                error=self.load_errors.get(path.name, ""),
            ))
        return infos

    def path_of(self, name: str) -> Path | None:
        """脚本名 → 路径（非法名返回 None，绝不拼出目录外的路径）。"""
        if not valid_name(name):
            return None
        return self.scripts_dir / name

    def read_script(self, name: str) -> str | None:
        path = self.path_of(name)
        if path is None or not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def write_script(self, name: str, content: str) -> str | None:
        """新建/覆盖脚本；返回错误文案（None = 成功）。

        先做语法编译检查再落盘——把写坏的脚本存进去只会让下次加载报错，
        存之前就拦下来能省一事。
        """
        if not valid_name(name):
            return "invalid name"
        try:
            compile(content, name, "exec")
        except SyntaxError as e:
            return f"syntax error: {e.msg} (line {e.lineno})"
        try:
            self.scripts_dir.mkdir(parents=True, exist_ok=True)
            path = self.scripts_dir / name
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return f"write failed: {e}"
        self.load_errors.pop(name, None)
        return None

    def delete_script(self, name: str) -> bool:
        path = self.path_of(name)
        if path is None or not path.is_file():
            return False
        try:
            path.unlink()
        except OSError as e:
            log.warning("删除脚本失败 %s: %s", name, e)
            return False
        self.load_errors.pop(name, None)
        return True

    # ------------------------------------------------------------ 加载

    def build_addons(self, enabled: dict[str, bool]) -> list:
        """把启用的脚本加载成 addon 列表（代理启动 / 热替换用）。

        `enabled`: {脚本名: 是否启用}（缺省视为启用——文件在目录里、用户
        没显式关过，就该跑）。加载失败记 ``load_errors`` 并跳过，
        返回的列表只含加载成功的。
        """
        self.load_errors = {}
        addons: list = []
        for info in self.list_scripts():
            if not enabled.get(info.name, True):
                continue
            addon, err = self._load_one(info.name)
            if err:
                self.load_errors[info.name] = err
                log.warning("用户脚本 %s 加载失败: %s", info.name, err)
                continue
            addons.append(addon)
        return addons

    def _load_one(self, name: str):
        """加载单个脚本 → (addon, 错误)。模块每次全新导入（不缓存），
        保存后热替换能拿到新代码。"""
        path = self.path_of(name)
        if path is None:
            return None, "invalid name"
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return None, f"read failed: {e}"
        try:
            compile(source, name, "exec")
        except SyntaxError as e:
            return None, f"syntax error: {e.msg} (line {e.lineno})"

        module_name = f"mite_script_{Path(name).stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                return None, "cannot create module spec"
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

        hooks = _collect_hooks(module)
        if not hooks:
            return None, "no hooks found (define request/response/... functions " \
                         "or an Addon class)"
        return _ScriptAddon(name, module, hooks), None


def _collect_hooks(module) -> dict:
    """从模块里收集钩子：模块级函数优先；否则找带钩子的类（约定 Addon）。

    返回 {钩子名: callable(flow)}。类钩子现实例化并绑定 self。
    """
    hooks: dict = {}
    for hook_name in SUPPORTED_HOOKS:
        fn = getattr(module, hook_name, None)
        if callable(fn):
            hooks[hook_name] = fn
    if hooks:
        return hooks

    # 模块级函数一个都没有 → 找类。优先约定名 Addon，否则任何带钩子的类
    candidates = []
    for attr in vars(module).values():
        if not isinstance(attr, type):
            continue
        if attr.__module__ != module.__name__:
            continue        # 只认本模块定义的类（别把 import 进来的基类当脚本）
        if any(callable(getattr(attr, h, None)) for h in SUPPORTED_HOOKS):
            candidates.append(attr)
    candidates.sort(key=lambda c: (c.__name__ != "Addon", c.__name__))
    if not candidates:
        return {}
    cls = candidates[0]
    try:
        instance = cls()
    except Exception:
        return {}
    for hook_name in SUPPORTED_HOOKS:
        method = getattr(instance, hook_name, None)
        if callable(method):
            hooks[hook_name] = method
    return hooks


class _ScriptAddon:
    """单个用户脚本的 addon 包装：唯一 name + 异常隔离 + 可溯源日志。

    `name` 必须唯一：mitmproxy 的 AddonManager 按 name 去重，同名
    （比如都叫 scriptaddon）第二个 add 会直接抛 AddonManagerError。
    """

    def __init__(self, script_name: str, module, hooks: dict):
        self.script_name = script_name
        self.script_stem = Path(script_name).stem
        self.name = f"script_{self.script_stem}"
        self._module = module
        self._hooks = hooks

    def _invoke(self, hook_name: str, flow) -> None:
        fn = self._hooks.get(hook_name)
        if fn is None:
            return
        try:
            # 支持可选的 ctx 第一参：def request(ctx, flow) 也能跑。
            # ctx["script"] 给去扩展名的脚本名，日志里好看、也好比对
            if _wants_ctx(fn):
                fn({"script": self.script_stem}, flow)
            else:
                fn(flow)
        except Exception:
            # 隔离：一个钩子坏掉只记日志，代理主流程与其他脚本不受影响
            log.exception("用户脚本 %s 的 %s 钩子执行出错", self.script_name,
                          hook_name)

    # mitmproxy 只在 addon 上找同名属性即调用，逐个定义最直白
    def requestheaders(self, flow) -> None:
        self._invoke("requestheaders", flow)

    def request(self, flow) -> None:
        self._invoke("request", flow)

    def responseheaders(self, flow) -> None:
        self._invoke("responseheaders", flow)

    def response(self, flow) -> None:
        self._invoke("response", flow)

    def error(self, flow) -> None:
        self._invoke("error", flow)

    def websocket_message(self, flow) -> None:
        self._invoke("websocket_message", flow)

    def websocket_end(self, flow) -> None:
        self._invoke("websocket_end", flow)


def _wants_ctx(fn) -> bool:
    """钩子的第一个位置参数是否叫 ctx（可选上下文 dict）。"""
    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    for name, param in sig.parameters.items():
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD,
                          param.VAR_POSITIONAL):
            return name == "ctx"
    return False
