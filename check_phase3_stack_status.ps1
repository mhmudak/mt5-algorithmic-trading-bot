$processes = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
    Select-Object ProcessId, CommandLine

$liveBot = $processes | Where-Object { $_.CommandLine -like "*src.live_bot*" }
$autoStats = $processes | Where-Object { $_.CommandLine -like "*auto_refresh_phase3_statistics.py*" }

Write-Host ""
Write-Host "[PHASE 3 STACK STATUS]"
Write-Host "live_bot count      =" $liveBot.Count
Write-Host "auto_stats count    =" $autoStats.Count
Write-Host ""

if ($liveBot.Count -eq 1) {
    Write-Host "LIVE BOT: OK"
} elseif ($liveBot.Count -eq 0) {
    Write-Host "LIVE BOT: NOT RUNNING"
} else {
    Write-Host "LIVE BOT: DANGER - MULTIPLE LIVE BOTS RUNNING"
}

if ($autoStats.Count -eq 1) {
    Write-Host "AUTO STATS: OK"
} elseif ($autoStats.Count -eq 0) {
    Write-Host "AUTO STATS: NOT RUNNING"
} else {
    Write-Host "AUTO STATS: DUPLICATED"
}

Write-Host ""
Write-Host "[PYTHON PROCESSES]"
$processes | Format-Table -AutoSize