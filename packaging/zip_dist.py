#!/usr/bin/env python3
"""
将 PyInstaller onedir 产物压缩为带 MiteProxy/ 外层文件夹的 zip。

用法：
    python packaging/zip_dist.py [--src <目录>] [--out dist/MiteProxy-XXXX-windows-x64.zip]

默认源目录：自动探测（优先 dist/MiteProxy，其次 dist/ 下含 MiteProxy.exe 的目录）。
默认输出名：取当前 git HEAD 短 SHA → dist/MiteProxy-<sha>-windows-x64.zip

zip 内结构（解压后得到 MiteProxy/ 文件夹）：
    MiteProxy/
        MiteProxy.exe
        _internal/
        ...
"""
import os
import sys
import zipfile
import subprocess
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git_short_sha():
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT)
            .decode()
            .strip()
        )
    except Exception:
        return "local"


def find_src():
    # 优先 spec 约定的 dist/MiteProxy，其次 dist/ 下任何含 MiteProxy.exe 的目录
    cands = [os.path.join(ROOT, "dist", "MiteProxy"), os.path.join(ROOT, "dist")]
    for c in cands:
        if os.path.isfile(os.path.join(c, "MiteProxy.exe")):
            return c
    return None


# 不压进发布包的非产物文件
# ⚠️ 绝不能排除 .zip：_internal/base_library.zip 是 PyInstaller 必需文件（含 encodings 标准库），
#    误排会导致解压运行报 "Failed to import encodings module"
EXCLUDE_EXT = {".log"}
EXCLUDE_NAMES = {"pyinstaller_build.log", "smoke.log"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None, help="源目录（默认自动探测）")
    ap.add_argument("--out", default=None, help="输出 zip 路径")
    args = ap.parse_args()

    src = args.src or find_src()
    if not src or not os.path.isfile(os.path.join(src, "MiteProxy.exe")):
        print(
            "ERROR: 未找到 onedir 产物（需源目录下含 MiteProxy.exe），请先构建",
            file=sys.stderr,
        )
        sys.exit(1)

    out = args.out or os.path.join(
        ROOT, "dist", f"MiteProxy-{git_short_sha()}-windows-x64.zip"
    )

    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(src):
            for f in files:
                if f.lower().endswith(tuple(EXCLUDE_EXT)) or f in EXCLUDE_NAMES:
                    continue
                p = os.path.join(root, f)
                rel = os.path.relpath(p, src).replace("\\", "/")
                # 仅排除源目录【顶层】的旧发布 zip（避免打进旧包）；
                # _internal 深处的 .zip（如 base_library.zip）必须保留
                if rel.lower().endswith(".zip") and "/" not in rel:
                    continue
                arcname = "MiteProxy/" + rel  # 顶层统一包一层 MiteProxy/ 文件夹
                z.write(p, arcname)
                n += 1

    size = os.path.getsize(out)
    print(f"OK: {out}")
    print(f"src: {src}")
    print(f"files: {n}, size: {size/1024/1024:.1f} MB")
    print("解压结构: MiteProxy/  ->  MiteProxy.exe + _internal/ ...")


if __name__ == "__main__":
    main()
