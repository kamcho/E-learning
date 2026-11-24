#!/usr/bin/env python3
"""Set MPESA_PULL_NOMINATED_NUMBER on production and run register_mpesa_pull."""
import os
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "185.170.196.219")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_SSH_PASSWORD", "")
NOMINATED = os.environ.get("MPESA_PULL_NOMINATED_NUMBER", "254726550916")
APP_DIR = "/srv/elearning"
ENV_FILE = f"{APP_DIR}/.env"


def main() -> None:
    if not PASSWORD:
        sys.exit("Set DEPLOY_SSH_PASSWORD (same secret as GitHub Actions deploy).")
    shell = f"""
set -euo pipefail
if [[ ! -f {ENV_FILE} ]]; then
  echo "Missing {ENV_FILE}"
  exit 1
fi
if grep -q '^MPESA_PULL_NOMINATED_NUMBER=' {ENV_FILE}; then
  sed -i 's|^MPESA_PULL_NOMINATED_NUMBER=.*|MPESA_PULL_NOMINATED_NUMBER={NOMINATED}|' {ENV_FILE}
else
  printf '\\n# Daraja Pull Transactions\\nMPESA_PULL_NOMINATED_NUMBER={NOMINATED}\\n' >> {ENV_FILE}
fi
chown elearning:www-data {ENV_FILE}
chmod 640 {ENV_FILE}
grep '^MPESA_PULL_NOMINATED_NUMBER=' {ENV_FILE}
cd {APP_DIR}
sudo -u elearning {APP_DIR}/.venv/bin/python manage.py register_mpesa_pull
"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=60)
    stdin, stdout, stderr = client.exec_command(shell, get_pty=True)
    for line in iter(stdout.readline, ""):
        sys.stdout.buffer.write(line.encode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        sys.stderr.write(err)
    code = stdout.channel.recv_exit_status()
    client.close()
    sys.exit(code)


if __name__ == "__main__":
    main()