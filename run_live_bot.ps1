$Root = "F:\Desktop Backup\Mahmoud-2026\mt5-bot"
$Python = "$Root\.venv\Scripts\python.exe"

$Host.UI.RawUI.WindowTitle = "MT5 LIVE BOT"
Set-Location -LiteralPath $Root
& $Python -m src.live_bot