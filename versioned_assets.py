"""Content-addressed URLs for the existing first-party dashboard assets."""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import re
from pathlib import Path

from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from frontend_paths import STATIC_DIR


# Keep this list deliberately narrow: vendor Chart.js remains a local static asset.
VERSIONED_ASSETS = frozenset({
    "css/base.css", "css/app.css", "css/analytics.css", "css/web_controls.css",
    "js/web_auth.js", "js/analytics.js",
})
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def asset_bytes(path: str) -> bytes:
    if path not in VERSIONED_ASSETS:
        raise ValueError("Unknown versioned asset")
    file = (STATIC_DIR / path).resolve()
    if not file.is_relative_to(STATIC_DIR.resolve()):
        raise ValueError("Invalid asset path")
    return file.read_bytes()


def asset_digest(path: str) -> str:
    return hashlib.sha256(asset_bytes(path)).hexdigest()


def asset_integrity(path: str) -> str:
    digest = hashlib.sha256(asset_bytes(path)).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def versioned_asset(request: Request, path: str):
    return request.url_for("static", path=f"_v/{asset_digest(path)}/{path}")


class VersionedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        if not path.startswith("_v/"):
            return await super().get_response(path, scope)
        parts = path.split("/", 2)
        if len(parts) != 3 or not _DIGEST.fullmatch(parts[1]) or parts[2] not in VERSIONED_ASSETS:
            return Response(status_code=404, headers={"Cache-Control": "no-store"})
        try:
            body = asset_bytes(parts[2])
        except OSError:
            return Response(status_code=404, headers={"Cache-Control": "no-store"})
        digest = hashlib.sha256(body).hexdigest()
        if digest != parts[1]:
            return Response(status_code=404, headers={"Cache-Control": "no-store"})
        headers = {
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{digest}"',
            "X-Content-Type-Options": "nosniff",
        }
        media_type = mimetypes.guess_type(parts[2])[0] or "application/octet-stream"
        if scope["method"] == "HEAD":
            headers["Content-Length"] = str(len(body))
            body = b""
        return Response(body, media_type=media_type, headers=headers)
