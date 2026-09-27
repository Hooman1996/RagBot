"""Staging HTTPS or local forwarded-browser auth smoke test. Prints status, never credentials or cookies."""
from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx


def check(ok: bool, label: str) -> None:
    print(f'{"PASS" if ok else "FAIL"} {label}')
    if not ok:
        raise SystemExit(1)


def main() -> None:
    origin = os.environ["RAGBOT_STAGING_URL"].rstrip("/")
    parsed = urlparse(origin)
    check((parsed.scheme == "https" and parsed.hostname is not None) or
          (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}),
          "HTTPS or local forwarded HTTP origin")
    users = [(os.environ[f"RAGBOT_TEST_USER_{suffix}"],
              os.environ[f"RAGBOT_TEST_PASSWORD_{suffix}"]) for suffix in ("A", "B")]
    with httpx.Client(base_url=origin, timeout=15.0, follow_redirects=False) as anonymous, \
         httpx.Client(base_url=origin, timeout=15.0, follow_redirects=False) as a, \
         httpx.Client(base_url=origin, timeout=15.0, follow_redirects=False) as b:
        check(anonymous.get("/api/auth/me").status_code == 401, "anonymous API denied")
        check(anonymous.get("/app").status_code == 303, "anonymous page redirected")
        for client, (username, password) in ((a, users[0]), (b, users[1])):
            response = client.post("/api/login", json={"username": username, "password": password},
                                   headers={"Origin": origin})
            check(response.status_code == 200, "login")
            check(set(response.json()["user"]) == {"id", "username", "display_name", "role", "permissions", "landing_path"}
                  and response.json()["landing_path"] == response.json()["user"]["landing_path"],
                  "user DTO redacted")
            cookie = response.headers.get("set-cookie", "").lower()
            check(("secure" in cookie if parsed.scheme == "https" else "secure" not in cookie)
                  and "httponly" in cookie and "samesite=strict" in cookie,
                  "session cookie flags")
            check(client.get("/api/auth/me").status_code == 200, "session resolves")
        check(a.cookies.get("ragbot_web_session") != b.cookies.get("ragbot_web_session"),
              "independent user sessions")
        check(a.post("/api/sessions", json={"title": "auth smoke"},
                     headers={"Origin": origin}).status_code == 403, "CSRF rejected")
        headers_a = {"Origin": origin, "X-CSRF-Token": a.cookies["ragbot_web_csrf"]}
        headers_b = {"Origin": origin, "X-CSRF-Token": b.cookies["ragbot_web_csrf"]}
        created = a.post("/api/sessions", json={"title": "auth smoke"}, headers=headers_a)
        check(created.status_code == 200, "owned chat created")
        session_id = created.json()["id"]
        try:
            check(b.get(f"/api/sessions/{session_id}").status_code == 404,
                  "other user cannot read chat")
            check(b.delete(f"/api/sessions/{session_id}", headers=headers_b).status_code == 404,
                  "other user cannot delete chat")
        finally:
            check(a.delete(f"/api/sessions/{session_id}", headers=headers_a).status_code == 200,
                  "smoke chat removed")
        check(a.post("/api/auth/logout", headers=headers_a).status_code == 200, "logout")
        check(a.get("/api/auth/me").status_code == 401, "logout cleared browser session")
        check(b.post("/api/auth/logout", headers=headers_b).status_code == 200,
              "second user logout")


if __name__ == "__main__":
    main()
