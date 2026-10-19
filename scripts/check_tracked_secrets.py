#!/usr/bin/env python3
"""Check tracked bytes for local credential values; emit paths and key names only."""
from pathlib import Path
import subprocess

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENV_FILES = (".env", ".env.server_git", "Production_ENV")


def secret_key(name: str) -> bool:
    return name.endswith(("_PASSWORD", "_SECRET", "_SECRET_KEY", "_API_KEY",
                          "_ACCESS_KEY", "_AUTH_TOKEN")) or "CREDENTIAL" in name


def main() -> int:
    paths = [ROOT / name for name in LOCAL_ENV_FILES if (ROOT / name).is_file()]
    if not paths:
        print("tracked secrets: NOT RUN (no local env files)")
        return 0
    placeholders = {
        value for name in ("env.example", ".env.example.generated")
        if (ROOT / name).is_file()
        for value in dotenv_values(ROOT / name, interpolate=False).values() if value
    }
    candidates = {
        (key, value.encode()) for path in paths
        for key, value in dotenv_values(path, interpolate=False).items()
        if secret_key(key) and value and len(value) >= 8 and value not in placeholders
    }
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                             check=True, capture_output=True).stdout.split(b"\0")
    matches = []
    for raw in tracked:
        if not raw:
            continue
        name = raw.decode("utf-8", errors="surrogateescape")
        path = ROOT / name
        if not path.is_file():
            continue
        body = path.read_bytes()
        matches.extend((name, key) for key, value in candidates if value in body)
    if matches:
        for name, key in sorted(set(matches)):
            print(f"{name}: {key}")
        return 1
    print("tracked secrets: 0 matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
