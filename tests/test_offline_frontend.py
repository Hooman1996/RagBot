from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from frontend_paths import PROJECT_DIR, STATIC_DIR, TEMPLATE_DIR


AUDIT_SCRIPT = PROJECT_DIR / "scripts" / "audit_offline_frontend.py"
TEMPLATE_PATHS = {
    "login.html": "/",
    "index.html": "/app",
    "analytics.html": "/analytics",
    "kb_manager.html": "/knowledge-base/",
}
CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
CSS_IMPORT = re.compile(r"@import\s+(?:url\(\s*)?(['\"]?)([^'\"\s;)]+)\1", re.I)


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("offline_frontend_audit", AUDIT_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "script" and values.get("src"):
            self.assets.add(values["src"])
        elif tag == "link" and values.get("href"):
            rel = set(values.get("rel", "").split())
            if rel.intersection({"stylesheet", "preload", "modulepreload", "icon", "manifest"}):
                self.assets.add(values["href"])
        elif tag in {"img", "source"} and values.get("src"):
            self.assets.add(values["src"])


def _test_app() -> Starlette:
    return Starlette(routes=[Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static")])


def _render_templates() -> dict[str, str]:
    app = _test_app()
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    rendered: dict[str, str] = {}
    for name, path in TEMPLATE_PATHS.items():
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "app": app,
        }
        request = Request(scope)
        rendered[name] = templates.get_template(name).render(request=request)
    return rendered


def _static_path(target: str) -> Path | None:
    parsed = urlsplit(target)
    if parsed.scheme in {"data", "blob"} or target.startswith("#"):
        return None
    if parsed.scheme and (parsed.scheme, parsed.netloc) != ("http", "testserver"):
        raise AssertionError(f"external asset URL in rendered frontend: {target}")
    path = unquote(parsed.path)
    if not path.startswith("/static/"):
        return None
    candidate = (STATIC_DIR / path.removeprefix("/static/")).resolve()
    assert candidate.is_relative_to(STATIC_DIR.resolve()), f"static path traversal: {target}"
    return candidate


def _css_dependencies(css_path: Path) -> set[Path]:
    text = re.sub(r"/\*.*?\*/", "", css_path.read_text(encoding="utf-8"), flags=re.S)
    targets = [match.group(2) for match in CSS_URL.finditer(text)]
    targets.extend(match.group(2) for match in CSS_IMPORT.finditer(text))
    dependencies: set[Path] = set()
    for target in targets:
        parsed = urlsplit(target.strip())
        if parsed.scheme in {"data", "blob"} or target.startswith("#"):
            continue
        assert not parsed.scheme and not parsed.netloc, f"external CSS dependency: {target}"
        if parsed.path.startswith("/static/"):
            candidate = STATIC_DIR / parsed.path.removeprefix("/static/")
        else:
            candidate = css_path.parent / unquote(parsed.path)
        candidate = candidate.resolve()
        assert candidate.is_relative_to(STATIC_DIR.resolve()), f"CSS path traversal: {target}"
        dependencies.add(candidate)
    return dependencies


def test_source_audit_has_no_external_runtime_dependencies() -> None:
    audit = _load_audit_module()
    assert audit.audit() == []


def test_audit_distinguishes_runtime_resources_from_links_and_comments(tmp_path: Path) -> None:
    audit = _load_audit_module()
    harmless = tmp_path / "harmless.html"
    harmless.write_text(
        '<!-- <script src="https://cdn.example.invalid/a.js"></script> -->\n'
        '<a href="https://docs.example.invalid/guide">Guide</a>',
        encoding="utf-8",
    )
    assert audit.scan_file(harmless) == []

    runtime = tmp_path / "runtime.html"
    runtime.write_text(
        '<link rel="stylesheet" href="https://cdn.example.invalid/a.css">\n'
        '<script>fetch("https://api.example.invalid/data")</script>',
        encoding="utf-8",
    )
    findings = audit.scan_file(runtime)
    assert {finding.kind for finding in findings} == {
        "HTML link[href]",
        "JavaScript network/module target",
    }


def test_rendered_templates_reference_only_existing_local_assets() -> None:
    for template_name, html in _render_templates().items():
        parser = AssetParser()
        parser.feed(html)
        assert parser.assets, f"no assets extracted from {template_name}"
        for target in parser.assets:
            asset = _static_path(target)
            assert asset is not None, f"non-static runtime asset in {template_name}: {target}"
            assert asset.is_file(), f"missing asset in {template_name}: {target}"


def test_all_css_dependencies_exist_and_stay_inside_static_tree() -> None:
    checked: set[Path] = set()
    pending = list(STATIC_DIR.rglob("*.css"))
    while pending:
        css_path = pending.pop()
        if css_path in checked:
            continue
        checked.add(css_path)
        for dependency in _css_dependencies(css_path):
            assert dependency.is_file(), f"missing CSS dependency from {css_path}: {dependency}"
            if dependency.suffix.lower() == ".css":
                pending.append(dependency)


def test_rendered_static_assets_return_200_with_expected_mime_types() -> None:
    rendered = _render_templates()
    asset_urls: set[str] = set()
    for html in rendered.values():
        parser = AssetParser()
        parser.feed(html)
        asset_urls.update(parser.assets)

    async def request_assets() -> None:
        transport = httpx.ASGITransport(app=_test_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for target in sorted(asset_urls):
                path = urlsplit(target).path
                response = await client.get(path)
                assert response.status_code == 200, f"{path}: {response.status_code}"
                if path.endswith(".css"):
                    assert response.headers["content-type"].startswith("text/css")
                elif path.endswith(".js"):
                    assert "javascript" in response.headers["content-type"]

            for font in sorted(STATIC_DIR.rglob("*.woff2")):
                path = "/static/" + font.relative_to(STATIC_DIR).as_posix()
                response = await client.get(path)
                assert response.status_code == 200, f"{path}: {response.status_code}"
                assert response.headers["content-type"].startswith("font/woff2")

    async def direct_run_sync(function, *args, **_kwargs):
        # The repository's packaged anyio worker pool is not operational in the
        # audit shell. StaticFiles normally delegates stat/read calls to it; run
        # those same calls directly so the ASGI response itself remains covered.
        return function(*args)

    with patch("anyio.to_thread.run_sync", new=direct_run_sync):
        asyncio.run(request_assets())


def test_frontend_paths_and_mount_are_cwd_independent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert STATIC_DIR == PROJECT_DIR / "static"
    assert TEMPLATE_DIR == PROJECT_DIR / "templates"
    assert STATIC_DIR.is_dir()
    assert TEMPLATE_DIR.is_dir()
    main_source = (PROJECT_DIR / "main.py").read_text(encoding="utf-8")
    kb_source = (PROJECT_DIR / "kb_manager.py").read_text(encoding="utf-8")
    assert 'StaticFiles(directory=str(STATIC_DIR))' in main_source
    assert 'Jinja2Templates(directory=str(TEMPLATE_DIR))' in main_source
    assert 'Jinja2Templates(directory=str(TEMPLATE_DIR))' in kb_source


def test_frontend_files_are_readable_and_not_world_writable() -> None:
    for root in (TEMPLATE_DIR, STATIC_DIR):
        for path in root.rglob("*"):
            mode = path.stat().st_mode
            assert mode & 0o444, f"not readable: {path}"
            assert not mode & 0o002, f"world-writable frontend path: {path}"


def test_vendor_manifest_covers_assets_and_hashes_match() -> None:
    manifest_path = STATIC_DIR / "vendor" / "VENDOR_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    covered: set[Path] = set()
    for dependency in manifest["dependencies"]:
        dependency_root = PROJECT_DIR / dependency["local_path"]
        principal_hashes = {item["sha256"] for item in dependency["files_required"]}
        assert dependency["sha256"] in principal_hashes
        for item in dependency["files_required"]:
            path = dependency_root / item["path"]
            assert path.is_file(), f"manifest file missing: {path}"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == item["sha256"], f"vendor hash mismatch: {path}"
            covered.add(path.resolve())
    actual = {
        path.resolve()
        for path in (STATIC_DIR / "vendor").rglob("*")
        if path.is_file() and path != manifest_path
    }
    assert actual == covered, f"unmanifested vendor files: {sorted(actual - covered)}"


class OfflineFrontendTests(unittest.TestCase):
    """unittest wrappers keep validation runnable when pytest is unavailable."""

    def test_source_audit(self) -> None:
        test_source_audit_has_no_external_runtime_dependencies()

    def test_audit_classification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            test_audit_distinguishes_runtime_resources_from_links_and_comments(Path(directory))

    def test_rendered_assets_exist(self) -> None:
        test_rendered_templates_reference_only_existing_local_assets()

    def test_css_dependency_tree(self) -> None:
        test_all_css_dependencies_exist_and_stay_inside_static_tree()

    def test_static_http_responses(self) -> None:
        test_rendered_static_assets_return_200_with_expected_mime_types()

    def test_cwd_independent_paths(self) -> None:
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                assert STATIC_DIR == PROJECT_DIR / "static"
                assert TEMPLATE_DIR == PROJECT_DIR / "templates"
                assert STATIC_DIR.is_dir() and TEMPLATE_DIR.is_dir()
            finally:
                os.chdir(previous)

    def test_safe_file_permissions(self) -> None:
        test_frontend_files_are_readable_and_not_world_writable()

    def test_vendor_manifest(self) -> None:
        test_vendor_manifest_covers_assets_and_hashes_match()


if __name__ == "__main__":
    unittest.main(verbosity=2)
