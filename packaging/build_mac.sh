#!/usr/bin/env bash
# macOS 一键构建（DESIGN.md 阶段 6，方案 A：本地构建）
# 用法：./packaging/build_mac.sh
set -euo pipefail

cd "$(dirname "$0")/.."
echo "==> 项目根目录: $(pwd)"

PYTHON=${PYTHON:-python3}

if [ ! -d .venv ]; then
    echo "==> 创建虚拟环境"
    "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> 安装依赖"
pip install -q -r requirements.txt
pip install -q pyinstaller

echo "==> PyInstaller 构建"
pyinstaller packaging/miteproxy.spec --noconfirm --clean

echo ""
echo "==> 完成: dist/MiteProxy.app"
echo "    首次运行如被 Gatekeeper 拦截：右键 -> 打开"
