$Root = "F:\Desktop Backup\Mahmoud-2026\mt5-bot"

$LiveBotScript = Join-Path $Root "run_live_bot.ps1"
$AutoStatsScript = Join-Path $Root "run_auto_stats.ps1"

Start-Process powershell.exe -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$LiveBotScript`""
Start-Process powershell.exe -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$AutoStatsScript`""