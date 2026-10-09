#!/usr/bin/env python3
"""SSH to production and run deploy/init-for-github-actions.sh (one-time)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "185.170.196.219")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_SSH_PASSWORD", "")
REMOTE_DIR = "/srv/elearning"
REPO_ROOT = Path(__file__).resolve().parent.parent
INIT_SCRIPT = REPO_ROOT / "deploy" / "init-for-github-actions.sh"


def main() -> None:
    if not PASSWORD:
        print("Set DEPLOY_SSH_PASSWORD in the environment.", file=sys.stderr)
        sys.exit(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {USER}@{HOST} ...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=60)

    remote_init = f"{REMOTE_DIR}/deploy/init-for-github-actions.sh"
    sftp = client.open_sftp()
    try:
        sftp.stat(f"{REMOTE_DIR}/deploy")
    except FileNotFoundError:
        client.exec_command(f"mkdir -p {REMOTE_DIR}/deploy")[1].read()
    sftp.put(str(INIT_SCRIPT), remote_init)
    sftp.close()

    cmd = f"""
set -euo pipefail
cd {REMOTE_DIR}
sed -i 's/\\r$//' deploy/init-for-github-actions.sh
chmod +x deploy/init-for-github-actions.sh
bash deploy/init-for-github-actions.sh
"""
    stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")
    if err:
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
        sys.stderr.buffer.write(b"\n")
    if code != 0:
        sys.exit(code)
    print("Server is ready for push-to-deploy. Update DROPLET_SSH_PASSWORD on GitHub if this host is new.")


if __name__ == "__main__":
    main()
