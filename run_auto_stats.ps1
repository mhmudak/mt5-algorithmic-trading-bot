$Root = "F:\Desktop Backup\Mahmoud-2026\mt5-bot"
$Python = "$Root\.venv\Scripts\python.exe"

$Host.UI.RawUI.WindowTitle = "PHASE 3 AUTO STATS"
Set-Location -LiteralPath $Root
& $Python .\scripts\auto_refresh_phase3_statistics.py --interval-seconds 900