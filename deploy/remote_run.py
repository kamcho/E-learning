#!/usr/bin/env python3
"""Run a remote shell command (stdout streamed). Usage: python deploy/remote_run.py 'command'"""
import os
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "185.170.196.219")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_SSH_PASSWORD", "")


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: remote_run.py <command>", file=sys.stderr)
        sys.exit(2)
    if not PASSWORD:
        sys.exit("Set DEPLOY_SSH_PASSWORD")
    cmd = sys.argv[1]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=60)
    stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
    for line in iter(stdout.readline, ""):
        sys.stdout.buffer.write(line.encode("utf-8", errors="replace"))
    code = stdout.channel.recv_exit_status()
    client.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
