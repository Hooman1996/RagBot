"""Read-only CLI for evaluation migration status."""

from evaluation_system.backend.app.config import get_settings
from evaluation_system.backend.app.services.migrations import MigrationService


def main() -> int:
    status = MigrationService(get_settings()).status()
    print(f"status={status.status}")
    print(f"current_revision={status.current_revision or ''}")
    print(f"required_revision={status.required_revision or ''}")
    print("missing_objects=" + ",".join(status.missing_objects))
    print(f"allow_initialize={str(status.allow_initialize).lower()}")
    return 0 if status.status in {"READY", "NOT_INITIALIZED", "UPGRADE_REQUIRED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

