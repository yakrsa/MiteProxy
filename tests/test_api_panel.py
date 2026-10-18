"""ApiPanel UI 测试：请求构建 / 从流量带入 / 发送线程回包。"""

import json
import time

import pytest

from tests.test_httpclient import MiniHTTPServer

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def server():
    srv = MiniHTTPServer()
    srv.serve_forever()
    yield srv
    srv.close()


def _panel(qapp):
    from app.ui.api_panel import ApiPanel

    return ApiPanel()


class TestApiPanel:
    def test_load_request_fills_fields(self, qapp):
        panel = _panel(qapp)
        panel.load_request(
            method="POST",
            url="https://a.com/api/x",
            headers={"Content-Type": "application/json", "X-Token": "t1"},
            body='{"a":1}',
        )
        assert panel.method_combo.currentText() == "POST"
        assert panel.url_edit.text() == "https://a.com/api/x"
        assert panel._collect_headers() == {
            "Content-Type": "application/json",
            "X-Token": "t1",
        }
        assert panel.body_edit.toPlainText() == '{"a":1}'
        panel.deleteLater()

    def test_send_and_show_response(self, qapp, server):
        panel = _panel(qapp)
        panel.url_edit.setText(f"http://127.0.0.1:{server.port}/echo")
        panel.body_edit.setPlainText("hello")
        panel._on_send()
        # 后台线程回包：轮询等 finished 处理完
        deadline = time.time() + 5
        while time.time() < deadline and panel._sending:
            qapp.processEvents()
            time.sleep(0.02)
        qapp.processEvents()
        assert "HTTP 200" in panel.resp_label.text()
        assert "X-Echo" not in panel.resp_label.text()
        # BodyPane 显示了响应
        assert panel.resp_pane.body_bytes is not None
        payload = json.loads(panel.resp_pane.body_bytes)
        assert payload["body"] == "hello"
        panel.deleteLater()

    def test_response_headers_table_populated(self, qapp, server):
        """bug2：API 调试页要渲染响应 Header 表，不能只数个数。"""
        panel = _panel(qapp)
        panel.url_edit.setText(f"http://127.0.0.1:{server.port}/echo")
        panel.body_edit.setPlainText("hello")
        panel._on_send()
        deadline = time.time() + 5
        while time.time() < deadline and panel._sending:
            qapp.processEvents()
            time.sleep(0.02)
        qapp.processEvents()
        assert panel.resp_headers_table.rowCount() > 0
        names = [
            panel.resp_headers_table.item(r, 0).text()
            for r in range(panel.resp_headers_table.rowCount())
        ]
        assert "X-Echo" in names
        panel.deleteLater()

    def test_gzip_response_body_shown_as_text(self, qapp, server):
        """bug1：gzip 压缩响应经 httpclient 解压后，BodyPane 应显示明文而非十六进制。"""
        panel = _panel(qapp)
        panel.url_edit.setText(f"http://127.0.0.1:{server.port}/gz")
        panel._on_send()
        deadline = time.time() + 5
        while time.time() < deadline and panel._sending:
            qapp.processEvents()
            time.sleep(0.02)
        qapp.processEvents()
        assert "HTTP 200" in panel.resp_label.text()
        body = panel.resp_pane.body_bytes
        assert body is not None
        payload = json.loads(body)
        assert payload["hello"] == "world"
        panel.deleteLater()

    def test_send_error_shown(self, qapp):
        panel = _panel(qapp)
        panel.url_edit.setText("http://127.0.0.1:1/")  # 不可达
        panel._on_send()
        deadline = time.time() + 5
        while time.time() < deadline and panel._sending:
            qapp.processEvents()
            time.sleep(0.02)
        qapp.processEvents()
        assert "✗" in panel.resp_label.text() and "连接失败" in panel.resp_label.text()
        panel.deleteLater()

    def test_empty_url_rejected(self, qapp):
        panel = _panel(qapp)
        panel.url_edit.setText("")
        panel._on_send()
        assert not panel._sending
        assert "URL" in panel.resp_label.text()
        panel.deleteLater()

    def test_seq_guards_stale_result(self, qapp):
        """旧请求的结果不能覆盖新状态（连点保护）。"""
        panel = _panel(qapp)
        panel._seq = 3
        from app.httpclient import ApiResponse

        panel._on_finished((2, ApiResponse(ok=True, status=200)))
        assert "HTTP 200" not in panel.resp_label.text()
        panel._on_finished((3, ApiResponse(ok=True, status=201)))
        assert "HTTP 201" in panel.resp_label.text()
        panel.deleteLater()
