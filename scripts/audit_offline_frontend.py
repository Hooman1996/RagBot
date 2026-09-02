#!/usr/bin/env python3
"""Fail when the RagBot browser frontend depends on a public runtime URL."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (PROJECT_DIR / "templates", PROJECT_DIR / "static")
PYTHON_FRONTEND_FILES = (
    PROJECT_DIR / "main.py",
    PROJECT_DIR / "kb_manager.py",
    PROJECT_DIR / "frontend_paths.py",
)
PUBLIC_SCHEMES = ("http://", "https://", "//")
TEXT_SUFFIXES = {".css", ".html", ".htm", ".jinja", ".jinja2", ".js", ".mjs"}


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    kind: str
    target: str

    def display(self) -> str:
        relative = self.path.relative_to(PROJECT_DIR)
        return f"{relative}:{self.line}: {self.kind}: {self.target}"


def _is_public(target: str) -> bool:
    value = target.strip().strip("'\"")
    return value.lower().startswith(PUBLIC_SCHEMES)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _without_css_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group(0).count("\n"), text, flags=re.S)


def _without_js_comments(text: str) -> str:
    # Runtime URL checks are anchored to calls/imports, so a conservative comment
    # remover is enough and deliberately leaves quoted strings intact.
    text = re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text)


def scan_css(path: Path, text: str) -> list[Finding]:
    clean = _without_css_comments(text)
    findings: list[Finding] = []
    patterns = (
        ("CSS import", re.compile(r"@import\s+(?:url\(\s*)?(['\"]?)([^'\"\s;)]+)\1", re.I)),
        ("CSS asset", re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", re.I)),
    )
    seen: set[tuple[int, str, str]] = set()
    for kind, pattern in patterns:
        for match in pattern.finditer(clean):
            target = match.group(2).strip()
            if not _is_public(target):
                continue
            key = (match.start(), kind, target)
            if key not in seen:
                seen.add(key)
                findings.append(Finding(path, _line_number(clean, match.start()), kind, target))
    return findings


SCRIPT_CALL = re.compile(
    r"(?:fetch|import|importScripts|axios(?:\.[A-Za-z]+)?|"
    r"new\s+(?:Worker|SharedWorker|WebSocket|EventSource))\s*\(\s*(['\"])(.*?)\1",
    re.I | re.S,
)
STATIC_IMPORT = re.compile(r"(?:import|export)\s+(?:[^;]*?\s+from\s+)?(['\"])(.*?)\1", re.I)
XHR_OPEN = re.compile(r"\.open\s*\(\s*(['\"])[A-Z]+\1\s*,\s*(['\"])(.*?)\2", re.I)


def scan_javascript(path: Path, text: str, line_offset: int = 0) -> list[Finding]:
    clean = _without_js_comments(text)
    findings: list[Finding] = []
    for kind, pattern, target_group in (
        ("JavaScript network/module target", SCRIPT_CALL, 2),
        ("JavaScript module target", STATIC_IMPORT, 2),
        ("XMLHttpRequest target", XHR_OPEN, 3),
    ):
        for match in pattern.finditer(clean):
            target = match.group(target_group).strip()
            if _is_public(target):
                findings.append(
                    Finding(path, line_offset + _line_number(clean, match.start()), kind, target)
                )
    return findings


class RuntimeHTMLParser(HTMLParser):
    RUNTIME_ATTRIBUTES = {
        "script": {"src"},
        "link": {"href"},
        "img": {"src", "srcset"},
        "source": {"src", "srcset"},
        "audio": {"src"},
        "video": {"src", "poster"},
        "iframe": {"src"},
        "embed": {"src"},
        "object": {"data"},
    }

    def __init__(self, path: Path) -> None:
        super().__init__(convert_charrefs=False)
        self.path = path
        self.findings: list[Finding] = []
        self.in_script = False
        self.script_line = 0
        self.script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        if tag == "script":
            self.in_script = True
            self.script_line = self.getpos()[0]
            self.script_parts = []
        allowed = self.RUNTIME_ATTRIBUTES.get(tag, set())
        if tag == "link":
            rel = set(values.get("rel", "").lower().split())
            if rel and not rel.intersection({"stylesheet", "preload", "modulepreload", "icon", "manifest"}):
                allowed = set()
        for name in allowed:
            raw_target = values.get(name, "")
            targets = [part.strip().split()[0] for part in raw_target.split(",") if part.strip()]
            for target in targets:
                if _is_public(target):
                    self.findings.append(
                        Finding(self.path, self.getpos()[0], f"HTML {tag}[{name}]", target)
                    )
        style = values.get("style")
        if style:
            self.findings.extend(scan_css(self.path, style))

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self.script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_script:
            script = "".join(self.script_parts)
            self.findings.extend(scan_javascript(self.path, script, self.script_line - 1))
            self.in_script = False
            self.script_parts = []


def scan_html(path: Path, text: str) -> list[Finding]:
    parser = RuntimeHTMLParser(path)
    parser.feed(text)
    clean = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    style_blocks = re.finditer(r"<style\b[^>]*>(.*?)</style>", clean, re.I | re.S)
    for block in style_blocks:
        for finding in scan_css(path, block.group(1)):
            parser.findings.append(
                Finding(path, _line_number(clean, block.start()) + finding.line, finding.kind, finding.target)
            )
    return parser.findings


def scan_file(path: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    suffix = path.suffix.lower()
    if suffix == ".css":
        return scan_css(path, text)
    if suffix in {".js", ".mjs"}:
        return scan_javascript(path, text)
    if suffix in {".html", ".htm", ".jinja", ".jinja2"}:
        return scan_html(path, text)
    if suffix == ".py":
        # This catches resource tags in Python-generated HTML while avoiding
        # backend-only service URLs such as vLLM, PostgreSQL, or Qdrant.
        return scan_html(path, text)
    return []


def iter_frontend_files() -> list[Path]:
    files = [
        path
        for root in SCAN_ROOTS
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES
    ]
    files.extend(path for path in PYTHON_FRONTEND_FILES if path.exists())
    return sorted(set(files))


def audit() -> list[Finding]:
    return [finding for path in iter_frontend_files() for finding in scan_file(path)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="list scanned files")
    args = parser.parse_args()
    if args.verbose:
        for path in iter_frontend_files():
            print(path.relative_to(PROJECT_DIR))
    findings = audit()
    if findings:
        print("Offline frontend audit: FAIL")
        print(f"External runtime dependencies: {len(findings)}")
        for finding in findings:
            print(f"- {finding.display()}")
        return 1
    print("Offline frontend audit: PASS")
    print("External runtime dependencies: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
