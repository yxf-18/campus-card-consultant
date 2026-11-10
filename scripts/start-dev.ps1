$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (!(Test-Command 'python') -and !(Test-Path "$Root\.venv\Scripts\python.exe")) {
    throw '未找到 Python。请先安装 Python 3.12 并加入 PATH，或手动创建 .venv：python -m venv .venv'
}
if (!(Test-Command 'npm')) {
    throw '未找到 npm。请先安装 Node.js（18+）并加入 PATH，再执行 npm --prefix admin-web install 和 npm --prefix mobile-web install。'
}

if (!(Test-Path "$Root\.venv")) {
    Write-Host '首次启动：正在创建 Python 虚拟环境 .venv ...'
    python -m venv "$Root\.venv"
}
$Python = "$Root\.venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
    throw "虚拟环境不可用：$Python 不存在。请删除 .venv 目录后重新执行本脚本。"
}
& $Python -c "import sys" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw '虚拟环境 .venv 已失效（它记录的基础 Python 可能已被移动或卸载）。请删除 .venv 目录后重新执行本脚本，或手动执行：python -m venv .venv 并安装 backend-api/backend-ai 的 requirements。'
}

& (Join-Path $PSScriptRoot 'stop-dev.ps1')
Write-Host '正在安装/校验后端依赖，请稍候 ...'
& $Python -m pip install -r "$Root\backend-api\requirements.txt" -r "$Root\backend-ai\requirements.txt"
Push-Location "$Root\backend-api"
Start-Process -FilePath $Python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WindowStyle Hidden
Pop-Location
Push-Location "$Root\backend-ai"
Start-Process -FilePath $Python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8001' -WindowStyle Hidden
Pop-Location
Start-Process -FilePath 'npm' -ArgumentList 'run','dev' -WorkingDirectory "$Root\admin-web" -WindowStyle Hidden
Start-Process -FilePath 'npm' -ArgumentList 'run','dev' -WorkingDirectory "$Root\mobile-web" -WindowStyle Hidden
Write-Host 'Services starting: API 8000, AI 8001, admin 5173, mobile 5174.'
Start-Sleep -Seconds 5
Push-Location "$Root\backend-api"
try { & $Python -m app.reindex_seed } finally { Pop-Location }
Write-Host '启动完成：管理端 http://127.0.0.1:5173 ，移动端 http://127.0.0.1:5174'
