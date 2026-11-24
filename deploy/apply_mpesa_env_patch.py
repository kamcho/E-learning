#!/usr/bin/env python3
"""Merge MPESA_* lines from a patch file into a target .env (production)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

SYNC_KEYS = {
    "MPESA_ENVIRONMENT",
    "MPESA_CONSUMER_KEY",
    "MPESA_CONSUMER_SECRET",
    "MPESA_SHORTCODE",
    "MPESA_PASSKEY",
    "MPESA_CALLBACK_BASE_URL",
    "MPESA_PULL_NOMINATED_NUMBER",
}


def load_patch(path: Path) -> dict[str, str]:
    patch: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key in SYNC_KEYS and val:
            patch[key] = val
    return patch


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: apply_mpesa_env_patch.py <target.env> <patch.env>")
    target = Path(sys.argv[1])
    patch_path = Path(sys.argv[2])
    patch = load_patch(patch_path)
    if not patch:
        sys.exit("No MPESA keys in patch file")

    text = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    for key, val in patch.items():
        line = f"{key}={val}"
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(line, text, count=1)
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += line + "\n"
    text = re.sub(r"^MPESA_CALLBACK_URL=.*\n?", "", text, flags=re.MULTILINE)
    target.write_text(text, encoding="utf-8")
    target.chmod(0o640)
    print("Patched:", ", ".join(sorted(patch)))


if __name__ == "__main__":
    main()