#!/usr/bin/env python3
"""Print non-secret MPESA_* fingerprints (local or given env file)."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key.startswith("MPESA_"):
            out[key] = val
    return out


def fp(value: str) -> str:
    if not value:
        return "(empty)"
    digest = hashlib.sha256(value.encode()).hexdigest()[:12]
    return f"sha256:{digest} len={len(value)}"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / ".env"
    env = load_env(path)
    keys = sorted(env.keys())
    print(f"# {path}")
    for key in keys:
        if "SECRET" in key or "PASSKEY" in key:
            print(f"{key}={fp(env[key])}")
        else:
            print(f"{key}={env.get(key, '')}")


if __name__ == "__main__":
    main()