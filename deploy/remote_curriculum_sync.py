#!/usr/bin/env python3
"""Upload curriculum seed files and run seed_kicd_curriculum on production."""
import os
import sys
from pathlib import Path

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "185.170.196.219")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_SSH_PASSWORD", "")
REPO = Path(__file__).resolve().parent.parent

FILES = [
    REPO / "subjects/management/commands/seed_kicd_curriculum.py",
    REPO / "subjects/grade_utils.py",
    REPO / "accounts/views.py",
]


def main():
    if not PASSWORD:
        print("Set DEPLOY_SSH_PASSWORD", file=sys.stderr)
        sys.exit(1)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=60)
    sftp = client.open_sftp()
    for local in FILES:
        remote = f"/srv/elearning/{local.relative_to(REPO).as_posix()}"
        sftp.put(str(local), remote)
        print("uploaded", remote)
    sftp.close()
    cmd = (
        "chown elearning:www-data /srv/elearning/subjects/management/commands/seed_kicd_curriculum.py "
        "/srv/elearning/subjects/grade_utils.py /srv/elearning/accounts/views.py && "
        "cd /srv/elearning && sudo -u elearning .venv/bin/python manage.py seed_kicd_curriculum"
    )
    _, stdout, stderr = client.exec_command(cmd, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    sys.exit(code)


if __name__ == "__main__":
    main()
