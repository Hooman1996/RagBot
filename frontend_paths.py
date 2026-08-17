"""Filesystem paths for frontend resources, independent of process CWD."""

from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_DIR / "static"
TEMPLATE_DIR = PROJECT_DIR / "templates"
