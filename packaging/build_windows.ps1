# Windows 一键构建（DESIGN.md 阶段 6，方案 A：本地构建）
# 用法：powershell -ExecutionPolicy Bypass -File .\packaging\build_windows.ps1
#       可选指定版本号：... -Version 1.14
# 产物：dist\MiteProxy-v<版本>-windows-x64.zip
#       zip 内是完整的 MiteProxy 文件夹（MiteProxy.exe + _internal 依赖目录），
#       解压后双击 MiteProxy.exe 即可直接使用，无需安装。
param(
    [string]$Version = "2.0.0"
)
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

Write-Host "==> PyInstaller 构建（onedir：exe + 依赖目录）"
pyinstaller packaging\miteproxy.spec --noconfirm --clean

$exe = "dist\MiteProxy\MiteProxy.exe"
if (-not (Test-Path $exe)) {
    throw "构建产物缺失：$exe 不存在，PyInstaller 可能失败了"
}

Write-Host "==> 打包 zip"
$zip = "dist\MiteProxy-v$Version-windows-x64.zip"
# 压缩整个 MiteProxy 文件夹：解压得到 MiteProxy\{MiteProxy.exe, _internal\...}
Compress-Archive -Path .\dist\MiteProxy -DestinationPath $zip -Force
$size = "{0:N1} MB" -f ((Get-Item $zip).Length / 1MB)

Write-Host ""
Write-Host "==> 完成: $zip ($size)"
Write-Host "    解压后进入 MiteProxy 文件夹，双击 MiteProxy.exe 直接使用（免安装）。"
Write-Host "    首次运行：Windows 防火墙弹窗请允许'专用网络'；杀毒软件如误报请加白"
