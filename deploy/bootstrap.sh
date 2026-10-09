#!/usr/bin/env bash
# First-time production bootstrap on Ubuntu 24.04+ (run as root on the server).
# Usage:
#   export ELEARNING_DB_PASSWORD='your-strong-db-password'
#   export ELEARNING_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
#   bash deploy/bootstrap.sh
#
# Optional: ELEARNING_REPO_URL, ELEARNING_DOMAIN, ELEARNING_EXTRA_HOSTS (comma-separated IPs)
set -euo pipefail

APP_DIR="/srv/elearning"
APP_USER="elearning"
DOMAIN="${ELEARNING_DOMAIN:-somasmartassesments.com}"
EXTRA_HOSTS="${ELEARNING_EXTRA_HOSTS:-185.170.196.219}"
REPO_URL="${ELEARNING_REPO_URL:-}"

if [[ -z "${ELEARNING_DB_PASSWORD:-}" ]]; then
  echo "Set ELEARNING_DB_PASSWORD before running." >&2
  exit 1
fi
if [[ -z "${ELEARNING_SECRET_KEY:-}" ]]; then
  echo "Set ELEARNING_SECRET_KEY before running." >&2
  exit 1
fi

echo "==> System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
  python3 python3-venv python3-dev python3-pip build-essential \
  libpq-dev postgresql postgresql-contrib nginx git curl ufw rsync

echo "==> Firewall"
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable || true

echo "==> App user"
if ! id "$APP_USER" &>/dev/null; then
  adduser --system --group --home "$APP_DIR" "$APP_USER"
fi
usermod -aG www-data "$APP_USER"
mkdir -p "$APP_DIR"
chown -R "$APP_USER:www-data" "$APP_DIR"

echo "==> PostgreSQL"
DB_PASS_ESC="${ELEARNING_DB_PASSWORD//\'/\'\'}"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='elearning'" | grep -q 1; then
  sudo -u postgres psql -c "CREATE USER elearning WITH PASSWORD '${DB_PASS_ESC}';"
else
  sudo -u postgres psql -c "ALTER USER elearning WITH PASSWORD '${DB_PASS_ESC}';"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='elearning'" | grep -q 1; then
  sudo -u postgres psql -c "CREATE DATABASE elearning OWNER elearning;"
fi
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
ALTER ROLE elearning SET client_encoding TO 'utf8';
ALTER ROLE elearning SET default_transaction_isolation TO 'read committed';
ALTER ROLE elearning SET timezone TO 'Africa/Nairobi';
GRANT ALL PRIVILEGES ON DATABASE elearning TO elearning;
SQL
sudo -u postgres psql -v ON_ERROR_STOP=1 -d elearning -c "GRANT ALL ON SCHEMA public TO elearning;"

echo "==> Application code"
if [[ -n "$REPO_URL" ]] && [[ ! -d "$APP_DIR/.git" ]]; then
  git clone "$REPO_URL" "$APP_DIR"
  chown -R "$APP_USER:www-data" "$APP_DIR"
elif [[ ! -f "$APP_DIR/manage.py" ]]; then
  echo "No manage.py in $APP_DIR — rsync or git clone the project first, then re-run." >&2
  exit 1
fi

echo "==> Python venv"
cd "$APP_DIR"
if [[ ! -d .venv ]]; then
  sudo -u "$APP_USER" python3 -m venv .venv
fi
sudo -u "$APP_USER" .venv/bin/pip install --upgrade pip -q
sudo -u "$APP_USER" .venv/bin/pip install -r requirements.txt -q

ALLOWED="${DOMAIN},www.${DOMAIN},${EXTRA_HOSTS}"
CSRF="http://${DOMAIN},http://www.${DOMAIN},https://${DOMAIN},https://www.${DOMAIN}"
for h in ${EXTRA_HOSTS//,/ }; do
  CSRF="${CSRF},http://${h},https://${h}"
done

if [[ ! -f .env ]]; then
  echo "==> Creating .env from template"
  if [[ -f .env.production.example ]]; then
    cp .env.production.example .env
  else
    touch .env
  fi
  sed -i "s/^SECRET_KEY=.*/SECRET_KEY=${ELEARNING_SECRET_KEY}/" .env
  sed -i "s/^DEBUG=.*/DEBUG=False/" .env
  sed -i "s/^ALLOWED_HOSTS=.*/ALLOWED_HOSTS=${ALLOWED}/" .env
  sed -i "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=${CSRF}|" .env
  sed -i "s/^DB_ENGINE=.*/DB_ENGINE=postgres/" .env
  sed -i "s/^DB_NAME=.*/DB_NAME=elearning/" .env
  sed -i "s/^DB_USER=.*/DB_USER=elearning/" .env
  sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=${ELEARNING_DB_PASSWORD}/" .env
  sed -i "s/^DB_HOST=.*/DB_HOST=127.0.0.1/" .env
  sed -i "s/^DB_PORT=.*/DB_PORT=5432/" .env
  chown "$APP_USER:www-data" .env
  chmod 640 .env
  echo "    Edit /srv/elearning/.env for Google, M-Pesa, email, etc."
fi

echo "==> Django migrate + static"
sudo -u "$APP_USER" .venv/bin/python manage.py migrate --noinput
sudo -u "$APP_USER" .venv/bin/python manage.py collectstatic --noinput

echo "==> systemd"
cp "$APP_DIR/deploy/elearning.service" /etc/systemd/system/elearning.service
systemctl daemon-reload
systemctl enable elearning
systemctl restart elearning

echo "==> nginx"
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/elearning
ln -sf /etc/nginx/sites-available/elearning /etc/nginx/sites-enabled/elearning
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

chmod +x "$APP_DIR/deploy/update.sh" 2>/dev/null || true

echo "==> Bootstrap complete"
systemctl is-active elearning nginx postgresql
echo "Visit http://${EXTRA_HOSTS%%*,*} or http://${DOMAIN}"
