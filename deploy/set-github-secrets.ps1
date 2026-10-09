# Configure GitHub Actions deploy secrets (run once per server / password change).
# Requires: gh CLI logged in (gh auth login)
#
#   .\deploy\set-github-secrets.ps1
#   .\deploy\set-github-secrets.ps1 -Host 185.170.196.219

param(
  [string]$Host = '185.170.196.219',
  [string]$User = 'root',
  [string]$Repo = 'kamcho/E-learning'
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw 'Install GitHub CLI: https://cli.github.com/ then run gh auth login'
}

Write-Host "Setting DROPLET_HOST=$Host and DROPLET_USER=$User on $Repo"
gh secret set DROPLET_HOST --body $Host -R $Repo
gh secret set DROPLET_USER --body $User -R $Repo

$secure = Read-Host 'DROPLET_SSH_PASSWORD (root SSH password)' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

gh secret set DROPLET_SSH_PASSWORD --body $plain -R $Repo
$plain = $null

Write-Host 'Secrets updated. Push to main or run workflow_dispatch: Deploy to droplet'
