"""Staging-only guard shared by the release evaluation tools.

A refusal names the failed key on one fixed line, never its value, and exits 3.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
RETRIEVAL_KEYS = ("QDRANT_HOST", "POSTGRES_HOST", "TEI_EMBED_URL", "TEI_RERANK_URL", "VLLM_URL")


def load_env() -> None:
    """Fill unset variables from this checkout's .env, as the application does."""
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=False)


def _refuse(key: str) -> None:
    print(f"staging guard: refused ({key})", file=sys.stderr)
    raise SystemExit(3)


def _host(key: str, value: str) -> str | None:
    return urlsplit(value).hostname if key.endswith("URL") else value


def require_staging(keys) -> None:
    """Each key must equal this checkout's .env value and point at loopback; ENVIRONMENT must be staging."""
    from dotenv import dotenv_values
    if os.environ.get("ENVIRONMENT") != "staging":
        _refuse("ENVIRONMENT")
    file_values = dotenv_values(ENV_FILE)
    for key in keys:
        value = os.environ.get(key, "")
        if value != file_values.get(key) or _host(key, value) not in LOOPBACK:
            _refuse(key)


def require_loopback_url(name: str, url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or parts.hostname not in LOOPBACK:
        _refuse(name)
