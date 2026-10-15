"""单实例锁：防止应用被多次启动出现多个实例。

多个实例会抢代理端口/证书端口，还会互相覆盖系统代理设置（后启动的
接管、先退出的还原，把还在跑的实例的代理一起撤掉），所以必须在入口
挡住第二实例。

实现 = QSharedMemory 原子占位 + QLocalServer 唤醒，两个都用：
- 只看共享内存：上次崩溃残留的段会被误判成「已在运行」，应用打不开；
- 只看本地 socket：connect 行为受残留 socket 文件影响，不够原子。
create() 是原子操作，占不到说明有人先占了；再用 socket 探活区分
「活实例」和「崩溃残留」——活实例一定会监听 LOCAL_SERVER_NAME。

第二个实例的流程：acquire() 失败 → notify_running() 通知主实例把窗口
带到前台 → 自己退出（不弹主界面）。
"""

from __future__ import annotations

from PySide6.QtCore import QSharedMemory
from PySide6.QtNetwork import QLocalServer, QLocalSocket

INSTANCE_KEY = "MiteProxy-SingleInstance"
LOCAL_SERVER_NAME = "MiteProxy-Wake"

_shared_mem: QSharedMemory | None = None
_wake_server: QLocalServer | None = None


def acquire() -> bool:
    """尝试成为唯一实例。

    成功：占住共享内存并开始监听唤醒请求，返回 True（调用方继续启动）。
    失败：已有实例在运行（或极端情况下锁不可用），返回 False。

    共享内存必须持有到进程退出——QSharedMemory 被回收（无引用/ detach）
    后锁就失效了，所以这里存到模块级变量。
    """
    global _shared_mem, _wake_server
    if _shared_mem is not None:
        return True     # 本进程已持有（幂等）
    mem = QSharedMemory(INSTANCE_KEY)
    if not mem.create(1):
        if _wake_socket_alive():
            return False    # 有活实例在监听：确认真双开
        # 段残留但没有活实例（上次崩溃）：attach+detach 触发清理后重试
        mem.attach()
        mem.detach()
        if not mem.create(1):
            # 仍占不到：宁可误判成「已在运行」也不能双开
            # （双开会抢端口、互相覆盖系统代理）
            return False
    _shared_mem = mem
    # 清掉上次崩溃可能残留的 socket 文件（活实例场景根本走不到这里）
    QLocalServer.removeServer(LOCAL_SERVER_NAME)
    _wake_server = QLocalServer()
    if not _wake_server.listen(LOCAL_SERVER_NAME):
        # 监听失败不致命：只是后续实例唤醒不了本实例（仍会被锁挡住）
        _wake_server = None
    return True


def release() -> None:
    """主动让出单实例锁。

    「换端口重启整个应用」时用：旧实例必须先放手，否则新实例会被锁
    挡回去（当成双开只唤醒旧窗口然后退出），重启就变成了直接退出。
    """
    global _shared_mem, _wake_server
    if _wake_server is not None:
        _wake_server.close()
        _wake_server = None
    QLocalServer.removeServer(LOCAL_SERVER_NAME)
    if _shared_mem is not None:
        _shared_mem.detach()
        _shared_mem = None


def start_wake_listener(on_wake) -> None:
    """注册唤醒回调（主窗口 show 之后再调用，避免窗口没就绪就被 raise）。"""
    if _wake_server is None:
        return

    def _handle() -> None:
        assert _wake_server is not None
        while _wake_server.hasPendingConnections():
            conn = _wake_server.nextPendingConnection()
            conn.disconnectFromServer()
            conn.deleteLater()
        on_wake()

    _wake_server.newConnection.connect(_handle)


def notify_running() -> bool:
    """第二个实例：让已运行的实例把主窗口带到前台。返回是否联系上了。"""
    sock = QLocalSocket()
    sock.connectToServer(LOCAL_SERVER_NAME)
    if not sock.waitForConnected(1000):
        sock.abort()
        return False
    sock.write(b"show")
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def _wake_socket_alive() -> bool:
    """本地 socket 探活：能否连上活实例的唤醒服务。"""
    sock = QLocalSocket()
    sock.connectToServer(LOCAL_SERVER_NAME)
    alive = sock.waitForConnected(500)
    sock.abort()
    return alive
