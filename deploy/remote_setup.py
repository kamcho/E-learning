#!/usr/bin/env python3
"""One-shot: upload repo to server and run deploy/bootstrap.sh (reads SSH password from env)."""
from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from pathlib import Path

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "185.170.196.219")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_SSH_PASSWORD", "")
REMOTE_DIR = "/srv/elearning"
REPO_ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "staticfiles", "media", ".cursor"}
SKIP_FILES = {".env"}
SKIP_PREFIXES = ("_tmp_",)


def should_skip(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & SKIP_DIRS:
        return True
    if rel.name in SKIP_FILES:
        return True
    if any(rel.name.startswith(p) for p in SKIP_PREFIXES):
        return True
    if rel.suffix == ".pyc":
        return True
    return False


def make_zip() -> Path:
    fd, path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    zpath = Path(path)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in REPO_ROOT.rglob("*"):
            if item.is_dir():
                continue
            rel = item.relative_to(REPO_ROOT)
            if should_skip(rel):
                continue
            zf.write(item, rel.as_posix())
    return zpath


def run():
    if not PASSWORD:
        print("Set DEPLOY_SSH_PASSWORD in the environment.", file=sys.stderr)
        sys.exit(1)

    print(f"Packaging {REPO_ROOT} ...")
    archive = make_zip()
    print(f"Archive size: {archive.stat().st_size / 1024 / 1024:.1f} MB")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {USER}@{HOST} ...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=60)

    remote_zip = "/tmp/elearning-deploy.zip"
    print("Uploading ...")
    sftp = client.open_sftp()
    sftp.put(str(archive), remote_zip)
    sftp.close()
    archive.unlink(missing_ok=True)

    bootstrap = f"""
set -euo pipefail
apt-get update -qq
apt-get install -y -qq unzip
mkdir -p {REMOTE_DIR}
rm -rf {REMOTE_DIR}/*
unzip -o -q {remote_zip} -d {REMOTE_DIR}
rm -f {remote_zip}
sed -i 's/\\r$//' {REMOTE_DIR}/deploy/*.sh 2>/dev/null || true
chmod +x {REMOTE_DIR}/deploy/bootstrap.sh {REMOTE_DIR}/deploy/update.sh 2>/dev/null || true
export ELEARNING_DB_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"
export ELEARNING_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
export ELEARNING_EXTRA_HOSTS="{HOST}"
bash {REMOTE_DIR}/deploy/bootstrap.sh
echo "=== DB password (save this) ==="
grep '^DB_PASSWORD=' {REMOTE_DIR}/.env | cut -d= -f2-
"""
    print("Running bootstrap on server ...")
    stdin, stdout, stderr = client.exec_command(bootstrap, get_pty=True)
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
    print("Deploy finished. Try http://{HOST}/")


if __name__ == "__main__":
    run()
