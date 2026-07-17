$Root = "F:\Desktop Backup\Mahmoud-2026\mt5-bot"
$Venv = "$Root\.venv\Scripts\Activate.ps1"

function Start-BotWindow {
    param(
        [string]$Title,
        [string]$Command
    )

    $FullCommand = @"
Set-Location -LiteralPath '$Root'
. '$Venv'
`$Host.UI.RawUI.WindowTitle = '$Title'
$Command
"@

    Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $FullCommand
}

Start-BotWindow -Title "MT5 LIVE BOT" -Command "python -m src.live_bot"

Start-BotWindow -Title "PHASE 3 AUTO STATS" -Command "python .\scripts\auto_refresh_phase3_statistics.py --interval-seconds 900"