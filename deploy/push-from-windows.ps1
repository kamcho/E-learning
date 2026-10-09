# Sync local Elearning project to the server (run from repo root on Windows).
# Does NOT send .env, .venv, __pycache__, or .git unless you opt in.
#
#   $env:DEPLOY_HOST = '185.170.196.219'
#   $env:DEPLOY_USER = 'root'
#   .\deploy\push-from-windows.ps1
#
# Requires OpenSSH scp/rsync (Git for Windows) or WSL rsync.

param(
  [string]$Host = $(if ($env:DEPLOY_HOST) { $env:DEPLOY_HOST } else { '185.170.196.219' }),
  [string]$User = $(if ($env:DEPLOY_USER) { $env:DEPLOY_USER } else { 'root' }),
  [string]$RemoteDir = '/srv/elearning'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path (Join-Path $Root 'manage.py'))) {
  throw "Run from the Elearning repo (manage.py not found in $Root)"
}

$Dest = "${User}@${Host}:${RemoteDir}/"
Write-Host "Syncing $Root -> $Dest"

$rsync = Get-Command rsync -ErrorAction SilentlyContinue
if ($rsync) {
  & rsync -avz --delete `
    --exclude '.git/' --exclude '.venv/' --exclude '__pycache__/' `
    --exclude '*.pyc' --exclude '.env' --exclude 'media/' `
    --exclude 'staticfiles/' --exclude '_tmp_*' `
    -e ssh `
    "$Root/" $Dest
} else {
  Write-Host "rsync not found; using scp (slower, no deletes)."
  ssh "${User}@${Host}" "mkdir -p $RemoteDir"
  scp -r "$Root\*" "${User}@${Host}:${RemoteDir}/"
}

Write-Host "Done. On server run: bash $RemoteDir/deploy/bootstrap.sh (first time) or $RemoteDir/deploy/update.sh"
