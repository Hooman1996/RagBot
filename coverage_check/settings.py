"""Validated coverage-check settings. Errors name the variable, never its value."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = "/root/projects/faq-private/knowledge-coverage"


class SettingsError(ValueError):
    """Raised with the name of the invalid variable or field."""


def _bool(env, key, default):
    raw = env.get(key, default)
    value = raw.strip().lower() if isinstance(raw, str) else None
    if value not in {"true", "false"}:
        raise SettingsError(key)
    return value == "true"


def _int(env, key, default, low, high):
    raw = env.get(key, str(default))
    try:
        if not isinstance(raw, str):
            raise ValueError
        value = int(raw.strip())
    except ValueError:
        raise SettingsError(key) from None
    if not low <= value <= high:
        raise SettingsError(key)
    return value


def coverage_enabled(environ=None) -> bool:
    """On unless KNOWLEDGE_COVERAGE_ENABLED is false, in every environment."""
    env = os.environ if environ is None else environ
    return _bool(env, "KNOWLEDGE_COVERAGE_ENABLED", "true")


@dataclass(frozen=True)
class RunSettings:
    """The six values the page may change; each run stores the values it used."""
    depth: int = 150
    keep: int = 50
    batch_size: int = 5
    broader_enabled: bool = False
    broader_depth: int = 200
    broader_keep: int = 50

    def __post_init__(self):
        for name in ("depth", "keep", "batch_size", "broader_depth", "broader_keep"):
            if type(getattr(self, name)) is not int:
                raise SettingsError(name)
        if type(self.broader_enabled) is not bool:
            raise SettingsError("broader_enabled")
        if not 1 <= self.depth <= 1000:
            raise SettingsError("depth")
        if not 1 <= self.keep <= self.depth:
            raise SettingsError("keep")
        if not 1 <= self.batch_size <= 20:
            raise SettingsError("batch_size")
        if not self.depth < self.broader_depth <= 1000:
            raise SettingsError("broader_depth")
        if not 1 <= self.broader_keep <= 1000:
            raise SettingsError("broader_keep")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CoverageSettings:
    artifact_dir: Path
    upload_max_bytes: int
    max_rows: int
    run: RunSettings
    combine_max: int
    chunk_max_chars: int
    model_max_tokens: int
    # Suggestions only; not part of a run's stored settings.
    suggest_context: int = 5
    suggest_max_tokens: int = 700

    def run_values(self, run: RunSettings) -> dict:
        """Everything a run used, stored in its meta."""
        return {**run.as_dict(), "combine_max": self.combine_max,
                "chunk_max_chars": self.chunk_max_chars, "model_max_tokens": self.model_max_tokens}


def _artifact_dir(env) -> Path:
    key = "KNOWLEDGE_COVERAGE_ARTIFACT_DIR"
    raw = env.get(key, DEFAULT_ARTIFACT_DIR)
    if not isinstance(raw, str) or not raw.strip():
        raise SettingsError(key)
    path = Path(raw.strip())
    tmp = Path("/tmp")
    if (not path.is_absolute() or path == REPO_ROOT or REPO_ROOT in path.parents
            or path == tmp or tmp in path.parents):
        raise SettingsError(key)
    return path


def load_settings(environ=None) -> CoverageSettings:
    env = os.environ if environ is None else environ
    depth = _int(env, "KNOWLEDGE_COVERAGE_DEPTH", 150, 1, 1000)
    values = dict(
        depth=depth,
        keep=_int(env, "KNOWLEDGE_COVERAGE_KEEP", 50, 1, depth),
        batch_size=_int(env, "KNOWLEDGE_COVERAGE_BATCH_SIZE", 5, 1, 20),
        broader_enabled=_bool(env, "KNOWLEDGE_COVERAGE_BROADER_ENABLED", "false"),
        broader_depth=_int(env, "KNOWLEDGE_COVERAGE_BROADER_DEPTH", 200, depth + 1, 1000),
        broader_keep=_int(env, "KNOWLEDGE_COVERAGE_BROADER_KEEP", 50, 1, 1000),
    )
    try:
        run = RunSettings(**values)
    except SettingsError as exc:
        # Each value was range-checked above; this only maps a field to its variable.
        raise SettingsError("KNOWLEDGE_COVERAGE_" + str(exc).upper()) from None
    return CoverageSettings(
        artifact_dir=_artifact_dir(env),
        upload_max_bytes=_int(env, "KNOWLEDGE_COVERAGE_UPLOAD_MAX_BYTES", 5242880, 1024, 20971520),
        max_rows=_int(env, "KNOWLEDGE_COVERAGE_MAX_ROWS", 10000, 1, 100000),
        run=run,
        combine_max=_int(env, "KNOWLEDGE_COVERAGE_COMBINE_MAX", 10, 2, 20),
        chunk_max_chars=_int(env, "KNOWLEDGE_COVERAGE_CHUNK_MAX_CHARS", 4000, 500, 20000),
        model_max_tokens=_int(env, "KNOWLEDGE_COVERAGE_MODEL_MAX_TOKENS", 300, 64, 2048),
        suggest_context=_int(env, "KNOWLEDGE_COVERAGE_SUGGEST_CONTEXT", 5, 1, 20),
        suggest_max_tokens=_int(env, "KNOWLEDGE_COVERAGE_SUGGEST_MAX_TOKENS", 700, 128, 2048),
    )
