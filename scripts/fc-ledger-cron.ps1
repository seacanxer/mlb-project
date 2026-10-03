# FC Ledger Cron (Windows dev) — same steps as scripts/fc-ledger-cron.sh.
# Schedule every 30 minutes:
#   schtasks /create /tn "FC Ledger Cron" /sc MINUTE /mo 30 `
#     /tr "powershell -ExecutionPolicy Bypass -File C:\path\to\repo\scripts\fc-ledger-cron.ps1"
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $root
$venv = Join-Path $root 'betting-machine-fc\venv\Scripts\python.exe'
$py = if (Test-Path -LiteralPath $venv) { $venv } else { 'python' }
Write-Output ("[ledger-cron] {0} log projections" -f (Get-Date).ToUniversalTime().ToString('o'))
& $py scripts/fc-log-projections.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output ("[ledger-cron] {0} grade + report" -f (Get-Date).ToUniversalTime().ToString('o'))
& $py scripts/fc-grade-projections.py --report-out reports/fc-model-performance.json
exit $LASTEXITCODE
