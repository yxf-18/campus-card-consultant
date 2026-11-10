$ErrorActionPreference = 'SilentlyContinue'
$Ports = 8000,8001,5173,5174
$ids = @()
foreach ($Port in $Ports) {
    try {
        $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)
        $ids += $connections | Select-Object -ExpandProperty OwningProcess
    } catch {
        # No listener on this port is a normal case.
    }
}
try {
    $extra = @(Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object { $_.CommandLine -match 'uvicorn app\.main:app' -or $_.CommandLine -match 'vite.*--port 517[34]' -or $_.CommandLine -match 'npm.*run dev' } |
        Select-Object -ExpandProperty ProcessId)
    $ids += $extra
} catch {
    # CIM process enumeration may be unavailable; port detection above is still useful.
}
$ids = $ids | Where-Object { $_ -and $_ -gt 0 } | Sort-Object -Unique
foreach ($processId in $ids) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}
Write-Host "Development services stopped. Checked $($ids.Count) process(es)."
