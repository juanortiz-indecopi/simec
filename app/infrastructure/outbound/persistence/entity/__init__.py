"""Modelos SQLAlchemy de las tablas. Importarlos aquí registra todas las tablas en Base.metadata,
que es lo que Alembic compara contra la base de datos al generar migraciones."""
from app.infrastructure.outbound.persistence.entity.base import Base
from app.infrastructure.outbound.persistence.entity.news import NewsArticleEntity, NewsMentionEntity
from app.infrastructure.outbound.persistence.entity.party import PartyEntity, PartyLinkEntity
from app.infrastructure.outbound.persistence.entity.query import QueryEntity
from app.infrastructure.outbound.persistence.entity.snapshot import (
    QuerySnapshotEntity,
    SnapshotPayloadEntity,
    SourceSnapshotEntity,
)
from app.infrastructure.outbound.persistence.entity.source import SourceEntity
from app.infrastructure.outbound.persistence.entity.source_cache import SourceCacheEntity

__all__ = [
    "Base",
    "NewsArticleEntity",
    "NewsMentionEntity",
    "PartyEntity",
    "PartyLinkEntity",
    "QueryEntity",
    "QuerySnapshotEntity",
    "SnapshotPayloadEntity",
    "SourceCacheEntity",
    "SourceEntity",
    "SourceSnapshotEntity",
]
