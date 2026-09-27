"""Reviewed browser route policy. Unknown roles and routes have no product access."""

from __future__ import annotations

import re

PERMISSIONS = frozenset({
    "chat", "sessions", "feedback", "downloads", "documents", "ocr",
    "analytics", "kb_page", "kb_read", "kb_write", "batch", "system",
})

USER_PERMISSIONS = frozenset({
    "chat", "sessions", "feedback", "downloads", "documents", "ocr",
})

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": PERMISSIONS,
    "user": USER_PERMISSIONS,
    "moderator": USER_PERMISSIONS,
    "analytics_viewer": frozenset({"analytics"}),
    "knowledge_editor": frozenset({"kb_page", "kb_read", "kb_write"}),
}


def permissions_for(role: str | None) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role or "", frozenset())


def landing_for(role: str | None) -> str:
    permissions = permissions_for(role)
    for permission, path in (("chat", "/app"), ("analytics", "/analytics"),
                             ("kb_page", "/knowledge-base/")):
        if permission in permissions:
            return path
    return "/access-denied"


# Each entry is (HTTP method, full path regex, permission). Unknown routes
# remain unclassified and are denied by the browser middleware.
ROUTES = (
    ("GET", r"/app", "chat"),
    ("POST", r"/api/query", "chat"),
    ("GET", r"/api/sessions", "sessions"),
    ("POST", r"/api/sessions", "sessions"),
    ("GET", r"/api/sessions/[^/]+", "sessions"),
    ("DELETE", r"/api/sessions/[^/]+", "sessions"),
    ("POST", r"/api/sessions/[^/]+/message", "sessions"),
    ("GET", r"/api/sessions/[^/]+/messages", "sessions"),
    ("PATCH", r"/api/sessions/[^/]+/pin", "sessions"),
    ("POST", r"/api/sessions/[^/]+/satisfaction", "sessions"),
    ("GET", r"/api/sessions/[^/]+/download", "downloads"),
    ("PATCH", r"/api/queries/[^/]+/feedback", "feedback"),
    ("PATCH", r"/api/queries/[^/]+/comment", "feedback"),
    ("GET", r"/api/documents", "documents"),
    ("GET", r"/api/ocr/status", "ocr"),
    ("POST", r"/api/ocr/extract", "ocr"),
    ("GET", r"/analytics", "analytics"),
    ("GET", r"/api/analytics", "analytics"),
    ("GET", r"/knowledge-base/?", "kb_page"),
    ("GET", r"/knowledge-base/api/documents", "kb_read"),
    ("GET", r"/knowledge-base/api/chunks/[^/]+/versions", "kb_read"),
    ("GET", r"/knowledge-base/api/chunks/[^/]+", "kb_read"),
    ("POST", r"/knowledge-base/api/chunks/create", "kb_write"),
    ("PUT", r"/knowledge-base/api/chunks/update", "kb_write"),
    ("DELETE", r"/knowledge-base/api/chunks/delete/[^/]+", "kb_write"),
    ("POST", r"/knowledge-base/api/chunks/revert", "kb_write"),
    ("POST", r"/api/mass-answer", "batch"),
    ("POST", r"/api/mass-answer/jobs/cleanup", "system"),
    ("GET", r"/api/mass-answer/jobs/[^/]+", "batch"),
    ("GET", r"/api/mass-answer/jobs/[^/]+/result", "batch"),
    ("DELETE", r"/api/mass-answer/jobs/[^/]+", "batch"),
    ("POST", r"/api/initialize", "system"),
    ("GET", r"/api/metrics/admission", "system"),
)


def route_permission(method: str, path: str) -> str | None:
    for route_method, pattern, permission in ROUTES:
        if method == route_method and re.fullmatch(pattern, path):
            return permission
    return None
