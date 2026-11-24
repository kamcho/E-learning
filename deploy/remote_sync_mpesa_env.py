#!/usr/bin/env python3
"""Sync MPESA_* keys from local .env to /srv/elearning/.env on production."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "185.170.196.219")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_SSH_PASSWORD", "")
REPO = Path(__file__).resolve().parent.parent
LOCAL_ENV = REPO / ".env"

SYNC_KEYS = (
    "MPESA_ENVIRONMENT",
    "MPESA_CONSUMER_KEY",
    "MPESA_CONSUMER_SECRET",
    "MPESA_SHORTCODE",
    "MPESA_PASSKEY",
    "MPESA_CALLBACK_BASE_URL",
    "MPESA_PULL_NOMINATED_NUMBER",
)


def load_mpesa_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key in SYNC_KEYS and val:
            out[key] = val
    return out


def main() -> None:
    if not PASSWORD:
        sys.exit("Set DEPLOY_SSH_PASSWORD")
    if not LOCAL_ENV.is_file():
        sys.exit(f"Missing {LOCAL_ENV}")
    values = load_mpesa_env(LOCAL_ENV)
    missing = [k for k in SYNC_KEYS if k not in values and k != "MPESA_PULL_NOMINATED_NUMBER"]
    if missing:
        sys.exit(f"Local .env missing: {', '.join(missing)}")

    remote_py = r"""
import re
from pathlib import Path

values = """ + repr(values) + r"""

path = Path("/srv/elearning/.env")
text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
for key, val in values.items():
    safe = val.replace("\\", "\\\\").replace('"', '\\"')
    line = f'{key}="{safe}"' if " " in val or "#" in val else f"{key}={val}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
# Drop legacy callback that breaks Pull URL construction
text = re.sub(r"^MPESA_CALLBACK_URL=.*\n?", "", text, flags=re.MULTILINE)
path.write_text(text, encoding="utf-8")
path.chmod(0o640)
print("Synced keys:", ", ".join(sorted(values)))
"""

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=60)
    _stdin, stdout, stderr = client.exec_command(
        f"python3 -c {repr(remote_py)}", get_pty=True,
    )
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    if code:
        sys.exit(code)
    restart = (
        "chown elearning:www-data /srv/elearning/.env && systemctl restart elearning"
    )
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=60)
    _stdin, stdout, _stderr = client.exec_command(restart, get_pty=True)
    sys.stdout.write(stdout.read().decode("utf-8", errors="replace"))
    client.close()


if __name__ == "__main__":
    main()