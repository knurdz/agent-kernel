"""Alembic environment for AgriPilot marketplace (Phase 18).

Target URL precedence: ``sqlalchemy.url`` set on the Config (tests / programmatic
runs) > ``AK_MARKETPLACE__DATABASE_URL`` > ``config.yaml`` > default.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import marketplace.models  # noqa: F401  populate Base metadata
from marketplace.database import get_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = marketplace.models.Base.metadata


def _target_url() -> str:
    configured = (config.get_main_option("sqlalchemy.url") or "").strip()
    if configured:
        return configured
    return get_database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_target_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _target_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
