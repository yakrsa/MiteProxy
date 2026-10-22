"""SSE 解析与展示测试（路线图 #8）。"""

import pytest
from PySide6.QtWidgets import QApplication

from app.bodyview import VIEW_SSE, detect_view_mode
from app.sse import MAX_EVENTS, is_sse, parse_sse
from app.ui.detail_panel import BodyPane


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def body_pane(qapp):
    return BodyPane()


# ---------------------------------------------------------------- 解析器


def test_is_sse():
    assert is_sse("text/event-stream")
    assert is_sse("text/event-stream; charset=utf-8")
    assert is_sse("TEXT/EVENT-STREAM")
    assert not is_sse("text/plain")
    assert not is_sse("")
    assert not is_sse(None)


def test_parse_basic_events():
    text = (
        "event: message\n"
        "id: 1\n"
        "data: hello\n"
        "\n"
        "data: world\n"
        "\n"
    )
    result = parse_sse(text)
    assert len(result.events) == 2
    assert result.events[0].event == "message"
    assert result.events[0].id == "1"
    assert result.events[0].data == "hello"
    assert result.events[1].event == ""           # 缺省事件名（规范默认 message）
    assert result.events[1].data == "world"
    assert not result.trailing_incomplete


def test_parse_multiline_data_joins_with_newline():
    text = "data: line1\ndata: line2\ndata: line3\n\n"
    result = parse_sse(text)
    assert result.events[0].data == "line1\nline2\nline3"


def test_parse_strips_single_leading_space_only():
    # "data:  x"（两个空格）→ 值是一个空格 + x；"data:x" → x
    text = "data:  x\n\ndata:y\n\n"
    result = parse_sse(text)
    assert result.events[0].data == " x"
    assert result.events[1].data == "y"


def test_parse_comments_ignored():
    text = ": keep-alive\ndata: after comment\n\n"
    result = parse_sse(text)
    assert len(result.events) == 1
    assert result.events[0].data == "after comment"


def test_parse_retry_field():
    text = "retry: 3000\ndata: x\n\n"
    result = parse_sse(text)
    assert result.events[0].retry == "3000"


def test_parse_trailing_incomplete():
    """流还在写：最后一段没有空行收尾 → 标不完整但仍展示。"""
    text = "data: first\n\ndata: partial"
    result = parse_sse(text)
    assert len(result.events) == 2
    assert result.trailing_incomplete
    assert result.events[1].data == "partial"
    assert not result.events[1].complete
    assert result.events[0].complete


def test_parse_empty_and_blank_lines():
    assert parse_sse("").events == []
    # 连续空行不产生空事件
    assert parse_sse("\n\n\n").events == []


def test_parse_truncates_at_max_events():
    text = "data: x\n\n" * (MAX_EVENTS + 10)
    result = parse_sse(text)
    assert len(result.events) == MAX_EVENTS
    assert result.truncated


def test_parse_crlf_and_cr():
    text = "data: a\r\n\r\ndata: b\r\r"
    result = parse_sse(text)
    assert len(result.events) == 2
    assert result.events[0].data == "a"
    assert result.events[1].data == "b"


# ---------------------------------------------------------------- 视图选择


def test_detect_view_mode_sse():
    assert detect_view_mode("text/event-stream", b"data: x\n\n") == VIEW_SSE
    assert detect_view_mode(
        "text/event-stream; charset=utf-8", b"data: x\n\n"
    ) == VIEW_SSE


# ---------------------------------------------------------------- BodyPane


def _show(body: bytes, content_type="text/event-stream"):
    pane = BodyPane()
    pane.show_body(
        {"content-type": content_type} if content_type else {},
        body,
    )
    return pane


def test_body_pane_renders_sse_events(body_pane):
    text = "event: message\nid: 1\ndata: hello\n\ndata: world\n\n"
    body_pane.show_body({"content-type": "text/event-stream"}, text.encode())
    assert body_pane.current_mode == VIEW_SSE
    shown = body_pane.body_view.toPlainText()
    assert "事件 1" in shown
    assert "event: message" in shown
    assert "id: 1" in shown
    assert "data: hello" in shown
    assert "事件 2" in shown
    assert "data: world" in shown
    # 提示行：2 个事件
    assert "2 个事件" in body_pane.view_note.text()


def test_body_pane_sse_incomplete_note(body_pane):
    body_pane.show_body(
        {"content-type": "text/event-stream"}, b"data: partial"
    )
    shown = body_pane.body_view.toPlainText()
    assert "未收尾" in shown
    assert "最后一个未收尾" in body_pane.view_note.text()


def test_body_pane_sse_empty(body_pane):
    body_pane.show_body({"content-type": "text/event-stream"}, b"")
    # 空 body 走「（空 body）」分支，不进 SSE 渲染
    assert body_pane.body_view.toPlainText() == "（空 body）"


def test_body_pane_sse_no_events(body_pane):
    body_pane.show_body({"content-type": "text/event-stream"}, b"\n\n: comment\n")
    assert "未解析到 SSE 事件" in body_pane.view_note.text()


def test_body_pane_sse_manual_mode_sticky(body_pane):
    """手动切到别的视图后换会话不回弹（粘性语义与其它视图一致）。"""
    body_pane.show_body({"content-type": "text/event-stream"}, b"data: x\n\n")
    assert body_pane.current_mode == VIEW_SSE
    body_pane.set_mode("raw")
    body_pane.show_body({"content-type": "text/event-stream"}, b"data: y\n\n")
    assert body_pane.current_mode == "raw"
    # 切回自动仍然是 SSE
    body_pane.set_mode("auto")
    body_pane.show_body({"content-type": "text/event-stream"}, b"data: z\n\n")
    assert body_pane.current_mode == VIEW_SSE
