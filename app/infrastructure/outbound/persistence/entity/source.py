from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Identity, Integer, SmallInteger, String, Text, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.outbound.persistence.entity.base import Base
from app.infrastructure.outbound.persistence.entity.types import created_at_column


class SourceEntity(Base):
    """Catálogo de fuentes consultadas. `code` coincide con AuditResult.source_name."""

    __tablename__ = "sources"
    __table_args__ = (CheckConstraint("cache_ttl_hours > 0", name="cache_ttl_hours_positive"),)

    id: Mapped[int] = mapped_column(SmallInteger, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    # IDENTITY, TAX_REGISTRY, PUBLIC_PROCUREMENT, PROPERTY_REGISTRY, JUDICIAL, PRESS, SOCIAL_NETWORK...
    category: Mapped[str] = mapped_column(String(40))
    base_url: Mapped[str | None] = mapped_column(Text)
    # Horas tras las que la foto se marca como posiblemente desactualizada (no re-consulta sola).
    cache_ttl_hours: Mapped[int] = mapped_column(Integer, server_default=text("720"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    created_at: Mapped[datetime] = created_at_column()
