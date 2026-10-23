"""详情面板 TLS 页签：展示连接的 TLS 版本 / 加密套件 / SNI / ALPN / 证书链。

数据源是 mitmproxy 的连接对象：``flow.client_conn``（浏览器 → MiteProxy）
与 ``flow.server_conn``（MiteProxy → 目标服务器）。两段都是 TLS 才算
「HTTPS 全链路」；任何一段缺失/明文时给占位说明，不显示空白吓用户。

设计要点：
- 纯数据提取走模块级 ``extract_tls(flow)``（不碰 Qt），返回的标签一律是
  **英文键**（version/cipher/sni/…），由 UI 层 TlsPane 映射为当前语言
  文案——单测喂 SimpleNamespace 假连接即可覆盖，不起真 TLS；
- 证书链用 QTreeWidget 两层：连接段 → 证书（subject/issuer/有效期/指纹）。
"""

from __future__ import annotations

from cryptography.hazmat.primitives.hashes import SHA256
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme


# ---------------------------------------------------------------- 纯数据层


def _fmt_cert(cert) -> list[tuple[str, str]]:
    """把一张证书拆成 (英文键, 值) 列表；属性缺失就跳过，不抛。"""
    rows: list[tuple[str, str]] = []
    if cert is None:
        return rows
    try:
        subject = cert.subject.rfc4514_string()
    except Exception:
        subject = ""
    if subject:
        rows.append(("subject", subject))
    try:
        issuer = cert.issuer.rfc4514_string()
    except Exception:
        issuer = ""
    if issuer:
        rows.append(("issuer", issuer))
    try:
        nb = cert.not_valid_before_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        na = cert.not_valid_after_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        rows.append(("validity", f"{nb} → {na}"))
    except Exception:
        pass
    try:
        serial = format(cert.serial_number, "X")
        rows.append(("serial", serial))
    except Exception:
        pass
    try:
        fp = cert.fingerprint(SHA256())
        rows.append(("sha256", fp.hex()))
    except Exception:
        pass
    return rows


def _conn_rows(conn) -> list[tuple[str, str]]:
    """单个连接对象的 TLS 属性（英文键标签，不含证书链）。"""
    rows: list[tuple[str, str]] = []
    if conn is None:
        return rows
    version = getattr(conn, "tls_version", "") or ""
    if version:
        rows.append(("version", version))
    cipher = getattr(conn, "cipher_name", "") or ""
    if cipher:
        rows.append(("cipher", cipher))
    sni = getattr(conn, "sni", "") or ""
    if sni:
        rows.append(("sni", sni))
    alpn = getattr(conn, "alpn_proto_negotiated", "") or b""
    if isinstance(alpn, bytes):
        alpn = alpn.decode("utf-8", "replace")
    if alpn:
        rows.append(("alpn", alpn))
    ts_tls = getattr(conn, "timestamp_tls_setup", None)
    ts_start = getattr(conn, "timestamp_start", None)
    if ts_tls and ts_start:
        rows.append(("handshake", f"{max(0.0, ts_tls - ts_start) * 1000:.1f} ms"))
    return rows


def _conn_certs(conn) -> list:
    certs = getattr(conn, "certificate_list", None) or []
    return [c for c in certs if c is not None]


def extract_tls(flow) -> dict | None:
    """从 flow 提取 TLS 信息；完全明文（两段都无 TLS）时返回 None。

    返回结构（rows/certs 里的标签都是英文键，UI 层负责本地化）：::

        {
          "client": {"rows": [...], "certs": [...]},
          "server": {"rows": [...], "certs": [...]},
          "client_cert": [...],   # 客户端证书 rows（mTLS）
        }
    """
    client_conn = getattr(flow, "client_conn", None)
    server_conn = getattr(flow, "server_conn", None)
    client_tls = bool(getattr(client_conn, "tls", False)) if client_conn else False
    server_tls = bool(getattr(server_conn, "tls", False)) if server_conn else False
    if not client_tls and not server_tls:
        return None

    info: dict = {"client": None, "server": None, "client_cert": None}
    if client_tls and client_conn is not None:
        info["client"] = {
            "rows": _conn_rows(client_conn),
            "certs": _conn_certs(client_conn),
        }
        clientcert = getattr(client_conn, "clientcert", None)
        if clientcert is not None:
            info["client_cert"] = _fmt_cert(clientcert)
    if server_tls and server_conn is not None:
        info["server"] = {
            "rows": _conn_rows(server_conn),
            "certs": _conn_certs(server_conn),
        }
    return info


def has_tls(flow) -> bool:
    """该 flow 是否有任何一段是 TLS（控制页签显隐）。"""
    return extract_tls(flow) is not None


# ---------------------------------------------------------------- UI 层


class TlsPane(QWidget):
    """TLS 页：连接属性树 + 证书链。非 TLS 连接显示占位说明。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_labels()
        self._build_ui()

    def _build_labels(self) -> None:
        """英文键 → 当前语言文案（构造时取，语言切换需重启生效）。"""
        self._row_labels = {
            "version": self.tr("TLS 版本"),
            "cipher": self.tr("加密套件"),
            "sni": self.tr("SNI"),
            "alpn": self.tr("ALPN"),
            "handshake": self.tr("TLS 握手耗时"),
        }
        self._cert_labels = {
            "subject": self.tr("Subject"),
            "issuer": self.tr("Issuer"),
            "validity": self.tr("有效期"),
            "serial": self.tr("序列号"),
            "sha256": self.tr("SHA-256 指纹"),
        }
        self._section_titles = {
            "client": self.tr("客户端连接（浏览器 → MiteProxy）"),
            "server": self.tr("服务端连接（MiteProxy → 目标服务器）"),
        }
        self._text_cert_chain = self.tr("证书链")
        self._text_cert_item = self.tr("证书 #{0}")
        self._text_certs_count = self.tr("{0} 张")
        self._text_client_cert = self.tr("客户端证书（mTLS）")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.placeholder = QLabel()
        self.placeholder.setWordWrap(True)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet(f"color: {theme.css('hint')};")
        layout.addWidget(self.placeholder, stretch=1)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Item", "Value"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        self.tree.setWordWrap(False)
        layout.addWidget(self.tree, stretch=1)

        self.tree.setVisible(False)

    # ---------------------------------------------------------------- 数据

    def _label(self, mapping: dict, key: str) -> str:
        return mapping.get(key, key)

    def show_flow(self, flow) -> None:
        info = extract_tls(flow)
        if info is None:
            self._show_placeholder()
            return
        self.tree.clear()
        self.placeholder.setVisible(False)
        self.tree.setVisible(True)

        for key in ("client", "server"):
            section = info.get(key)
            if not section:
                continue
            top = QTreeWidgetItem([self._section_titles[key], ""])
            self.tree.addTopLevelItem(top)
            for label, value in section["rows"]:
                top.addChild(QTreeWidgetItem([self._label(self._row_labels, label), value]))
            certs = section["certs"]
            if certs:
                chain = QTreeWidgetItem([self._text_cert_chain,
                                         self._text_certs_count.format(len(certs))])
                top.addChild(chain)
                for i, cert in enumerate(certs):
                    cert_item = QTreeWidgetItem([self._text_cert_item.format(i + 1), ""])
                    chain.addChild(cert_item)
                    for label, value in _fmt_cert(cert):
                        cert_item.addChild(QTreeWidgetItem(
                            [self._label(self._cert_labels, label), value]))
            top.setExpanded(True)

        client_cert = info.get("client_cert")
        if client_cert:
            top = QTreeWidgetItem([self._text_client_cert, ""])
            self.tree.addTopLevelItem(top)
            for label, value in client_cert:
                top.addChild(QTreeWidgetItem([self._label(self._cert_labels, label), value]))
            top.setExpanded(True)

    def _show_placeholder(self) -> None:
        self.tree.setVisible(False)
        self.placeholder.setVisible(True)
        self.placeholder.setText(
            self.tr("该连接未使用 TLS（明文 HTTP）。\n"
            "TLS 信息只在 HTTPS / WSS 连接上出现，分两段展示：\n"
            "· 客户端连接：浏览器（或 App）→ MiteProxy\n"
            "· 服务端连接：MiteProxy → 目标服务器")
        )

    def clear(self) -> None:
        self.tree.clear()
        self.tree.setVisible(False)
        self.placeholder.setVisible(False)
