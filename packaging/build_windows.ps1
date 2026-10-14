# Windows 一键构建（DESIGN.md 阶段 6，方案 A：本地构建）
# 用法：powershell -ExecutionPolicy Bypass -File .\packaging\build_windows.ps1
$ErrorActionPreference = 'Stop'

Set-Location (Join-Path $PSScriptRoot '..')
Write-Host "==> 项目根目录: $(Get-Location)"

if (-not (Test-Path .\.venv)) {
    Write-Host "==> 创建虚拟环境"
    python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1

Write-Host "==> 安装依赖"
pip install -q -r requirements.txt
pip install -q pyinstaller

Write-Host "==> PyInstaller 构建"
pyinstaller packaging\miteproxy.spec --noconfirm --clean

Write-Host ""
Write-Host "==> 完成: dist\MiteProxy\MiteProxy.exe"
Write-Host "    首次运行：Windows 防火墙弹窗请允许'专用网络'；杀毒软件如误报请加白"
