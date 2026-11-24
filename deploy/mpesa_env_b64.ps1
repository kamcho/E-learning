# Emit base64 of MPESA_* lines from local .env for GitHub Actions sync-mpesa-env workflow.
$Root = Split-Path $PSScriptRoot -Parent
$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) { throw "Missing $EnvFile" }
$lines = Get-Content $EnvFile | Where-Object {
    $_ -match '^\s*MPESA_' -and $_ -notmatch '^\s*#'
}
$body = ($lines -join "`n") + "`n"
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($body))
$b64 | Set-Clipboard
Write-Host "Copied MPESA .env block (base64) to clipboard ($($lines.Count) lines)."
Write-Host "Run: gh workflow run sync-mpesa-env.yml -f env_b64=`"<paste>`""
Write-Host $b64