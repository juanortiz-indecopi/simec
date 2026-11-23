"""Coordinador de caché: envuelve el puerto de persistencia con tolerancia a fallos.

Ninguna falla de la base de datos interrumpe una consulta: si PostgreSQL no responde, se registra
un aviso y la consulta sigue en vivo, exactamente como funcionaba antes de tener persistencia.
"""
import asyncio
import logging
import time
from collections.abc import Collection
from datetime import timedelta

from app.application.port.out.snapshot_repository_port import (
    PersistenceError,
    QueryOutcome,
    SnapshotRepositoryPort,
)
from app.domain.models.query import StoredSnapshot

logger = logging.getLogger(__name__)

# La reserva dura lo que el timeout de la fuente más este margen: si el proceso muere, la
# reserva vence sola y otra petición puede volver a consultar.
LEASE_MARGIN = timedelta(minutes=5)
DEFAULT_POLL_INTERVAL_S = 2.0


def lease_for(timeout_s: float) -> timedelta:
    return timedelta(seconds=timeout_s) + LEASE_MARGIN


class SourceCache:
    def __init__(
        self,
        repository: SnapshotRepositoryPort | None,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    ) -> None:
        # None = sin persistencia (modo puente): nada se lee ni se guarda.
        self._repository = repository
        self._poll_interval_s = poll_interval_s

    async def lookup(self, names: Collection[str], cache_key: str) -> dict[str, StoredSnapshot]:
        if self._repository is None or not names:
            return {}
        try:
            return await self._repository.find_current(names, cache_key)
        except PersistenceError as exc:
            logger.warning("Caché no disponible, se consulta en vivo: %s", exc)
            return {}

    async def claim(
        self, names: Collection[str], cache_key: str, lease: timedelta
    ) -> frozenset[str]:
        """Fuentes que esta petición debe consultar. Sin BD, todas (no hay con quién coordinar)."""
        if not names:
            return frozenset()
        if self._repository is None:
            return frozenset(names)
        try:
            return await self._repository.try_begin_refresh(names, cache_key, lease)
        except PersistenceError as exc:
            logger.warning("No se pudo reservar el refresco, se consulta igual: %s", exc)
            return frozenset(names)

    async def wait_for_others(
        self, names: Collection[str], cache_key: str, lease: timedelta, timeout_s: float
    ) -> None:
        """Espera a que otras peticiones terminen de consultar estas fuentes (o a que venza el
        plazo). No lanza excepciones: al terminar, el llamador relee la caché y decide."""
        if self._repository is None or not names:
            return
        pending = set(names)
        deadline = time.monotonic() + timeout_s
        while pending and time.monotonic() < deadline:
            await asyncio.sleep(self._poll_interval_s)
            try:
                pending &= await self._repository.refreshing(pending, cache_key, lease)
            except PersistenceError as exc:
                logger.warning("No se pudo seguir la consulta en curso: %s", exc)
                return

    async def release(self, names: Collection[str], cache_key: str) -> None:
        if self._repository is None or not names:
            return
        try:
            await self._repository.end_refresh(names, cache_key)
        except PersistenceError as exc:
            logger.warning("No se pudo liberar la reserva (vencerá sola): %s", exc)

    async def save(self, outcome: QueryOutcome) -> None:
        if self._repository is None:
            return
        try:
            await self._repository.save_outcome(outcome)
        except PersistenceError as exc:
            logger.error(
                "No se guardó la consulta %s %s (la respuesta se entrega igual): %s",
                outcome.query_type.value,
                outcome.query_parameter,
                exc,
            )
