"""Map Local（域名 → 本地目录）与证书页二维码。

Map Local 盯这些点：
1. target 形态识别：`host:port` 是 remote，路径开头才是 local，不能互相抢；
2. 安全：路径穿越（`..`）与符号链接逃逸必须拒，拒的方式是**透传上游**而不是报错；
3. 语义边界：只拦 GET/HEAD、查询串丢弃、目录找 index.html、不存在就回落；
4. remote 规则不能被 local 逻辑影响（build_map_remote_spec 对 local 返回 None）。

证书页盯：多候选 IP、二维码 SVG 生成、segno 缺失时降级为纯链接、真 HTTP 服务出页。
"""

import asyncio
import io
import os
import socket
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MITEPROXY_HOME", "/tmp/mpf-maplocal-test-home")

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from addons.maplocal import INDEX_FILE, MapLocalAddon  # noqa: E402
from app import certserver  # noqa: E402
from app.network import (  # noqa: E402
    MapRule,
    build_map_remote_spec,
    looks_like_path,
    map_local_entries,
)
from mitmproxy.test import tflow  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- 形态识别


class TestPathDetection:
    @pytest.mark.parametrize(
        "text",
        ["/var/www", "./static", "../up", "~/site", "C:\\web", "C:/web", "\\share"],
    )
    def test_paths(self, text):
        assert looks_like_path(text) is True

    @pytest.mark.parametrize(
        "text",
        ["127.0.0.1:8080", "http://dev.local:9000", "localhost:3000", "", "   "],
    )
    def test_not_paths(self, text):
        assert looks_like_path(text) is False


class TestMapRuleKind:
    def test_remote(self):
        assert MapRule("a.com", "127.0.0.1:8080").kind == "remote"

    def test_local(self):
        assert MapRule("a.com", "./static").kind == "local"

    def test_unknown_garbage(self):
        assert MapRule("a.com", "!!!").kind == "unknown"

    def test_empty_is_unknown(self):
        assert MapRule("", "").kind == "unknown"

    def test_remote_spec_rejects_local(self):
        """local 规则的 target 不是 host:port，remote spec 必须生成不出来。"""
        assert build_map_remote_spec(MapRule("a.com", "./static")) is None

    def test_remote_spec_still_works(self):
        spec = build_map_remote_spec(MapRule("api.prod.com", "127.0.0.1:8080"))
        assert spec is not None and "127.0.0.1:8080" in spec


class TestMapLocalEntries:
    def test_skips_non_local(self):
        rules = [
            MapRule("a.com", "127.0.0.1:8080"),   # remote
            MapRule("b.com", "!!!"),               # unknown
            MapRule("c.com", ""),                  # 空
        ]
        assert map_local_entries(rules) == []

    def test_skips_disabled(self):
        assert map_local_entries([MapRule("a.com", "./s", enabled=False)]) == []

    def test_builds_pattern_and_expands_home(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        rules = [MapRule("static.prod.com", "~/site")]
        entries = map_local_entries(rules)
        assert len(entries) == 1
        pattern, directory = entries[0]
        assert pattern.match("http://static.prod.com/a.js")
        assert not pattern.match("http://other.com/a.js")
        assert directory == tmp_path / "site"

    def test_skips_invalid_regex_source(self):
        # [ 开头的未闭合字符类：_host_pattern 当正则处理，编译失败要跳过
        rules = [MapRule("[bad", "./s")]
        assert map_local_entries(rules) == []


# ---------------------------------------------------------------- addon 行为


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    (root / "js").mkdir(parents=True)
    (root / "js" / "app.js").write_text("console.log(1)")
    (root / "index.html").write_text("<h1>hi</h1>")
    (root / "data.json").write_text('{"a":1}')
    (root / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n fake")
    return root


def _addon(entries):
    return MapLocalAddon(entries)


def _flow(url, method="GET"):
    flow = tflow.tflow(resp=False)
    flow.request.url = url
    flow.request.method = method
    return flow


class TestMapLocalAddon:
    def test_serves_file(self, site):
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/js/app.js")
        _run(addon.request(flow))
        assert flow.response is not None
        assert flow.response.status_code == 200
        assert flow.response.content == b"console.log(1)"
        assert "javascript" in flow.response.headers.get("content-type", "")
        assert flow.marked.startswith("LOCAL:")

    def test_missing_file_passes_through(self, site):
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/nope.js")
        _run(addon.request(flow))
        assert flow.response is None  # 透传上游

    def test_query_string_dropped(self, site):
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/js/app.js?v=123")
        _run(addon.request(flow))
        assert flow.response is not None
        assert flow.response.content == b"console.log(1)"

    def test_directory_uses_index(self, site):
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/")
        _run(addon.request(flow))
        assert flow.response is not None
        assert flow.response.content == b"<h1>hi</h1>"

    def test_json_gets_charset(self, site):
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/data.json")
        _run(addon.request(flow))
        ctype = flow.response.headers.get("content-type", "")
        assert "application/json" in ctype and "charset=utf-8" in ctype

    def test_png_no_charset(self, site):
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/pic.png")
        _run(addon.request(flow))
        ctype = flow.response.headers.get("content-type", "")
        assert "image/png" in ctype and "charset" not in ctype

    def test_traversal_refused(self, site, tmp_path):
        """../ 穿越：拒掉并透传上游，绝不能读到目录外的文件。"""
        secret = tmp_path / "secret.txt"
        secret.write_text("TOPSECRET")
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/../secret.txt")
        _run(addon.request(flow))
        assert flow.response is None

    def test_encoded_traversal_refused(self, site, tmp_path):
        """%2e%2e%2f：mitmproxy 的 path 保留编码形态，也要拒。"""
        secret = tmp_path / "secret2.txt"
        secret.write_text("TOPSECRET")
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/%2e%2e/secret2.txt")
        _run(addon.request(flow))
        assert flow.response is None

    def test_symlink_escape_refused(self, site, tmp_path):
        outside = tmp_path / "outside.txt"
        outside.write_text("ESCAPED")
        (site / "link.txt").symlink_to(outside)
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/link.txt")
        _run(addon.request(flow))
        assert flow.response is None

    def test_symlink_inside_dir_allowed(self, site):
        (site / "js" / "alias.js").symlink_to(site / "js" / "app.js")
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/js/alias.js")
        _run(addon.request(flow))
        assert flow.response is not None
        assert flow.response.content == b"console.log(1)"

    def test_post_not_intercepted(self, site):
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/js/app.js", method="POST")
        _run(addon.request(flow))
        assert flow.response is None

    def test_head_returns_empty_body(self, site):
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/js/app.js", method="HEAD")
        _run(addon.request(flow))
        assert flow.response is not None
        assert flow.response.content == b""

    def test_oversized_file_passes_through(self, site, monkeypatch):
        big = site / "big.bin"
        big.write_bytes(b"x" * 1024)
        import addons.maplocal as ml

        monkeypatch.setattr(ml, "LOCAL_FILE_LIMIT", 10)  # 10 字节上限
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://static.prod.com/big.bin")
        _run(addon.request(flow))
        assert flow.response is None

    def test_non_matching_host_ignored(self, site):
        addon = _addon(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow = _flow("http://other.com/js/app.js")
        _run(addon.request(flow))
        assert flow.response is None

    def test_set_entries_live_update(self, site):
        addon = _addon([])
        flow = _flow("http://static.prod.com/js/app.js")
        _run(addon.request(flow))
        assert flow.response is None
        addon.set_entries(map_local_entries([MapRule("static.prod.com", str(site))]))
        flow2 = _flow("http://static.prod.com/js/app.js")
        _run(addon.request(flow2))
        assert flow2.response is not None

    def test_empty_entries_fast_path(self):
        addon = _addon([])
        flow = _flow("http://x/")
        _run(addon.request(flow))  # 不抛
        assert flow.response is None

    def test_nonexistent_directory_passes_through(self, tmp_path):
        """目录不存在：每条请求都找不到文件，透传（配置期不拦）。"""
        addon = _addon(
            map_local_entries([MapRule("a.com", str(tmp_path / "ghost"))])
        )
        flow = _flow("http://a.com/x")
        _run(addon.request(flow))
        assert flow.response is None


# ---------------------------------------------------------------- 证书页二维码


class TestLanIps:
    def test_returns_nonempty_list(self):
        ips = certserver._lan_ips()
        assert ips and all(isinstance(i, str) for i in ips)

    def test_primary_first(self):
        ips = certserver._lan_ips()
        primary = certserver._lan_ip()
        if not primary.startswith("127."):
            assert ips[0] == primary

    def test_no_loopback_in_list(self):
        assert not any(i.startswith("127.") for i in certserver._lan_ips()) or (
            certserver._lan_ips() == ["127.0.0.1"]
        )


class TestQrSvg:
    def test_generates_inline_svg(self):
        svg = certserver._qr_svg("http://192.168.1.5:8081")
        assert svg.startswith("<svg")
        assert "xml version" not in svg  # 声明已剥掉（内联用）
        assert "rect" in svg or "path" in svg

    def test_graceful_without_segno(self, monkeypatch):
        """segno 缺失 → 空串，页面降级为纯链接，不能抛。"""
        monkeypatch.setitem(sys.modules, "segno", None)
        assert certserver._qr_svg("http://x:1") == ""

    def test_different_urls_different_svg(self):
        a = certserver._qr_svg("http://192.168.1.5:8081")
        b = certserver._qr_svg("http://192.168.1.6:8081")
        assert a != b


def _http_get(port: int, path: str) -> str:
    """raw socket GET（避开 urllib 的代理环境变量干扰）。"""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.sendall(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n".encode())
        chunks = []
        while True:
            data = s.recv(65536)
            if not data:
                break
            chunks.append(data)
    raw = b"".join(chunks)
    return raw.split(b"\r\n\r\n", 1)[1].decode("utf-8", "replace")


class TestCertServerPage:
    @pytest.fixture
    def running_server(self, tmp_path, monkeypatch):
        pem = tmp_path / "ca.pem"
        pem.write_text(
            "-----BEGIN CERTIFICATE-----\nZmFrZQ==\n-----END CERTIFICATE-----\n"
        )
        monkeypatch.setattr(certserver, "CA_PEM_PATH", pem)
        server = certserver.CertServer(port=0, proxy_port=8080)
        server.start()
        try:
            yield server._server.server_address[1]
        finally:
            server.stop()

    def test_page_has_qr_and_addresses(self, running_server):
        html = _http_get(running_server, "/")
        assert "MiteProxy CA 证书" in html
        assert "<svg" in html                      # 二维码
        assert "http://" in html                   # 至少一个地址
        assert "/cert.cer" in html                 # 下载按钮
        assert "代理设置" in html

    def test_cert_download(self, running_server):
        body = _http_get(running_server, "/cert.pem")
        assert "BEGIN CERTIFICATE" in body

    def test_404(self, running_server):
        with socket.create_connection(("127.0.0.1", running_server), timeout=5) as s:
            s.sendall(b"GET /nope HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            raw = b""
            while True:
                d = s.recv(4096)
                if not d:
                    break
                raw += d
        assert b"404" in raw
