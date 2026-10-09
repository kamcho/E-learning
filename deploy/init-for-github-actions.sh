#!/usr/bin/env bash
# One-time: turn /srv/elearning into a git checkout so GitHub Actions can git pull.
# Preserves production .env (and leaves .venv in place if present).
# Run on the droplet as root:
#   bash /srv/elearning/deploy/init-for-github-actions.sh
set -euo pipefail

APP_DIR="/srv/elearning"
APP_USER="elearning"
REPO_URL="${ELEARNING_GITHUB_REPO:-https://github.com/kamcho/E-learning.git}"
BRANCH="${ELEARNING_GITHUB_BRANCH:-main}"
ENV_BACKUP="/root/elearning.env.github-actions.bak"

cd "$APP_DIR"

if [[ -f .env ]]; then
  cp -a .env "$ENV_BACKUP"
  echo "==> Backed up .env to $ENV_BACKUP"
fi

git config --global --add safe.directory "$APP_DIR"

if [[ ! -d .git ]]; then
  echo "==> Initializing git in $APP_DIR"
  git init -b "$BRANCH"
  git remote add origin "$REPO_URL"
else
  echo "==> Git repo exists; ensuring origin URL"
  if git remote get-url origin &>/dev/null; then
    git remote set-url origin "$REPO_URL"
  else
    git remote add origin "$REPO_URL"
  fi
fi

echo "==> Fetching $BRANCH from GitHub"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [[ -f "$ENV_BACKUP" ]]; then
  cp -a "$ENV_BACKUP" .env
  chown "$APP_USER":www-data .env
  chmod 640 .env
  echo "==> Restored production .env"
fi

chown -R "$APP_USER":www-data "$APP_DIR"
chmod +x "$APP_DIR/deploy/update.sh" 2>/dev/null || true

echo "==> Done. Test with: bash $APP_DIR/deploy/update.sh"
echo "    Then push to main on GitHub or run Actions → Deploy to droplet."
