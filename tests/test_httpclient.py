"""httpclient.send_request 单元测试：本地最小 HTTP 服务真发真收。"""

import json
import socket
import threading

import pytest

from app.httpclient import send_request


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class MiniHTTPServer:
    """够用的 HTTP 服务：按 path 返回 JSON，记录收到的请求。"""

    def __init__(self):
        self.port = _free_port()
        self.requests = []
        self._srv = socket.socket()
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", self.port))
        self._srv.listen(4)

    def serve_forever(self) -> None:
        def run():
            while True:
                try:
                    conn, _ = self._srv.accept()
                except OSError:
                    return
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

        threading.Thread(target=run, daemon=True).start()

    def _handle(self, conn):
        try:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                data += chunk
            head, _, rest = data.partition(b"\r\n\r\n")
            lines = head.decode("latin-1").split("\r\n")
            method, path, _ = lines[0].split(" ", 2)
            length = 0
            for line in lines[1:]:
                if line.lower().startswith("content-length:"):
                    length = int(line.split(":", 1)[1])
            while len(rest) < length:
                rest += conn.recv(4096)
            self.requests.append((method, path, rest))
            if path == "/echo":
                body = json.dumps(
                    {"method": method, "body": rest.decode("utf-8", "replace")}
                ).encode()
                resp = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"X-Echo: yes\r\n"
                    b"Set-Cookie: a=1\r\nSet-Cookie: b=2\r\n"
                    b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
                )
            elif path == "/gz":
                import gzip

                raw = json.dumps({"hello": "world"}).encode()
                comp = gzip.compress(raw)
                resp = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Encoding: gzip\r\n"
                    b"Content-Length: " + str(len(comp)).encode() + b"\r\n\r\n" + comp
                )
            elif path == "/br":
                import brotli

                raw = json.dumps({"hello": "world"}).encode()
                comp = brotli.compress(raw)
                resp = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Encoding: br\r\n"
                    b"Content-Length: " + str(len(comp)).encode() + b"\r\n\r\n" + comp
                )
            elif path == "/redirect":
                resp = (
                    b"HTTP/1.1 302 Found\r\nLocation: /echo\r\nContent-Length: 0\r\n\r\n"
                )
            else:
                resp = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
            conn.sendall(resp)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def close(self):
        self._srv.close()


@pytest.fixture()
def server():
    srv = MiniHTTPServer()
    srv.serve_forever()
    yield srv
    srv.close()


class TestSendRequest:
    def test_get_json(self, server):
        r = send_request("GET", f"http://127.0.0.1:{server.port}/echo")
        assert r.ok and r.status == 200
        payload = json.loads(r.body)
        assert payload["method"] == "GET"
        names = [k for k, _ in r.headers]
        assert names.count("Set-Cookie") == 2  # 重复响应头保序保留

    def test_post_body_and_header(self, server):
        r = send_request(
            "POST",
            f"http://127.0.0.1:{server.port}/echo",
            headers={"Content-Type": "application/json"},
            body=b'{"a":1}',
        )
        assert r.ok
        method, path, body = server.requests[-1]
        assert method == "POST" and path == "/echo"
        assert body == b'{"a":1}'
        assert json.loads(r.body)["body"] == '{"a":1}'

    def test_no_redirect_follow(self, server):
        """3xx 原样返回（调试要看 302 本身）。"""
        r = send_request("GET", f"http://127.0.0.1:{server.port}/redirect")
        assert r.ok and r.status == 302
        assert dict(r.headers).get("Location") == "/echo"

    def test_404_still_ok(self, server):
        r = send_request("GET", f"http://127.0.0.1:{server.port}/nope")
        assert r.ok and r.status == 404

    def test_invalid_url(self, server):
        r = send_request("GET", "ftp://x")
        assert not r.ok and "http" in r.error
        r = send_request("GET", "")
        assert not r.ok

    def test_unreachable_host(self):
        r = send_request("GET", "http://127.0.0.1:1/", timeout=2)
        assert not r.ok and "连接失败" in r.error

    def test_method_normalized(self, server):
        r = send_request(" get ", f"http://127.0.0.1:{server.port}/echo")
        assert r.ok
        assert server.requests[-1][0] == "GET"

    def test_gzip_response_decompressed(self, server):
        """bug1：gzip 响应必须解压，body 是明文 JSON（不是压缩字节）。"""
        r = send_request("GET", f"http://127.0.0.1:{server.port}/gz")
        assert r.ok and r.status == 200
        assert r.raw_len > 0
        assert json.loads(r.body)["hello"] == "world"

    def test_brotli_response_decompressed(self, server):
        """bug1：brotli 响应也必须解压（之前 sniff_decompress 不认 brotli → 落到十六进制）。"""
        r = send_request("GET", f"http://127.0.0.1:{server.port}/br")
        assert r.ok and r.status == 200
        # 线上原始（压缩后）字节数应大于解压后
        assert r.raw_len > len(r.body)
        assert json.loads(r.body)["hello"] == "world"
