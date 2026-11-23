"""Implementación vacía del puerto: se usa cuando DATABASE_URL no está configurada.

Nunca encuentra fotos, siempre permite consultar en vivo y no guarda nada. Así los servicios no
necesitan preguntar si hay base de datos: la API funciona como puente, igual que antes.
"""
from collections.abc import Collection
from datetime import timedelta

from app.application.port.out.snapshot_repository_port import QueryOutcome, SnapshotRepositoryPort
from app.domain.models.query import StoredSnapshot


class NullSnapshotRepository(SnapshotRepositoryPort):
    async def find_current(
        self, source_names: Collection[str], cache_key: str
    ) -> dict[str, StoredSnapshot]:
        return {}

    async def try_begin_refresh(
        self, source_names: Collection[str], cache_key: str, lease: timedelta
    ) -> frozenset[str]:
        return frozenset(source_names)

    async def refreshing(
        self, source_names: Collection[str], cache_key: str, lease: timedelta
    ) -> frozenset[str]:
        return frozenset()

    async def end_refresh(self, source_names: Collection[str], cache_key: str) -> None:
        return None

    async def save_outcome(self, outcome: QueryOutcome) -> None:
        return None
