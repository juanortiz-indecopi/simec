from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.outbound.persistence.entity.base import Base
from app.infrastructure.outbound.persistence.entity.types import FETCH_MODE, SERVED_FROM


class QueryEntity(Base):
    """Cada petición recibida: qué se consultó, cuándo, en qué modo y de dónde salió la respuesta."""

    __tablename__ = "queries"
    __table_args__ = (Index(None, "query_type", "query_parameter"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # COMPANY_BY_RUC, PERSON_BY_DNI, SUNARP_PARTIDA, NAME_SEARCH, NEWS_SEARCH...
    query_type: Mapped[str] = mapped_column(String(40))
    # RUC, DNI o "CUSCO|Personas Juridicas|11156404".
    query_parameter: Mapped[str] = mapped_column(String(500))
    party_id: Mapped[int | None] = mapped_column(
        ForeignKey("parties.id", ondelete="SET NULL"), index=True
    )
    fetch_mode: Mapped[str] = mapped_column(FETCH_MODE, server_default="CACHE")
    served_from: Mapped[str | None] = mapped_column(SERVED_FROM)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
