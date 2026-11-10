$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $Python)) { throw '请先运行 scripts/start-dev.ps1 或创建 .venv。' }
Push-Location (Join-Path $Root 'backend-api')
try { & $Python -m app.seed; & $Python -m app.reindex_seed } finally { Pop-Location }
