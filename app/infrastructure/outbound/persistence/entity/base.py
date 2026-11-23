"""Base declarativa de SQLAlchemy para todas las tablas del esquema de SIMEC.

La convención de nombres hace que índices y restricciones tengan nombres estables y legibles
(p.ej. `fk_party_links_from_party_id_parties`), lo que permite que Alembic los detecte, compare
y elimine sin ambigüedad en migraciones futuras.
"""
from typing import Final

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

SCHEMA: Final = get_settings().database_schema

NAMING_CONVENTION: Final = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)
