# alembic/migration_helper.py

"""
Migration Helper
Utility functions for managing database migrations
"""

import os
import sys
from pathlib import Path
from typing import Optional, List
import subprocess

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from app.core.config import settings
from app.core.logging import logger


class MigrationHelper:
    """Helper class for database migrations"""

    def __init__(self):
        """Initialize migration helper"""
        self.alembic_dir = Path(__file__).parent
        self.alembic_ini = self.alembic_dir.parent / "alembic.ini"

    def run_command(self, command: List[str]) -> bool:
        """
        Run alembic command

        Args:
            command: Command arguments

        Returns:
            True if successful, False otherwise
        """
        try:
            full_command = ["alembic", "-c", str(self.alembic_ini)] + command

            logger.info(f"Running: {' '.join(full_command)}")

            result = subprocess.run(
                full_command,
                cwd=str(self.alembic_dir.parent),
                capture_output=True,
                text=True
            )

            if result.stdout:
                print(result.stdout)

            if result.stderr:
                print(result.stderr, file=sys.stderr)

            if result.returncode != 0:
                logger.error(f"Command failed with return code {result.returncode}")
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to run command: {str(e)}")
            return False

    def create_migration(
            self,
            message: str,
            autogenerate: bool = True
    ) -> bool:
        """
        Create new migration

        Args:
            message: Migration message
            autogenerate: Auto-generate migration from models

        Returns:
            True if successful, False otherwise
        """
        command = ["revision"]

        if autogenerate:
            command.append("--autogenerate")

        command.extend(["-m", message])

        return self.run_command(command)

    def upgrade(self, revision: str = "head") -> bool:
        """
        Upgrade database to revision

        Args:
            revision: Target revision (default: head)

        Returns:
            True if successful, False otherwise
        """
        return self.run_command(["upgrade", revision])

    def downgrade(self, revision: str = "-1") -> bool:
        """
        Downgrade database to revision

        Args:
            revision: Target revision (default: -1)

        Returns:
            True if successful, False otherwise
        """
        return self.run_command(["downgrade", revision])

    def current(self) -> bool:
        """
        Show current revision

        Returns:
            True if successful, False otherwise
        """
        return self.run_command(["current"])

    def history(self, verbose: bool = False) -> bool:
        """
        Show migration history

        Args:
            verbose: Show verbose output

        Returns:
            True if successful, False otherwise
        """
        command = ["history"]
        if verbose:
            command.append("--verbose")

        return self.run_command(command)

    def heads(self) -> bool:
        """
        Show current heads

        Returns:
            True if successful, False otherwise
        """
        return self.run_command(["heads"])

    def branches(self) -> bool:
        """
        Show current branches

        Returns:
            True if successful, False otherwise
        """
        return self.run_command(["branches"])

    def show(self, revision: str) -> bool:
        """
        Show migration details

        Args:
            revision: Revision to show

        Returns:
            True if successful, False otherwise
        """
        return self.run_command(["show", revision])

    def stamp(self, revision: str) -> bool:
        """
        Stamp database with revision

        Args:
            revision: Revision to stamp

        Returns:
            True if successful, False otherwise
        """
        return self.run_command(["stamp", revision])

    def check(self) -> bool:
        """
        Check for pending migrations

        Returns:
            True if no pending migrations, False otherwise
        """
        return self.run_command(["check"])

    def merge(self, revisions: List[str], message: str) -> bool:
        """
        Merge multiple revisions

        Args:
            revisions: Revisions to merge
            message: Merge message

        Returns:
            True if successful, False otherwise
        """
        command = ["merge"] + revisions + ["-m", message]
        return self.run_command(command)


def main():
    """Main CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description="Database Migration Helper")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Create migration
    create_parser = subparsers.add_parser("create", help="Create new migration")
    create_parser.add_argument("message", help="Migration message")
    create_parser.add_argument(
        "--no-autogenerate",
        action="store_true",
        help="Don't auto-generate migration"
    )

    # Upgrade
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade database")
    upgrade_parser.add_argument(
        "revision",
        nargs="?",
        default="head",
        help="Target revision (default: head)"
    )

    # Downgrade
    downgrade_parser = subparsers.add_parser("downgrade", help="Downgrade database")
    downgrade_parser.add_argument(
        "revision",
        nargs="?",
        default="-1",
        help="Target revision (default: -1)"
    )

    # Current
    subparsers.add_parser("current", help="Show current revision")

    # History
    history_parser = subparsers.add_parser("history", help="Show migration history")
    history_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show verbose output"
    )

    # Heads
    subparsers.add_parser("heads", help="Show current heads")

    # Branches
    subparsers.add_parser("branches", help="Show current branches")

    # Show
    show_parser = subparsers.add_parser("show", help="Show migration details")
    show_parser.add_argument("revision", help="Revision to show")

    # Stamp
    stamp_parser = subparsers.add_parser("stamp", help="Stamp database with revision")
    stamp_parser.add_argument("revision", help="Revision to stamp")

    # Check
    subparsers.add_parser("check", help="Check for pending migrations")

    # Merge
    merge_parser = subparsers.add_parser("merge", help="Merge revisions")
    merge_parser.add_argument("revisions", nargs="+", help="Revisions to merge")
    merge_parser.add_argument("-m", "--message", required=True, help="Merge message")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    helper = MigrationHelper()

    # Execute command
    success = False

    if args.command == "create":
        success = helper.create_migration(
            args.message,
            autogenerate=not args.no_autogenerate
        )
    elif args.command == "upgrade":
        success = helper.upgrade(args.revision)
    elif args.command == "downgrade":
        success = helper.downgrade(args.revision)
    elif args.command == "current":
        success = helper.current()
    elif args.command == "history":
        success = helper.history(verbose=args.verbose)
    elif args.command == "heads":
        success = helper.heads()
    elif args.command == "branches":
        success = helper.branches()
    elif args.command == "show":
        success = helper.show(args.revision)
    elif args.command == "stamp":
        success = helper.stamp(args.revision)
    elif args.command == "check":
        success = helper.check()
    elif args.command == "merge":
        success = helper.merge(args.revisions, args.message)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()