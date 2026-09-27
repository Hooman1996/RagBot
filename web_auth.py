"""Short-lived signed browser identity; mobile and evaluation use separate contracts."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from web_permissions import permissions_for, landing_for, route_permission
from starlette.concurrency import run_in_threadpool

SESSION_COOKIE = "ragbot_web_session"
CSRF_COOKIE = "ragbot_web_csrf"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MAX_COOKIE_LENGTH = 1024


def session_secret() -> bytes:
    value = os.getenv("WEB_SESSION_SECRET", "")
    if len(value.encode("utf-8")) < 32:
        raise RuntimeError("WEB_SESSION_SECRET must contain at least 32 bytes")
    return value.encode("utf-8")


def cookie_secure() -> bool:
    mode = os.getenv("WEB_COOKIE_MODE", "https").lower()
    environment = os.getenv("WEB_ENVIRONMENT", "production").lower()
    origin = os.getenv("WEB_PUBLIC_ORIGIN", "")
    parsed = urlsplit(origin)
    valid_origin = (bool(parsed.hostname) and not parsed.username and not parsed.password
                    and not parsed.path and not parsed.query and not parsed.fragment
                    and origin == f"{parsed.scheme}://{parsed.netloc}")
    if mode == "https":
        if not valid_origin or parsed.scheme != "https":
            raise RuntimeError("WEB_PUBLIC_ORIGIN must be the external HTTPS origin")
        return True
    if mode == "local-http" and environment == "development":
        if not valid_origin or parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise RuntimeError("local-http requires a localhost WEB_PUBLIC_ORIGIN")
        return False
    raise RuntimeError("WEB_COOKIE_MODE must be https or development local-http")


def session_seconds() -> int:
    value = int(os.getenv("WEB_SESSION_SECONDS", "900"))
    if not 300 <= value <= 3600:
        raise RuntimeError("WEB_SESSION_SECONDS must be between 300 and 3600")
    return value


def validate_config() -> None:
    session_secret()
    cookie_secure()
    session_seconds()


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _encode(decoded) != value:
        raise ValueError("Non-canonical encoding")
    return decoded


def _mac(purpose: bytes, value: bytes) -> bytes:
    return hmac.new(session_secret(), purpose + b":" + value, hashlib.sha256).digest()


def safe_user(row: dict) -> dict:
    return {"id": row["id"], "username": row["username"],
            "display_name": row.get("full_name", row.get("display_name")), "role": row.get("role"),
            "permissions": sorted(permissions_for(row.get("role"))),
            "landing_path": landing_for(row.get("role"))}


@dataclass(frozen=True)
class CurrentWebUser:
    id: int
    username: str
    display_name: str | None
    role: str | None


def current_web_user(request: Request) -> CurrentWebUser:
    user = getattr(request.state, "web_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


WebUser = Annotated[CurrentWebUser, Depends(current_web_user)]


def create_session(user_id: int) -> tuple[str, str]:
    now = int(time.time())
    payload = {"uid": int(user_id), "iat": now, "exp": now + session_seconds(),
               "nonce": secrets.token_urlsafe(24)}
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    token = f"{encoded}.{_encode(_mac(b'web-session', encoded.encode('ascii')))}"
    return token, csrf_for_nonce(payload["nonce"])


def verify_session(token: str) -> dict | None:
    if not token or len(token) > MAX_COOKIE_LENGTH or not token.isascii():
        return None
    try:
        encoded, signature = token.split(".")
        if not hmac.compare_digest(_mac(b"web-session", encoded.encode("ascii")), _decode(signature)):
            return None
        payload = json.loads(_decode(encoded))
        now = int(time.time())
        if (type(payload) is not dict or type(payload.get("uid")) is not int or payload["uid"] <= 0
                or type(payload.get("iat")) is not int or type(payload.get("exp")) is not int
                or type(payload.get("nonce")) is not str or len(payload["nonce"]) != 32
                or not payload["nonce"].isascii() or payload["iat"] > now + 30
                or payload["exp"] <= now or payload["exp"] <= payload["iat"]
                or payload["exp"] - payload["iat"] > session_seconds()):
            return None
        return payload
    except (ValueError, TypeError, UnicodeError, KeyError):
        return None


def csrf_for_nonce(nonce: str) -> str:
    return _encode(_mac(b"web-csrf", nonce.encode("ascii")))


def job_access_token(job_id: str, user_id: int) -> str:
    return _encode(_mac(b"mass-answer-job", f"{user_id}:{job_id}".encode("ascii")))


def valid_job_access(job_id: str, user_id: int, access: str) -> bool:
    return bool(job_id and job_id.isascii() and len(job_id) <= 128
                and access and len(access) <= 128 and access.isascii() and
                hmac.compare_digest(access, job_access_token(job_id, user_id)))


def set_cookies(response, session: str, csrf: str) -> None:
    common = {"max_age": session_seconds(), "path": "/", "samesite": "strict",
              "secure": cookie_secure()}
    response.set_cookie(SESSION_COOKIE, session, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **common)
    response.headers["Cache-Control"] = "no-store"


def clear_cookies(response) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", samesite="strict", secure=cookie_secure())
    response.headers["Cache-Control"] = "no-store"


def web_route(path: str, method: str = "GET") -> bool:
    if path.startswith("/api/mobile/") or path.startswith("/api/internal/evaluation/v1/"):
        return False
    if (method, path) in {
        ("GET", "/"), ("POST", "/api/login"), ("GET", "/api/health"),
        ("GET", "/docs"), ("GET", "/redoc"), ("GET", "/openapi.json"),
    }:
        return False
    if method == "GET" and (path == "/static" or path.startswith("/static/")):
        return False
    return True


def forbidden_page() -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Access denied</title><body style="font:1rem system-ui;'
        'max-width:40rem;margin:10vh auto;padding:1rem">'
        '<h1>Access denied / دسترسی مجاز نیست</h1>'
        '<p>Your current role does not allow this page.</p>'
        '<a href="/access-denied">Account access</a></body></html>',
        status_code=403, headers={"Cache-Control": "no-store"},
    )


async def web_auth_middleware(request: Request, call_next, db):
    path = request.url.path
    if not web_route(path, request.method):
        return await call_next(request)
    payload = verify_session(request.cookies.get(SESSION_COOKIE, ""))
    row = await run_in_threadpool(db.get_web_user_by_id, payload["uid"]) if payload else None
    if row is None or not row["is_active"]:
        if not path.startswith("/api/") and not path.startswith("/knowledge-base/api/"):
            return RedirectResponse("/", status_code=303)
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    request.state.web_user = CurrentWebUser(
        row["id"], row["username"], row.get("full_name"), row.get("role")
    )
    if (request.method, path) not in {
        ("GET", "/api/auth/me"), ("POST", "/api/auth/logout"),
        ("GET", "/access-denied"),
    }:
        permission = route_permission(request.method, path)
        if permission is None or permission not in permissions_for(row.get("role")):
            if not path.startswith("/api/") and not path.startswith("/knowledge-base/api/"):
                return forbidden_page()
            return JSONResponse(
                {"detail": "Permission denied", "required_permission": permission},
                status_code=403, headers={"Cache-Control": "no-store"},
            )
    if request.method in UNSAFE_METHODS:
        csrf = request.cookies.get(CSRF_COOKIE, "")
        header = request.headers.get("X-CSRF-Token", "")
        expected = csrf_for_nonce(payload["nonce"])
        if not (csrf and header and len(header) <= 128 and header.isascii()
                and hmac.compare_digest(csrf, expected)
                and hmac.compare_digest(header, expected)):
            return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != os.environ["WEB_PUBLIC_ORIGIN"]:
            return JSONResponse({"detail": "Invalid origin"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response
