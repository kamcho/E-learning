#!/usr/bin/env python3
"""Clear Postgres connection pressure and run deploy/update.sh on production."""
from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "185.170.196.219")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_SSH_PASSWORD", "")

REMOTE_SCRIPT = r"""
set -euo pipefail
export PAGER=cat
export GIT_PAGER=cat
pkill -f 'deploy/remote_fix_and_update' 2>/dev/null || true
echo "==> Postgres connections before"
sudo -u postgres psql -P pager=off -tAc "SELECT count(*) FROM pg_stat_activity;"
echo "==> Terminating idle elearning connections"
sudo -u postgres psql -P pager=off -tAc \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'elearning' AND pid <> pg_backend_pid() AND state = 'idle';" \
  || true
systemctl restart elearning
sleep 3
cd /srv/elearning
bash deploy/update.sh
"""


def main() -> None:
    if not PASSWORD:
        print("Set DEPLOY_SSH_PASSWORD", file=sys.stderr)
        sys.exit(1)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=60)
    stdin, stdout, stderr = client.exec_command(REMOTE_SCRIPT, get_pty=True)
    out_lines = []
    for line in iter(stdout.readline, ""):
        out_lines.append(line)
        sys.stdout.buffer.write(line.encode("utf-8", errors="replace"))
    out = "".join(out_lines)
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    sys.stdout.buffer.write(b"\n")
    if err:
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    if code != 0:
        sys.exit(code)


if __name__ == "__main__":
    main()
