"""本轮 bug 修复的回归测试（v1.12 bug 排查）。"""

import json
import base64

import pytest

from app import settings as settings_mod
from app.session import SessionLimits, _encode_body, _decode_body, save_session, load_session
from mitmproxy.test import tflow


class TestSettingsCertPort:
    def test_bad_cert_port_falls_back(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"cert_port": "abc", "proxy_port": 9999}), encoding="utf-8")
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
        s = settings_mod.load_settings()
        assert s.cert_port == settings_mod.DEFAULT_CERT_PORT
        assert s.proxy_port == 9999

    def test_bad_proxy_port_falls_back(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"proxy_port": None}), encoding="utf-8")
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
        s = settings_mod.load_settings()
        assert s.proxy_port == settings_mod.DEFAULT_PROXY_PORT


class TestGeometryRoundtrip:
    def test_geometry_persists(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
        s = settings_mod.Settings(window_geometry=b"\x01\x02\x03geo")
        settings_mod.save_settings(s)
        loaded = settings_mod.load_settings()
        assert loaded.window_geometry == b"\x01\x02\x03geo"

    def test_broken_geometry_ignored(self):
        s = settings_mod.Settings.from_dict({"window_geometry": "!!!not-b64!!!"})
        assert s.window_geometry is None
        assert settings_mod.Settings.from_dict({}).window_geometry is None


class TestCrashReportPromptSetting:
    """「不再提示崩溃上报」是用户偏好，必须能存下来、也要能默认打开。"""

    def test_defaults_to_enabled(self):
        assert settings_mod.Settings.from_dict({}).crash_report_prompt is True

    def test_roundtrip(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
        settings_mod.save_settings(settings_mod.Settings(crash_report_prompt=False))
        assert settings_mod.load_settings().crash_report_prompt is False

    def test_missing_key_keeps_prompt(self):
        """老版本 settings.json 没有这个键，升级后不能变成不提示。"""
        assert settings_mod.Settings.from_dict(
            {"proxy_port": 8888}
        ).crash_report_prompt is True


class TestStreamingRawContent:
    def test_summarize_with_none_raw_content(self):
        """流式响应 raw_content=None 时 summarize 不能抛 TypeError 丢行。"""
        from addons.capture import CaptureAddon

        flow = tflow.tflow(resp=True)
        flow.response.raw_content = None
        summary = CaptureAddon.summarize(flow)
        assert summary["size"] == 0
        assert summary["status"] == 200


class TestNonUtf8BodyRoundtrip:
    def test_gbk_body_bytes_survive(self):
        """非 UTF-8 body 保存→恢复字节必须一致（此前被按 UTF-8 重编码篡改）。"""
        limits = SessionLimits()
        original = "中文内容".encode("gbk")
        rec, _ = _encode_body(original, "text/plain; charset=gbk", limits, 1_000_000)
        assert rec["encoding"] == "base64"  # 非 UTF-8 走 base64，字节可逆
        restored = _decode_body(rec)
        assert restored == original

    def test_utf8_body_still_text(self):
        limits = SessionLimits()
        rec, _ = _encode_body("你好".encode("utf-8"), "text/plain", limits, 1_000_000)
        assert rec["encoding"] == "text"
        assert _decode_body(rec) == "你好".encode("utf-8")

    def test_session_roundtrip_with_gbk_flow(self, tmp_path):
        """端到端：GBK 响应保存再读回，字节一致。"""
        flow = tflow.tflow(resp=True)
        flow.response.content = "响应中文".encode("gbk")
        flow.response.headers["Content-Type"] = "text/plain; charset=gbk"
        path = tmp_path / "s.jsonl"
        result = save_session(path, [flow])
        assert result.ok
        loaded = load_session(path)
        assert loaded.ok
        assert loaded.flows[0].response.raw_content == "响应中文".encode("gbk")
