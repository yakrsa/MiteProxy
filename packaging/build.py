#!/usr/bin/env python3
"""
MiteProxy Windows 一键打包（自包含，无需其它脚本）。

用法：
  python packaging/build.py                 # 构建 onedir + 压 zip
  python packaging/build.py --check         # 额外解压产物并冒烟校验端口 8888
  python packaging/build.py --version 2.0.0  # 指定 zip 命名版本（默认取 git describe）

前置：已激活 venv 且装好 pyinstaller（脚本会自动尝试 pip 安装）。
产物：dist/MiteProxy-<ver>-windows-x64.zip（解压得 MiteProxy/ 文件夹，内含 MiteProxy.exe + _internal/）。

说明：
  - 用 --distpath dist_build --workpath build_build 全新目录构建，绕开本机清场不可靠的坑。
  - 压包【不排】 _internal 内的 .zip（base_library.zip 是 PyInstaller 必需文件，含 encodings
    标准库），缺它会导致解压运行报 "Failed to import encodings module"。
"""
import os
import sys
import argparse
import subprocess
import zipfile
import shutil
import socket
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISTPATH = os.path.join(ROOT, "dist_build")
WORKPATH = os.path.join(ROOT, "build_build")
SPEC = os.path.join(ROOT, "packaging", "miteproxy.spec")
EXCLUDE_LOGS = {"pyinstaller_build.log", "smoke.log"}


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def ensure_pyinstaller():
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyinstaller"], cwd=ROOT, check=True)


def build():
    # 全新目录绕开本机清场不可靠（残留被复用出假包）
    shutil.rmtree(DISTPATH, ignore_errors=True)
    shutil.rmtree(WORKPATH, ignore_errors=True)
    ensure_pyinstaller()
    run([sys.executable, "-m", "PyInstaller", SPEC, "--noconfirm",
         "--distpath", DISTPATH, "--workpath", WORKPATH])
    exe = os.path.join(DISTPATH, "MiteProxy", "MiteProxy.exe")
    if not os.path.isfile(exe):
        sys.exit("构建失败：未找到 " + exe)


def git_version():
    try:
        return subprocess.check_output(["git", "describe", "--tags", "--always"], cwd=ROOT).decode().strip()
    except Exception:
        return "local"


def zipit(version):
    src = os.path.join(DISTPATH, "MiteProxy")
    out = os.path.join(ROOT, "dist", f"MiteProxy-{version}-windows-x64.zip")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(src):
            for f in files:
                if f.lower().endswith(".log") or f in EXCLUDE_LOGS:
                    continue
                p = os.path.join(root, f)
                rel = os.path.relpath(p, src).replace("\\", "/")
                # 仅排除源目录【顶层】旧发布 zip；_internal 内 .zip（base_library.zip）必保留
                if rel.lower().endswith(".zip") and "/" not in rel:
                    continue
                z.write(p, "MiteProxy/" + rel)
                n += 1
    # 铁证校验：base_library.zip 必须在，否则解压必报 encodings 失败
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "MiteProxy/_internal/base_library.zip" in names, "FATAL: base_library.zip 缺失！"
    print(f"OK: {out} ({n} 文件, base_library.zip 已包含)")
    return out


def smoke_check(out):
    td = tempfile.mkdtemp(prefix="mp_smoke_")
    try:
        with zipfile.ZipFile(out) as z:
            z.extractall(td)
        exe = os.path.join(td, "MiteProxy", "MiteProxy.exe")
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        p = subprocess.Popen([exe], cwd=td, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(13)
        s = socket.socket()
        r = s.connect_ex(("127.0.0.1", 8888))
        s.close()
        p.terminate()
        print("冒烟:", "PORT_OPEN 8888 ✅ 解压产物可正常运行" if r == 0 else "PORT_CLOSED ❌ 仍不可用")
        return r == 0
    finally:
        shutil.rmtree(td, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="解压产物并冒烟校验 8888")
    ap.add_argument("--version", default=None, help="zip 命名版本，默认 git describe")
    args = ap.parse_args()
    build()
    ver = args.version or git_version()
    out = zipit(ver)
    if args.check:
        if not smoke_check(out):
            sys.exit("冒烟校验失败")
    print("完成:", out)


if __name__ == "__main__":
    main()
