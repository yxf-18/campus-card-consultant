$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (!(Test-Path "$Root\.venv")) {
    python -m venv "$Root\.venv"
}
$Python = "$Root\.venv\Scripts\python.exe"
& (Join-Path $PSScriptRoot 'stop-dev.ps1')
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
