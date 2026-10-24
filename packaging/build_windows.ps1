# Windows 一键构建（DESIGN.md 阶段 6，方案 A：本地构建）
# 用法：powershell -ExecutionPolicy Bypass -File .\packaging\build_windows.ps1 -Version 2.7.1
#       -Version 必填，不设默认值；且必须与 app\version.py 的 __version__ 一致
# 产物：dist\MiteProxy-v<版本>-windows-x64.zip
#       zip 内是完整的 MiteProxy 文件夹（MiteProxy.exe + _internal 依赖目录），
#       解压后双击 MiteProxy.exe 即可直接使用，无需安装。
param(
    [string]$Version = ""
)
$ErrorActionPreference = 'Stop'

Set-Location (Join-Path $PSScriptRoot '..')
Write-Host "==> 项目根目录: $(Get-Location)"

# ---- 版本号闸门：必须显式传入，且与代码里的版本一致 ----------------------
if ([string]::IsNullOrWhiteSpace($Version)) {
    throw ("缺少 -Version。必须显式指定本次发布的版本号（不设默认值），例如：`n" +
           "    .\packaging\build_windows.ps1 -Version 2.7.1")
}
if ($Version -notmatch '^\d+\.\d+(\.\d+)?$') {
    throw "-Version 格式不合法：'$Version'（应形如 2.7.1）"
}

$versionPy = ".\app\version.py"
if (-not (Test-Path $versionPy)) {
    throw "找不到 $versionPy，无法校验版本号"
}
$m = Select-String -Path $versionPy -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $m) {
    throw "无法从 $versionPy 解析 __version__"
}
$pyVersion = $m.Matches[0].Groups[1].Value
if ($pyVersion -ne $Version) {
    throw ("版本号不一致：-Version $Version，而 app\version.py 是 $pyVersion。`n" +
           "    请先确认发版版本号（同步改 app\version.py 与 version.info）再构建。")
}
Write-Host "==> 版本号: $Version（与 app\version.py 一致）"

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
