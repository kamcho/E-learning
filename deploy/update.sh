#!/usr/bin/env bash
# Production update script — run on the droplet as root.
# Called by GitHub Actions on push to main (and safe to run manually).
set -euo pipefail

APP_DIR="/srv/elearning"
APP_USER="elearning"
VENV="$APP_DIR/.venv/bin"

cd "$APP_DIR"

echo "==> Pulling latest code"
# Preserve local .env; never overwrite production secrets
git fetch origin
git reset --hard origin/main

echo "==> Ensuring ownership"
chown -R "$APP_USER":www-data "$APP_DIR"
# Keep .env readable only by app + group
if [[ -f "$APP_DIR/.env" ]]; then
  chown "$APP_USER":www-data "$APP_DIR/.env"
  chmod 640 "$APP_DIR/.env"
fi

echo "==> Installing Python dependencies"
sudo -u "$APP_USER" "$VENV/pip" install --upgrade pip
sudo -u "$APP_USER" "$VENV/pip" install -r requirements.txt

echo "==> Running migrations"
sudo -u "$APP_USER" "$VENV/python" manage.py migrate --noinput

echo "==> Collecting static files"
sudo -u "$APP_USER" "$VENV/python" manage.py collectstatic --noinput

echo "==> Restarting app (gunicorn + uvicorn workers)"
systemctl restart elearning
systemctl is-active --quiet elearning

# Reload nginx config if it changed (no downtime if config is unchanged)
if nginx -t 2>/dev/null; then
  systemctl reload nginx
fi

echo "==> Deploy complete"
systemctl status elearning --no-pager -l | head -n 20
