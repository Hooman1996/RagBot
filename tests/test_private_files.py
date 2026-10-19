from __future__ import annotations

from pathlib import Path
import stat
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.private_files import PrivateFileError, formula_safe, private_directory, private_write  # noqa: E402


@pytest.mark.parametrize("value", ["=1+1", "+1", "-1", "@SUM(A1)", "\t=1", "\r=1", "\tplain", "\rplain"])
def test_formula_safe_quotes_formula_and_control_prefixes(value):
    assert formula_safe(value) == "'" + value


@pytest.mark.parametrize("value", ["  +1", "‮@command", "\r\ntext", "\x00 -12", "‏‎=1"])
def test_formula_safe_sees_through_spaces_and_invisible_controls(value):
    assert formula_safe(value) == "'" + value


@pytest.mark.parametrize("value", ["plain", "", "a=b", "1-2", " text", "پرسش،\nنیم‌فاصله"])
def test_formula_safe_leaves_ordinary_text(value):
    assert formula_safe(value) == value


def test_private_directory_is_owner_only(tmp_path):
    created = private_directory(tmp_path / "out")
    assert created.is_dir()
    assert stat.S_IMODE(created.stat().st_mode) == 0o700


def test_private_write_is_owner_only_and_never_overwrites(tmp_path):
    target = tmp_path / "out" / "file.json"
    private_write(target, b"{}\n")
    assert target.read_bytes() == b"{}\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    with pytest.raises(FileExistsError):
        private_write(target, b"other")


@pytest.mark.parametrize("relative", ["never-created-private-output", "static/never-created-private-output"])
def test_private_directory_refuses_repository_path(relative):
    with pytest.raises(PrivateFileError) as caught:
        private_directory(ROOT / relative)
    assert str(caught.value) == "artifact_repository_forbidden"
    assert not (ROOT / relative).exists()


def test_private_directory_refuses_missing_parent_and_open_permissions(tmp_path):
    with pytest.raises(PrivateFileError) as caught:
        private_directory(tmp_path / "missing" / "out")
    assert str(caught.value) == "artifact_parent_missing"
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o755)
    with pytest.raises(PrivateFileError) as caught:
        private_directory(shared)
    assert str(caught.value) == "artifact_directory_permissions"


def test_private_directory_refuses_symlink(tmp_path):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(real)
    for target in (link, link / "child"):
        with pytest.raises(PrivateFileError) as caught:
            private_directory(target)
        assert str(caught.value) == "artifact_symlink_forbidden"
    assert not (real / "child").exists()
