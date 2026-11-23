from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.outbound.persistence.entity.base import Base
from app.infrastructure.outbound.persistence.entity.types import (
    PARTY_TYPE,
    created_at_column,
    updated_at_column,
)


class PartyEntity(Base):
    """Persona natural o jurídica: vista consolidada vigente, base de vínculos y búsquedas."""

    __tablename__ = "parties"
    __table_args__ = (
        UniqueConstraint("document_type", "document_number"),
        CheckConstraint(r"tax_id ~ '^[0-9]{11}$'", name="tax_id_format"),
        # Búsqueda aproximada por nombre ("ruiz aucapiña") con pg_trgm.
        Index(
            "ix_parties_display_name_trgm",
            "display_name",
            postgresql_using="gin",
            postgresql_ops={"display_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    party_type: Mapped[str] = mapped_column(PARTY_TYPE)
    # DNI, RUC, CE, PASAPORTE, OTRO
    document_type: Mapped[str] = mapped_column(String(20))
    document_number: Mapped[str] = mapped_column(String(20))
    # RUC. Una persona con RUC 10 comparte party con su DNI (dígitos 3 a 10 del RUC).
    tax_id: Mapped[str | None] = mapped_column(CHAR(11), unique=True)
    display_name: Mapped[str] = mapped_column(String(400))
    # True si fue consultado directamente; False si solo apareció como vínculo de otro.
    is_query_subject: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class PartyLinkEntity(Base):
    """Vínculo entre dos parties (accionista, representante legal...) con la foto que lo respalda."""

    __tablename__ = "party_links"
    __table_args__ = (
        UniqueConstraint("from_party_id", "to_party_id", "link_type", "source_id"),
        CheckConstraint("from_party_id <> to_party_id", name="not_self_link"),
        CheckConstraint(
            "share_percentage IS NULL OR share_percentage BETWEEN 0 AND 100",
            name="share_percentage_range",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # Quien ejerce el vínculo (accionista, representante).
    from_party_id: Mapped[int] = mapped_column(
        ForeignKey("parties.id", ondelete="CASCADE")
    )
    # Empresa vinculada.
    to_party_id: Mapped[int] = mapped_column(
        ForeignKey("parties.id", ondelete="CASCADE"), index=True
    )
    # SHAREHOLDER, LEGAL_REPRESENTATIVE, SEACE_LINKED_PROVIDER, OTHER...
    link_type: Mapped[str] = mapped_column(String(40))
    role: Mapped[str | None] = mapped_column(String(150))
    share_percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    start_date: Mapped[date | None] = mapped_column(Date)
    source_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("sources.id"))
    # Última foto que confirmó el vínculo.
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("source_snapshots.id"))
    # False si ya no aparece en la foto más reciente de su fuente.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
