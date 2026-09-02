"""Alembic environment restricted to the evaluation schema."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

from evaluation_system.backend.app.config import get_settings
from evaluation_system.backend.app.db.base import EVALUATION_SCHEMA, EvaluationBase
from evaluation_system.backend.app.db import models as _models  # noqa: F401


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = EvaluationBase.metadata


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == EVALUATION_SCHEMA
    if "schema_name" in parent_names:
        return parent_names.get("schema_name") == EVALUATION_SCHEMA
    return True


def include_object(obj, name, type_, reflected, compare_to):
    del name, type_, reflected, compare_to
    owner = getattr(obj, "table", obj)
    return getattr(owner, "schema", None) == EVALUATION_SCHEMA


def configure(connection=None, url=None):
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        version_table="alembic_version",
        version_table_schema=EVALUATION_SCHEMA,
        compare_type=True,
    )


def run_migrations_offline():
    configure(url=str(get_settings().sqlalchemy_url(async_driver=False)))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    supplied = config.attributes.get("connection")
    if supplied is not None:
        supplied.execute(text("create schema if not exists evaluation"))
        configure(connection=supplied)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(
        get_settings().sqlalchemy_url(async_driver=False),
        poolclass=pool.NullPool,
        hide_parameters=True,
    )
    with engine.connect() as connection:
        connection.execute(text("create schema if not exists evaluation"))
        connection.commit()
        configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
