"""意见反馈：应用内一键提交 GitHub Issue（v1.15）。

无服务器方案的反馈通道——用户在反馈对话框填写标题和内容，
应用自动附带版本 / 系统诊断信息，通过 GitHub Issues API 直接创建 issue。

认证：GitHub 创建 issue 必须带 token（不能匿名提交）。这里内置一个
fine-grained PAT（EMBEDDED_FEEDBACK_TOKEN），只授权 yakrsa/MiteProxy
一个仓库的 Issues 写权限——即使 token 被从包里提取，最坏影响也只是
有人往该仓库灌垃圾 issue。打包前把 token 填进该常量（或用环境变量
MITEPROXY_FEEDBACK_TOKEN 覆盖，便于本地测试）。

分层：本模块是纯函数层（payload / headers / 响应解析 / 错误提示），
网络发送在 UI 层用 QNetworkAccessManager 异步完成，测试注入假传输层。
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
from pathlib import Path

from app.version import __version__
from PySide6.QtCore import QCoreApplication

# ---------------------------------------------------------------- 常量

#: 版本号单一事实源在 app/version.py 的 __version__，这里统一加 "v" 前缀。
APP_VERSION = "v" + __version__
GITHUB_REPO = "yakrsa/MiteProxy"
ISSUES_URL = f"https://github.com/{GITHUB_REPO}/issues"
ISSUES_API = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
NEW_ISSUE_URL = f"https://github.com/{GITHUB_REPO}/issues/new"

TOKEN_ENV = "MITEPROXY_FEEDBACK_TOKEN"
# fine-grained PAT（仅 yakrsa/MiteProxy 的 Issues 写权限，泄露最坏影响=灌垃圾 issue）
EMBEDDED_FEEDBACK_TOKEN = (
    "github_pat_11AAVC4IA0IsytIfwzjjk0_"
    "y27Zbdzqpup1PDejteHrm7Hh6vE0Xgz1nDo7W7wDYT3ZJPPS7RIsDS4y5it"
)
# 本机 token 文件（开发机覆盖用，优先级介于环境变量与内置常量之间；
# 打包版用户机器上没有该文件，自然回落到内置 token）
TOKEN_FILE = Path("~/.miteproxy/feedback_token").expanduser()

REQUEST_TIMEOUT_MS = 15000

# 反馈人昵称：必填，最长 64 字符（GitHub issue 作者只能是 token 账号
# 本人，昵称放进标题/正文，让反馈可追溯）
NICKNAME_MAX_LEN = 64


def get_token() -> str:
    """运行时读取：环境变量 > 本机 token 文件 > 内置常量。

    分层覆盖便于测试（env）与开发机调试（文件），发布版只用内置常量。
    """
    env = os.environ.get(TOKEN_ENV, "").strip()
    if env:
        return env
    try:
        file_token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        file_token = ""
    return file_token or EMBEDDED_FEEDBACK_TOKEN.strip()


# ---------------------------------------------------------------- 诊断信息

def collect_diagnostics() -> str:
    """采集提交 issue 时自动附带的环境诊断信息（多行纯文本）。"""
    lines = [
        f"- App 版本: {APP_VERSION}",
        f"- 系统: {platform.system()} {platform.release()} "
        f"({platform.machine()})",
        f"- Python: {platform.python_version()}",
        f"- 打包运行: {'是' if getattr(sys, 'frozen', False) else '否'}",
    ]
    try:
        from PySide6 import QtCore  # 延迟导入：纯函数层测试可不依赖 Qt 细节

        lines.append(f"- Qt: {QtCore.qVersion()}")
    except Exception:  # pragma: no cover - 未装 Qt 时仅少一行
        pass
    return "\n".join(lines)


def build_issue_body(content: str, diagnostics: str, nickname: str = "") -> str:
    """用户反馈正文 + 昵称 + 诊断信息合并为 issue body。"""
    text = (content or "").strip()
    nick = (nickname or "").strip()[:NICKNAME_MAX_LEN]
    if nick:
        text = f"**反馈人：{nick}**\n\n{text}"
    diag = (diagnostics or "").strip()
    if diag:
        text = f"{text}\n\n---\n\n**诊断信息（自动生成）**\n\n```text\n{diag}\n```"
    return text


# ---------------------------------------------------------------- 请求构造

def build_issue_title(nickname: str, title: str) -> str:
    """issue 标题 = [昵称] 用户标题（昵称超长时先截断）。"""
    nick = (nickname or "").strip()[:NICKNAME_MAX_LEN]
    t = (title or "").strip()
    return f"[{nick}] {t}" if nick else t


def payload(title: str, body: str, labels: list[str] | None = None) -> dict:
    return {
        "title": (title or "").strip()[:200],
        "body": body,
        "labels": list(labels) if labels else ["feedback"],
    }


def headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": f"MiteProxy-feedback/{APP_VERSION}",
    }


# ---------------------------------------------------------------- 响应解析

def describe_result(status: int, err: str = "") -> str:
    """把 GitHub API / 网络层的结果转成用户可读的一句话提示。"""
    if status == 0:
        return QCoreApplication.translate(
            "feedback", "网络请求失败：{0}。请检查网络后重试。"
        ).format(err or QCoreApplication.translate("feedback", "无法连接 GitHub"))
    if status == 401:
        return QCoreApplication.translate("feedback", "提交失败：反馈凭证无效（token 已过期或被撤销）。")
    if status == 403:
        if "rate limit" in (err or "").lower():
            return QCoreApplication.translate("feedback", "提交失败：GitHub 接口限流，请稍后再试。")
        return QCoreApplication.translate("feedback", "提交失败：没有创建 issue 的权限（token 权限不足）。")
    if status == 404:
        return QCoreApplication.translate("feedback", "提交失败：仓库不存在或 token 未授权该仓库。")
    if status == 422:
        return QCoreApplication.translate("feedback", "提交失败：内容未通过 GitHub 校验（标题或正文可能过长）。")
    if 500 <= status < 600:
        return QCoreApplication.translate("feedback", '提交失败：GitHub 服务暂时不可用（HTTP {0}），请稍后再试。').format(status)
    return QCoreApplication.translate("feedback", '提交失败：HTTP {0} {1}').format(status, err).strip()


def parse_issue_response(status: int, raw: bytes, err: str = "") -> tuple[bool, str, str]:
    """解析 GitHub API 响应 -> (ok, 提示语, issue_url)。"""
    if status == 201:
        url = ""
        try:
            data = json.loads(raw.decode("utf-8"))
            url = data.get("html_url", "") or ""
        except Exception:
            pass
        return True, QCoreApplication.translate("feedback", "反馈已提交，感谢！"), url
    return False, describe_result(status, err), ""


# ---------------------------------------------------------------- 崩溃报告脱敏

#: 需要整行抹掉的敏感头。代理抓包日志里出现 Authorization / Cookie 是常态，
#: 而这两个头一旦泄露就等于泄露了用户的登录态。
_SECRET_HEADERS = (
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-csrf-token",
)

#: 同一条 URL 里出现这些参数名时，整个 query 都不留（宁可少给信息）。
#: 两个坑都要避开：① 只匹配参数名、不匹配值，替换后值还挂在后面，等于没脱敏；
#: ② 用 ``\btoken`` 匹配不到 ``access_token``——下划线也是单词字符，没有边界。
#: 所以这里带上前缀一起匹配，整体替换。
_SECRET_QUERY_HINT = re.compile(
    r"(?i)([A-Za-z0-9_\-]*(?:access_token|refresh_token|token|secret|password|"
    r"passwd|pwd|sessionid|session|cookie|authorization|auth|signature|"
    r"access_key|api_key|apikey|ticket|credential))"
    r"(\s*=\s*)([^\s&\"'<>;,)]+)"
)

_RE_HEADER_LINE = re.compile(
    r"(?im)^(\s*(?:" + "|".join(_SECRET_HEADERS) + r")\s*[:=]\s*)(.*)$"
)
_RE_URL = re.compile(r"(?i)\b(https?://[^\s?#\"'<>]+)(\?[^\s#\"'<>]*)?")


def redact(text: str, keep_urls: bool = False) -> str:
    """把诊断文本里的凭据抹掉再上报。

    ``keep_urls=False``（默认）时连 URL 的 query 一起抹掉——抓包日志里的
    query 常常带 ``access_token`` / 会话票据，而 path 本身通常不足以定位问题。
    ``keep_urls=True`` 时保留 host 与 path（协议、域名、接口路径对排查有用），
    仅抹掉 query；用于用户明确勾选「包含请求地址」的场景。

    这段代码跑在上报前，宁可抹多不可漏——漏一个 token 的代价远大于丢一点线索。
    """
    if not text:
        return ""

    out = _RE_HEADER_LINE.sub(lambda m: f"{m.group(1)}<已脱敏>", text)

    def _url(match: re.Match) -> str:
        base, query = match.group(1), match.group(2) or ""
        if not query:
            return base
        if keep_urls:
            # 保留参数名与个数，值一律不给：既说明"带了 3 个参数"，又不泄露值
            names = [part.split("=", 1)[0] for part in query[1:].split("&") if part]
            masked = "&".join(f"{n}=<已脱敏>" for n in names)
            return f"{base}?{masked}"
        return f"{base}?<已脱敏>"

    out = _RE_URL.sub(_url, out)
    # 无条件再跑一遍：keep_urls 模式放过了 URL，但日志里还可能有被拆行的
    # 裸参数（如 traceback 里带出的 access_token=…），那些同样要抹。
    out = _SECRET_QUERY_HINT.sub(
        lambda m: f"{m.group(1)}{m.group(2)}<已脱敏>", out
    )
    return out


def build_crash_body(summary: dict, diagnostics: str = "",
                     include_actions: bool = True,
                     include_urls: bool = False) -> str:
    """组装崩溃报告 issue 正文。

    分层组织：结论（何时、什么类型）在最上，诊断信息其次，最容易污染视线的
    栈与操作轨迹收进折叠块——既保证信息完整，又不让维护者一打开就看到几百行日志。
    """
    detected = summary.get("detected_at", "未知")
    started = summary.get("started_at", "")
    version = summary.get("version", "未知")
    excerpt = redact(summary.get("excerpt", ""), keep_urls=include_urls)
    hang = redact(summary.get("hang", ""), keep_urls=include_urls)
    actions = summary.get("actions") or []

    kinds = []
    if excerpt.strip():
        kinds.append("崩溃")
    if hang.strip():
        kinds.append("界面卡死")
    kind_text = " / ".join(kinds) or "非正常退出"

    lines = [
        f"**类型**：{kind_text}",
        f"**检测到的时间**：{detected}",
        f"**上个进程启动于**：{started or '未知'}",
        f"**程序版本**：v{version}",
    ]

    diag = (diagnostics or "").strip()
    if diag:
        lines += ["", "---", "", "**诊断信息（自动生成）**", "", "```text", diag, "```"]

    if excerpt.strip():
        lines += [
            "", "<details><summary>崩溃栈与 Qt 消息（crash.log）</summary>",
            "", "```text", excerpt, "```", "", "</details>",
        ]
    if hang.strip():
        lines += [
            "", "<details><summary>卡死采样（hang.log）</summary>",
            "", "```text", hang, "```", "", "</details>",
        ]
    if include_actions and actions:
        shown = [redact(a, keep_urls=include_urls) for a in actions]
        lines += [
            "", "<details><summary>最近操作（actions.log）</summary>",
            "", "```text", "\n".join(shown), "```", "", "</details>",
        ]

    lines += [
        "", "<!-- 由 MiteProxy 崩溃诊断上报自动生成 -->",
    ]
    return "\n".join(lines)


def crash_issue_title(summary: dict) -> str:
    """标题自动带上版本与类型，方便按版本聚类同一问题。"""
    version = summary.get("version", "?")
    parts = []
    if (summary.get("excerpt") or "").strip():
        # 优先用栈里最有用的一行：异常类型/故障模块比时间戳有价值得多
        for line in (summary["excerpt"] or "").splitlines():
            low = line.strip()
            if not low:
                continue
            if ("fatal exception" in low.lower()
                    or low.endswith("Error")
                    or "Exception" in low
                    or "0x" in low and "exception" in low.lower()):
                parts.append(low[:90])
                break
    if (summary.get("hang") or "").strip():
        parts.append("界面卡死")
    elif parts:
        parts.append("崩溃")
    detail = " · ".join(parts) or "非正常退出"
    return f"[自动上报] v{version} {detail}"[:200]
