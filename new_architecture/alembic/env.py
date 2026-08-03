# alembic/env.py

"""
Alembic Environment Configuration
Database migration environment setup and configuration
"""

from logging.config import fileConfig
import os
import sys
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# Add project root to Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Import application components
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_database_url

# Import all models to ensure they're registered with SQLAlchemy
from app.models.user import User
from app.models.document import Document, DocumentChunk
from app.models.embedding import Embedding
from app.models.query import Query, QueryResult
from app.models.collection import Collection
from app.models.permission import Permission, Role, UserRole
from app.models.api_key import APIKey
from app.models.audit_log import AuditLog

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate support
target_metadata = Base.meta_data

# Get database URL from settings
database_url = get_database_url()

# Override sqlalchemy.url in alembic.ini with environment variable
config.set_main_option('sqlalchemy.url', database_url)


def get_url():
    """
    Get database URL from environment or config

    Returns:
        Database URL string
    """
    return database_url


def include_object(object, name, type_, reflected, compare_to):
    """
    Filter objects to include in migrations

    Args:
        object: Database object
        name: Object name
        type_: Object type
        reflected: Whether object is reflected from database
        compare_to: Object to compare to

    Returns:
        True if object should be included, False otherwise
    """
    # Skip internal tables
    if type_ == "table" and name in ['alembic_version', 'spatial_ref_sys']:
        return False

    # Skip indexes on excluded tables
    if type_ == "index" and object.table.name in ['alembic_version', 'spatial_ref_sys']:
        return False

    return True


def include_name(name, type_, parent_names):
    """
    Filter schema names to include in migrations

    Args:
        name: Schema name
        type_: Object type
        parent_names: Parent schema names

    Returns:
        True if name should be included, False otherwise
    """
    # Include only public schema by default
    if type_ == "schema":
        return name in [None, "public"]

    return True


def process_revision_directives(context, revision, directives):
    """
    Process revision directives before writing migration script

    Args:
        context: Migration context
        revision: Revision tuple
        directives: List of directives
    """
    # Prevent empty migrations
    if config.cmd_opts.autogenerate:
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            print("No changes detected, skipping migration generation.")


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_url()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        include_name=include_name,
        process_revision_directives=process_revision_directives,
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
        version_table='alembic_version',
        render_as_batch=True  # For SQLite compatibility
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a
    connection with the context.
    """
    # Get configuration
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    # Create engine
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            include_name=include_name,
            process_revision_directives=process_revision_directives,
            compare_type=True,
            compare_server_default=True,
            include_schemas=False,
            version_table='alembic_version',
            render_as_batch=True,  # For SQLite compatibility
            transaction_per_migration=True,  # Wrap each migration in transaction
        )

        with context.begin_transaction():
            context.run_migrations()


# Determine which mode to run
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()