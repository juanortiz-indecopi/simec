from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CHAR, DateTime, ForeignKey, Identity, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.outbound.persistence.entity.base import Base


class NewsArticleEntity(Base):
    """Noticia obtenida de prensa o buscadores (segundo entregable)."""

    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("sources.id"))
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="SET NULL")
    )
    url: Mapped[str] = mapped_column(Text)
    # SHA-256 de la URL normalizada: evita guardar la misma noticia dos veces.
    url_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Medio, autor, mercado, conductas detectadas...
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)


class NewsMentionEntity(Base):
    """Persona o empresa mencionada en una noticia."""

    __tablename__ = "news_mentions"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("news_articles.id", ondelete="CASCADE"), primary_key=True
    )
    party_id: Mapped[int] = mapped_column(
        ForeignKey("parties.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    mention_text: Mapped[str | None] = mapped_column(Text)
