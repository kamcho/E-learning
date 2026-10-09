#!/usr/bin/env python3
"""Run Certbot on the production server and enable HTTPS in .env."""
import os
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "185.170.196.219")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_SSH_PASSWORD", "")
EMAIL = os.environ.get("CERTBOT_EMAIL", "privacy@somasmartassesments.com")
DOMAINS = ("somasmartassesments.com", "www.somasmartassesments.com")

SCRIPT = r"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq certbot python3-certbot-nginx

echo "==> DNS check (A records should point to this server)"
getent ahosts somasmartassesments.com | head -3 || true
hostname -I | awk '{print $1}'

echo "==> Certbot"
certbot --nginx \
  -d somasmartassesments.com \
  -d www.somasmartassesments.com \
  --non-interactive \
  --agree-tos \
  -m """ + EMAIL + r""" \
  --redirect

ENV=/srv/elearning/.env
if [[ -f "$ENV" ]]; then
  sed -i 's/^SECURE_SSL_REDIRECT=.*/SECURE_SSL_REDIRECT=True/' "$ENV"
  sed -i 's/^SESSION_COOKIE_SECURE=.*/SESSION_COOKIE_SECURE=True/' "$ENV"
  sed -i 's/^CSRF_COOKIE_SECURE=.*/CSRF_COOKIE_SECURE=True/' "$ENV"
  sed -i 's/^SECURE_HSTS_SECONDS=.*/SECURE_HSTS_SECONDS=31536000/' "$ENV"
  if grep -q '^CSRF_TRUSTED_ORIGINS=' "$ENV"; then
    sed -i 's|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=https://somasmartassesments.com,https://www.somasmartassesments.com|' "$ENV"
  fi
  if grep -q '^MPESA_CALLBACK_BASE_URL=' "$ENV"; then
    sed -i 's|^MPESA_CALLBACK_BASE_URL=.*|MPESA_CALLBACK_BASE_URL=https://somasmartassesments.com|' "$ENV"
  fi
  chown elearning:www-data "$ENV"
  chmod 640 "$ENV"
fi

nginx -t
systemctl reload nginx
systemctl restart elearning
echo "==> HTTPS test"
curl -sI https://somasmartassesments.com/ | head -5
certbot certificates
"""


def main():
    if not PASSWORD:
        print("Set DEPLOY_SSH_PASSWORD", file=sys.stderr)
        sys.exit(1)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=60)
    stdin, stdout, stderr = client.exec_command(SCRIPT, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err:
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    sys.exit(code)


if __name__ == "__main__":
    main()
