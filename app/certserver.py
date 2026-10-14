"""证书下载服务：给手机安装 CA 证书用（DESIGN.md 3.5）。

- 监听 0.0.0.0:8081，页面展示本机全部候选局域网地址（各带二维码，segno 生成，
  缺失时自动降级为纯链接）+ PEM/DER 下载 + 安装指引；
- CA 来源为 mitmproxy 自动生成的 ~/.mitmproxy/mitmproxy-ca-cert.pem；
- DER 版本用 cryptography 现场转换（mitmproxy 的依赖，必然可用），
  转换失败时只提供 PEM，不影响其他功能。
"""

from __future__ import annotations

import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PORT = 8081
CA_PEM_PATH = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"

PAGE_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MiteProxy · 安装 CA 证书</title>
<style>
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 680px; margin: 24px auto; padding: 0 16px; color: #1f2328; }
  h1 { font-size: 20px; }
  .url { background: #f6f8fa; border: 1px solid #d1d9e0; border-radius: 6px;
         padding: 10px 12px; font-family: ui-monospace, monospace; word-break: break-all; }
  .btn { display: inline-block; margin: 8px 12px 8px 0; padding: 10px 18px;
         background: #1f6feb; color: #fff; border-radius: 6px; text-decoration: none; }
  .btn.ghost { background: #fff; color: #1f6feb; border: 1px solid #1f6feb; }
  h2 { font-size: 16px; margin-top: 28px; }
  ol { line-height: 1.9; }
  .warn { background: #fff8c5; border: 1px solid #d4a72c; border-radius: 6px; padding: 10px 12px; }
  .addr { display: flex; align-items: center; gap: 14px; margin: 12px 0; }
  .addr .url { flex: 1; margin: 0; }
  .qr { line-height: 0; }
  .qr svg { width: 108px; height: 108px; display: block; }
  .note { color: #6b6b6b; font-size: 13px; }
</style>
</head>
<body>
<h1>MiteProxy CA 证书</h1>
<p>手机与电脑连同一 Wi-Fi 后，用手机相机<b>扫码</b>或直接在浏览器输入下面任一地址打开本页，点击按钮安装证书：</p>
%(addresses)s
<p>
  <a class="btn" href="/cert.cer">下载证书（iOS / Android 推荐）</a>
  <a class="btn ghost" href="/cert.pem">下载 PEM 版本</a>
</p>
<div class="warn">⚠️ 此证书仅用于本机调试，请在调试结束后及时从系统中移除。</div>

<h2>iOS / iPadOS</h2>
<ol>
  <li>点击上方按钮下载描述文件</li>
  <li>打开 <b>设置 → 通用 → VPN与设备管理</b>，安装已下载的描述文件</li>
  <li>进入 <b>设置 → 通用 → 关于本机 → 证书信任设置</b>，开启对该证书的信任</li>
</ol>

<h2>Android</h2>
<ol>
  <li>点击上方按钮下载证书</li>
  <li>打开 <b>设置 → 安全 → 加密与凭据 → 安装证书 → CA 证书</b>（各厂商路径略有差异）</li>
  <li>确认安装</li>
</ol>

<h2>macOS（本机浏览器抓包）</h2>
<ol>
  <li>下载 PEM 版本后双击，在<b>钥匙串访问</b>中找到该证书</li>
  <li>双击 → 信任 → 使用时访问设为<b>始终信任</b></li>
</ol>

<h2>代理设置</h2>
<p>手机 Wi-Fi 设置手动代理：服务器填上面任一地址的 IP，端口填 <b>%(proxy_port)s</b>。</p>
<p class="note">有多个地址时，选和手机同一网段的那个（通常是 192.168.x.x）。</p>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "MiteProxyCert/1.0"

    # 由外部注入
    ca_pem: bytes = b""
    ca_der: bytes | None = None
    proxy_port: int = 8080

    def do_GET(self):  # noqa: N802 (http.server 命名约定)
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._serve_html()
        elif path == "/cert.pem":
            self._serve_bytes(self.ca_pem, "application/x-pem-file", "mitmproxy-ca-cert.pem")
        elif path == "/cert.cer":
            data = self.ca_der or self.ca_pem
            ctype = "application/x-x509-ca-cert" if self.ca_der else "application/x-pem-file"
            self._serve_bytes(data, ctype, "mitmproxy-ca-cert.cer")
        else:
            self.send_error(404, "Not Found")

    def _serve_html(self):
        port = self.server.server_address[1]
        blocks = []
        for ip in _lan_ips():
            url = f"http://{ip}:{port}"
            qr = _qr_svg(url)
            # segno 缺失时优雅降级：只有链接没有二维码（功能不受影响）
            qr_html = f'<div class="qr">{qr}</div>' if qr else ""
            blocks.append(
                f'<div class="addr">{qr_html}<div class="url">{url}</div></div>'
            )
        body = (PAGE_TEMPLATE % {
            "addresses": "\n".join(blocks),
            "proxy_port": self.proxy_port,
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_bytes(self, data: bytes, content_type: str, filename: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # 静默默认访问日志
        log.debug("certserver: " + fmt, *args)


def _lan_ip() -> str:
    """探测本机局域网 IP（连 UDP 不真发包，拿路由出口地址）。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _lan_ips() -> list[str]:
    """候选局域网 IP 列表（去重保序，路由出口地址排第一）。

    多网卡机器（Wi-Fi + 以太网 + VPN）拿路由出口地址不一定对，所以把
    getaddrinfo 能拿到的都列上，让用户选和手机同网段的那个。
    """
    ips: list[str] = []
    primary = _lan_ip()
    if primary and not primary.startswith("127."):
        ips.append(primary)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or ip in ips:
                continue
            ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def _qr_svg(url: str) -> str:
    """URL → 内联 SVG 二维码（segno 缺失或失败时返回空串，页面降级为纯链接）。"""
    try:
        import io

        import segno

        buf = io.BytesIO()
        segno.make(url, error="m").save(
            buf, kind="svg", scale=4, dark="#1f2328", light=None
        )
        svg = buf.getvalue().decode("utf-8")
        # 去掉 XML 声明与 DOCTYPE，只留 <svg> 本体（内联进 HTML）
        start = svg.find("<svg")
        return svg[start:] if start >= 0 else ""
    except Exception as e:
        log.debug("二维码生成失败（segno 未安装？）: %s", e)
        return ""


def load_ca() -> tuple[bytes, bytes | None]:
    """读取 CA 证书；返回 (PEM, DER|None)。"""
    pem = CA_PEM_PATH.read_bytes()
    if not pem.strip():
        raise ValueError(f"CA 证书为空: {CA_PEM_PATH}")
    der = None
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding

        cert = x509.load_pem_x509_certificate(pem)
        der = cert.public_bytes(Encoding.DER)
    except Exception as e:  # cryptography 缺失或解析失败：降级只给 PEM
        log.warning("DER 转换失败，仅提供 PEM: %s", e)
    return pem, der


class CertServer:
    """证书下载 HTTP 服务（线程内运行）。"""

    def __init__(self, port: int = DEFAULT_PORT, proxy_port: int = 8080):
        self.port = port
        self.proxy_port = proxy_port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def url(self) -> str:
        return f"http://{_lan_ip()}:{self.port}"

    def start(self) -> None:
        if self.running:
            return
        pem, der = load_ca()

        handler = type(
            "BoundHandler",
            (_Handler,),
            {"ca_pem": pem, "ca_der": der, "proxy_port": self.proxy_port},
        )
        # allow_reuse_address：重启代理后能立刻占回端口
        self._server = ThreadingHTTPServer(("0.0.0.0", self.port), handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="cert-server",
            daemon=True,
        )
        self._thread.start()
        log.info("证书下载服务已启动: %s", self.url)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._thread = None
        log.info("证书下载服务已停止")
