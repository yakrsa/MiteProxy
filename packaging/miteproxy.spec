# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 配置：macOS 产 .app，Windows 产 onedir 目录（DESIGN.md 阶段 6）
# 用法：pyinstaller packaging/miteproxy.spec --noconfirm --clean

import sys
from pathlib import Path

block_cipher = None

PROJECT = Path(SPECPATH).resolve().parent  # spec 在 packaging/ 下，项目根是其上级

a = Analysis(
    [str(PROJECT / "app" / "main.py")],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=[
        # 运行时窗口/任务栏图标（main.py 按 _MEIPASS 查找）：
        # ico 含 16-256 全尺寸帧（任务栏/标题栏各 DPI 清晰），png 兜底
        (str(PROJECT / "packaging" / "icon.ico"), "."),
        (str(PROJECT / "packaging" / "icon_256.png"), "."),
    ],
    hiddenimports=[
        # mitmproxy 按平台动态 import 的模块，PyInstaller 静态分析抓不到
        "mitmproxy.platform.osx" if sys.platform == "darwin" else "mitmproxy.platform.windows",
        # mitmproxy 的若干可选组件（DNS / TLS 后端等）
        "mitmproxy.addons.dns_resolver",
        "mitmproxy.addons.tlsconfig",
        "mitmproxy.proxy.mode_servers",
        # certserver.py 里是函数内延迟 import（缺失会静默降级成纯链接），显式钉住
        "segno",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 用不到的大块头，砍包体积
        "tkinter",
        "numpy",
        "pandas",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MiteProxy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # 无控制台窗口（GUI 应用）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None if sys.platform == "darwin" else str(PROJECT / "packaging" / "icon.ico"),
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        name="MiteProxy.app",
        icon=str(PROJECT / "packaging" / "icon.icns"),
        bundle_identifier="com.miteproxy.app",
        info_plist={
            "CFBundleShortVersionString": "2.0.0",
            "CFBundleName": "MiteProxy",
            "NSHighResolutionCapable": True,
        },
    )
else:
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="MiteProxy",
    )
