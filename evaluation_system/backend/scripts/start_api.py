"""Optional standalone API launcher using backend-local settings."""

import uvicorn

from app.config import get_settings


def main() -> int:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
