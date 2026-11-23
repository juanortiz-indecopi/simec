from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.outbound.persistence.entity.base import Base
from app.infrastructure.outbound.persistence.entity.types import updated_at_column


class SourceCacheEntity(Base):
    """Puntero a la foto vigente por (fuente, parámetro). Decide si se responde desde la BD.

    Un refresco que falla actualiza `last_snapshot_id` pero nunca `last_success_snapshot_id`,
    así los datos buenos anteriores se siguen sirviendo.
    """

    __tablename__ = "source_cache"

    source_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("sources.id"), primary_key=True
    )
    # Parámetro normalizado: RUC, DNI o "CUSCO|Personas Juridicas|11156404".
    cache_key: Mapped[str] = mapped_column(String(500), primary_key=True)
    party_id: Mapped[int | None] = mapped_column(
        ForeignKey("parties.id", ondelete="SET NULL"), index=True
    )
    # Último intento (puede ser ERROR o NO_DATA).
    last_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("source_snapshots.id"))
    # Última foto válida: la que se sirve al usuario.
    last_success_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_snapshots.id")
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A partir de aquí la foto se marca is_stale (aviso al usuario, no re-consulta automática).
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # No NULL = hay un scraping en curso para esta clave (evita consultas duplicadas).
    refreshing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = updated_at_column()
