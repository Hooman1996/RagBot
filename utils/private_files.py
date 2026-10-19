"""Owner-only output files and spreadsheet-formula-safe cells for offline tools."""
from __future__ import annotations

import os
from pathlib import Path
import unicodedata


class PrivateFileError(ValueError):
    """Only fixed machine codes may cross the diagnostic boundary."""


def private_directory(path: Path) -> Path:
    """Require a dedicated owner-only directory outside the repository.

    No symlink traversal, Git/static artifacts, overwrites or permissive parents
    supplied as the output directory. /tmp's sticky parent is acceptable.
    """
    path = path.absolute()
    root = Path(__file__).resolve().parents[1]
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise PrivateFileError("artifact_symlink_forbidden")
    if path == root or root in path.parents:
        raise PrivateFileError("artifact_repository_forbidden")
    if not path.parent.is_dir():
        raise PrivateFileError("artifact_parent_missing")
    if not path.exists():
        path.mkdir(mode=0o700)
    stat = path.stat()
    if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        raise PrivateFileError("artifact_directory_permissions")
    return path


def private_write(path: Path, data: bytes) -> None:
    private_directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def formula_safe(value: str) -> str:
    effective = value.lstrip()
    while effective and (effective[0].isspace() or unicodedata.category(effective[0]) in {"Cc", "Cf"}):
        effective = effective[1:]
    if any(c in value[:len(value) - len(effective)] for c in "\t\r\n") or effective[:1] in {"=", "+", "-", "@"}:
        return "'" + value
    return value
