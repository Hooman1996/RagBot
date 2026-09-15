"""Compatibility launcher for the PostgreSQL evaluation worker."""

from evaluation_system.backend.app.worker.postgres_worker import main as worker_main


def main() -> int:
    return worker_main()


if __name__ == "__main__":
    raise SystemExit(main())
