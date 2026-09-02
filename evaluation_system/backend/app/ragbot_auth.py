"""Bridge to the existing process-local RagBot login state."""

from fastapi import HTTPException, Request


def establish_ragbot_user(request: Request, user: dict | None) -> None:
    request.app.state.ragbot_authenticated_user = user


def require_ragbot_user(request: Request) -> dict:
    current_user = getattr(
        request.app.state, "ragbot_authenticated_user", None
    )
    if not isinstance(current_user, dict) or not current_user.get("id"):
        raise HTTPException(
            status_code=401,
            detail={"error_code": "RAGBOT_AUTH_REQUIRED"},
        )
    return current_user
