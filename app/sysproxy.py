"""系统代理接管与还原（v1.13，对齐 Fiddler「Act as System Proxy」）。

启动代理后自动把系统 HTTP/HTTPS 代理指向 127.0.0.1:<port>，停止/退出时还原
原始设置——用户不用再手动配系统代理，Charles/Fiddler 就是这个体验。

设计要点：
- 纯 subprocess 驱动，`run` 参数可注入 → 单测不发真命令；
- 接管前逐服务记录原始状态，还原时逐项写回（原来开的写回原地址端口，
  原来关的关掉）——不会把用户自己的代理配置弄丢；
- 状态落盘 CONFIG_DIR/sysproxy.json：进程崩溃没来得及还原时，下次启动
  recover_if_needed() 按记录恢复现场；
- macOS 走 networksetup；Windows 走注册表（reg query/add），后者未经
  实机回归，以文档中的「已知限制」标注。
"""

from __future__ import annotations

import json
import logging
import platform
import subprocess

from app.rules import CONFIG_DIR
from PySide6.QtCore import QCoreApplication

log = logging.getLogger(__name__)

#: 接管状态落盘位置（崩溃恢复用）
STATE_PATH = CONFIG_DIR / "sysproxy.json"
_TIMEOUT_S = 15


#: Windows 独有常量（macOS/Linux 的 subprocess 没有这个属性，需 getattr 防护）
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(cmd: list[str], timeout: int = _TIMEOUT_S) -> tuple[int, str, str]:
    """执行外部命令，返回 (rc, stdout, stderr)。测试可注入替身。

    Windows 下必须带 CREATE_NO_WINDOW：打包后是无控制台的 GUI 进程，
    每次起 reg 子进程 Windows 都会给它新建一个控制台窗口——启动接管/退出
    还原连续跑 4~5 条命令，就是用户看到的「多个黑窗口闪现」，且每条都有
    100ms+ 的建窗开销。
    """
    extra: dict = {}
    if platform.system() == "Windows":
        extra["creationflags"] = _CREATE_NO_WINDOW
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
            **extra,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, "", str(e)


def _run_elevated(cmd: list[str]) -> tuple[int, str, str]:
    """macOS 提权执行：osascript 弹密码框，与 Charles 的体验一致。

    直接 networksetup 改代理通常需要管理员权限；失败时由调用方降级到这条路。
    """
    import shlex

    inner = " && ".join(shlex.quote(c) for c in cmd)
    return _run(
        ["osascript", "-e", f'do shell script {shlex.quote(inner)} with administrator privileges'],
        timeout=120,  # 等用户输密码
    )


# ------------------------------------------------------------------ macOS

def _macos_services(run) -> list[str]:
    """解析 networksetup -listallnetworkservices，跳过表头与禁用项（* 前缀）。"""
    rc, out, err = run(["networksetup", "-listallnetworkservices"])
    if rc != 0:
        log.warning("列举网络服务失败: %s", err.strip())
        return []
    services = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("An asterisk"):
            continue
        if line.startswith("*"):  # 禁用的服务改了也没意义
            continue
        services.append(line)
    return services


def _macos_get_proxy(run, service: str, secure: bool) -> dict:
    """读某服务当前代理状态。secure=True 读 HTTPS 代理，否则 HTTP。"""
    flag = "-getsecurewebproxy" if secure else "-getwebproxy"
    rc, out, _ = run(["networksetup", flag, service])
    state = {"enabled": False, "server": "", "port": 0}
    if rc != 0:
        return state
    for line in out.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "enabled":
            state["enabled"] = value.lower() in ("yes", "true")
        elif key == "server":
            state["server"] = value
        elif key == "port":
            try:
                state["port"] = int(value)
            except ValueError:
                pass
    return state


def _macos_set(run, service: str, secure: bool, server: str, port: int, enabled: bool) -> tuple[int, str]:
    flag = "-setsecurewebproxy" if secure else "-setwebproxy"
    state_flag = "-setsecurewebproxystate" if secure else "-setwebproxystate"
    if enabled:
        rc, _, err = run(["networksetup", flag, service, server, str(port)])
        if rc != 0:
            return rc, err
        rc, _, err = run(["networksetup", state_flag, service, "on"])
        return rc, err
    rc, _, err = run(["networksetup", state_flag, service, "off"])
    return rc, err


# ------------------------------------------------------------------ Windows

_WIN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def _win_current(run) -> dict:
    """读当前全局代理（ProxyEnable/ProxyServer/Override）。"""
    rc, out, _ = run(["reg", "query", _WIN_KEY, "/v", "ProxyEnable"])
    enabled = False
    if rc == 0 and "0x1" in out:
        enabled = True
    rc, out, _ = run(["reg", "query", _WIN_KEY, "/v", "ProxyServer"])
    server = ""
    if rc == 0:
        for line in out.splitlines():
            if "ProxyServer" in line and "REG_SZ" in line:
                server = line.rsplit(None, 1)[-1].strip()
    return {"enabled": enabled, "server": server}


# ------------------------------------------------------------------ 对外接口

def takeover(port: int, run=_run, elevate: bool = False) -> tuple[bool, str]:
    """把系统代理指向 127.0.0.1:<port>。返回 (是否成功, 说明)。

    先记录每个服务每个 scheme 的原始状态再改；中途失败回滚已改的服务。
    """
    if platform.system() == "Windows":
        return _win_takeover(port, run)
    return _macos_takeover(port, run, elevate)


def _macos_takeover(port: int, run, elevate: bool) -> tuple[bool, str]:
    if elevate:
        run = _run_elevated
    services = _macos_services(run)
    if not services:
        return False, QCoreApplication.translate("sysproxy", "无法枚举网络服务（networksetup 失败）")
    saved: dict[str, dict] = {}
    changed: list[tuple[str, bool]] = []
    for svc in services:
        saved[svc] = {
            "web": _macos_get_proxy(run, svc, secure=False),
            "secure": _macos_get_proxy(run, svc, secure=True),
        }
    for svc in services:
        for secure in (False, True):
            rc, err = _macos_set(run, svc, secure, "127.0.0.1", port, enabled=True)
            if rc != 0:
                # 回滚已改的（按记录还原）
                for done_svc, done_secure in reversed(changed):
                    orig = saved[done_svc]["secure" if done_secure else "web"]
                    _macos_set(
                        run, done_svc, done_secure,
                        orig["server"], orig["port"], orig["enabled"],
                    )
                return False, QCoreApplication.translate("sysproxy", '设置 {0} 代理失败: {1}').format(svc, err.strip() or rc)
            changed.append((svc, secure))
    STATE_PATH.write_text(
        json.dumps({"platform": "darwin", "port": port, "services": saved},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return True, QCoreApplication.translate("sysproxy", '已接管 {0} 个网络服务的系统代理').format(len(services))


def _win_takeover(port: int, run) -> tuple[bool, str]:
    saved = _win_current(run)
    server = f"127.0.0.1:{port}"
    rc, _, err = run([
        "reg", "add", _WIN_KEY, "/v", "ProxyServer", "/t", "REG_SZ", "/d", server, "/f",
    ])
    if rc != 0:
        return False, QCoreApplication.translate("sysproxy", '写注册表失败: {0}').format(err.strip())
    run(["reg", "add", _WIN_KEY, "/v", "ProxyEnable", "/t", "REG_DWORD", "/d", "1", "/f"])
    STATE_PATH.write_text(
        json.dumps({"platform": "windows", "port": port, "saved": saved},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return True, QCoreApplication.translate("sysproxy", "已接管系统代理")


def restore(run=_run, port: int | None = None) -> tuple[bool, str]:
    """还原接管前的系统代理；没有接管记录时是幂等 no-op。

    `port` 是兜底参数：快照文件丢失/损坏时（如被清理工具删掉），无法
    知道接管前的原始设置，但可以识别「当前代理仍指向 127.0.0.1:port
    （我们自己的端口）」并直接关闭——这只可能移除我们自己的接管，不会
    碰用户手动配置的其他代理。
    """
    if not STATE_PATH.exists():
        if port is not None:
            return _clear_local_proxy(run, port)
        return True, QCoreApplication.translate("sysproxy", "无接管记录")
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        STATE_PATH.unlink(missing_ok=True)
        if port is not None:
            return _clear_local_proxy(run, port)
        return False, QCoreApplication.translate("sysproxy", '接管记录损坏，跳过还原: {0}').format(e)

    if state.get("platform") == "windows":
        saved = state.get("saved", {})
        if saved.get("enabled") and saved.get("server"):
            run(["reg", "add", _WIN_KEY, "/v", "ProxyServer",
                 "/t", "REG_SZ", "/d", saved["server"], "/f"])
            run(["reg", "add", _WIN_KEY, "/v", "ProxyEnable",
                 "/t", "REG_DWORD", "/d", "1", "/f"])
        else:
            run(["reg", "add", _WIN_KEY, "/v", "ProxyEnable",
                 "/t", "REG_DWORD", "/d", "0", "/f"])
    else:
        services = _macos_services(run)
        for svc, schemes in state.get("services", {}).items():
            if svc not in services:
                continue  # 服务已被删除（如拔掉的网卡），无从还原
            for key, secure in (("web", False), ("secure", True)):
                orig = schemes.get(key) or {}
                _macos_set(
                    run, svc, secure,
                    orig.get("server", ""), orig.get("port", 0),
                    bool(orig.get("enabled")),
                )
    STATE_PATH.unlink(missing_ok=True)
    return True, QCoreApplication.translate("sysproxy", "已还原系统代理")


def _clear_local_proxy(run, port: int) -> tuple[bool, str]:
    """无快照兜底：关闭所有指向 127.0.0.1:port 的系统代理。

    只精确匹配本机回环地址 + 我们的端口——用户手动配的其他代理
    （哪怕也是 127.0.0.1 但端口不同）一律不动。
    """
    changed = 0
    if platform.system() == "Windows":
        current = _win_current(run)
        server = str(current.get("server") or "")
        if current.get("enabled") and (
            server.endswith(f":{port}")
            and server.split(":")[0] in ("127.0.0.1", "localhost")
        ):
            run(["reg", "add", _WIN_KEY, "/v", "ProxyEnable",
                 "/t", "REG_DWORD", "/d", "0", "/f"])
            changed += 1
    else:
        for svc in _macos_services(run):
            for secure in (False, True):
                cur = _macos_get_proxy(run, svc, secure)
                if (cur.get("enabled")
                        and cur.get("server") in ("127.0.0.1", "localhost")
                        and cur.get("port") == port):
                    _macos_set(run, svc, secure, "", 0, False)
                    changed += 1
    if changed:
        return True, QCoreApplication.translate("sysproxy", '已还原系统代理（无接管记录，按端口 {0} 兜底关闭）').format(port)
    return True, QCoreApplication.translate("sysproxy", "无接管记录")


def recover_if_needed(run=_run, port: int | None = None) -> bool:
    """启动时调用：上次异常退出没还原的，这里补还原。返回是否做了还原。"""
    if not STATE_PATH.exists():
        # 快照不存在也可能有残留接管（快照被外部删除等），按端口兜底扫一遍
        if port is not None:
            ok, msg = _clear_local_proxy(run, port)
            if QCoreApplication.translate("sysproxy", "兜底") in msg:
                log.info("崩溃恢复系统代理: %s", msg)
                return ok
        return False
    ok, msg = restore(run, port=port)
    log.info("崩溃恢复系统代理: %s", msg)
    return ok
