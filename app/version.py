"""应用版本号 —— 全仓库唯一事实源。

发版时只改这里的 ``__version__``：
- ``app.feedback.APP_VERSION`` 由它派生（"v" + __version__），用于关于框、
  反馈诊断、User-Agent；
- 仓库根的 ``version.info`` 的 ``version`` 字段需同步成同值（已有测试
  ``test_current_version_matches_repo_file`` 强制二者相等）。

不要把版本号再写死到别处，否则检查更新会判定失效。
"""

__version__ = "3.0.2"
