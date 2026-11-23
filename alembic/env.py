"""Entorno de migraciones de Alembic para SIMEC.

- La URL sale de DATABASE_MIGRATION_URL (.env), con el usuario dueño del esquema (simec_owner).
  No se escribe en alembic.ini para no versionar contraseñas.
- Solo se gestiona el esquema de la app (DATABASE_SCHEMA); se ignoran public y cualquier otro.
- La tabla de control `alembic_version` vive en ese mismo esquema.
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import get_settings
from app.infrastructure.outbound.persistence.entity import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
SCHEMA = settings.database_schema
target_metadata = Base.metadata


def _migration_url() -> str:
    if settings.database_migration_url is None:
        raise RuntimeError("DATABASE_MIGRATION_URL no está configurada en el archivo .env")
    return settings.database_migration_url.get_secret_value()


def _include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    if type_ == "schema":
        return name == SCHEMA
    return True


def _configure_kwargs() -> dict:
    return {
        "target_metadata": target_metadata,
        "include_schemas": True,
        "include_name": _include_name,
        "version_table_schema": SCHEMA,
        "compare_type": True,
    }


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (alembic upgrade head --sql)."""
    context.configure(
        url=_migration_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_kwargs(),
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **_configure_kwargs())
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # search_path solo con "public": así el esquema de la app NO es el esquema por defecto de la
    # conexión y Alembic lo reconoce por su nombre al comparar modelos contra la base. Todas las
    # tablas y tipos se califican explícitamente con el esquema en las migraciones.
    connectable = create_async_engine(
        _migration_url(),
        poolclass=pool.NullPool,
        connect_args={"server_settings": {"search_path": "public"}},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
