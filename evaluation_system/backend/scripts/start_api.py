"""Optional standalone diagnostic API using root-.env-backed settings."""

import uvicorn

from evaluation_system.backend.app.config import get_settings


def main() -> int:
    settings = get_settings()
    uvicorn.run(
        "evaluation_system.backend.app.main:app",
        host=settings.api_host,
        port=settings.api_port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
