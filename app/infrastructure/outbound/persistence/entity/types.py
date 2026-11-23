"""Tipos ENUM nativos de PostgreSQL.

Solo se usan para listas estables. Las que crecerán con nuevas fuentes (categoría de fuente, tipo
de consulta, tipo de vínculo, tipo de documento) son VARCHAR validados en Python, porque un ENUM
de PostgreSQL exige migración para agregar valores y no permite quitarlos.
"""
from sqlalchemy import DateTime, Enum, func
from sqlalchemy.orm import mapped_column

from app.domain.models.audit import AuditStatus
from app.infrastructure.outbound.persistence.entity.base import SCHEMA

PARTY_TYPE = Enum("PERSON", "COMPANY", name="party_type", schema=SCHEMA)

AUDIT_STATUS = Enum(
    AuditStatus,
    name="audit_status",
    schema=SCHEMA,
    values_callable=lambda enum: [member.value for member in enum],
)

# CACHE: responde desde la BD si hay foto válida. REFRESH: fuerza la consulta web (?refresh=true).
FETCH_MODE = Enum("CACHE", "REFRESH", name="fetch_mode", schema=SCHEMA)

SERVED_FROM = Enum("DATABASE", "LIVE", "MIXED", name="served_from", schema=SCHEMA)


def created_at_column():
    """Fecha de creación asignada por PostgreSQL."""
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at_column():
    """Fecha de última modificación; el ORM la renueva en cada UPDATE."""
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
