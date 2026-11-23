from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.audit import AuditStatus
from app.infrastructure.outbound.persistence.entity.base import Base
from app.infrastructure.outbound.persistence.entity.types import AUDIT_STATUS


class SnapshotPayloadEntity(Base):
    """Contenido JSON deduplicado por hash: N consultas con el mismo resultado ocupan una fila.

    Las columnas JSONB usan compresión lz4 (se configura en la migración).
    """

    __tablename__ = "snapshot_payloads"
    __table_args__ = (
        CheckConstraint(r"data_hash ~ '^[0-9a-f]{64}$'", name="data_hash_format"),
        # Búsquedas dentro del JSON con el operador @> ("contiene").
        Index(
            "ix_snapshot_payloads_data_gin",
            "data",
            postgresql_using="gin",
            postgresql_ops={"data": "jsonb_path_ops"},
        ),
    )

    # SHA-256 en hexadecimal del JSON `data` en forma canónica.
    data_hash: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    # Dataclass de dominio serializado.
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Respuesta original del extractor, la primera vez que se vio este contenido.
    raw: Mapped[Any | None] = mapped_column(JSONB)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourceSnapshotEntity(Base):
    """Una fila por AuditResult. Solo INSERT: es el historial con las fechas de consulta."""

    __tablename__ = "source_snapshots"
    __table_args__ = (
        Index(None, "source_id", "query_parameter", "executed_at"),
        CheckConstraint("duration_ms >= 0", name="duration_ms_non_negative"),
        # Una foto exitosa siempre tiene contenido; ERROR y NO_DATA no lo tienen.
        CheckConstraint(
            "status <> 'SUCCESS' OR data_hash IS NOT NULL", name="success_has_payload"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("sources.id"))
    # Consulta que provocó esta ejecución.
    query_id: Mapped[int | None] = mapped_column(ForeignKey("queries.id", ondelete="SET NULL"))
    party_id: Mapped[int | None] = mapped_column(
        ForeignKey("parties.id", ondelete="SET NULL"), index=True
    )
    query_parameter: Mapped[str] = mapped_column(String(500))
    status: Mapped[AuditStatus] = mapped_column(AUDIT_STATUS)
    duration_ms: Mapped[int] = mapped_column(Integer)
    details: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_hash: Mapped[str | None] = mapped_column(
        CHAR(64), ForeignKey("snapshot_payloads.data_hash")
    )


class QuerySnapshotEntity(Base):
    """Qué fotos se usaron para responder cada consulta y si salieron de la BD o de la web."""

    __tablename__ = "query_snapshots"

    query_id: Mapped[int] = mapped_column(
        ForeignKey("queries.id", ondelete="CASCADE"), primary_key=True
    )
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("source_snapshots.id"), primary_key=True)
    from_cache: Mapped[bool] = mapped_column(Boolean)
