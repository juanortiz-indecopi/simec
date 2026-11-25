"""Implementación del puerto SnapshotRepositoryPort sobre PostgreSQL.

Cada método abre una única transacción corta. La conversión a JSON (CPU) se hace antes de abrir
la transacción, para tener la conexión tomada el menor tiempo posible. Cualquier falla de base de
datos se traduce a PersistenceError: el servicio la captura y responde en vivo igual.
"""
import logging
from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.application.port.out.snapshot_repository_port import (
    PersistenceError,
    QueryOutcome,
    SnapshotRepositoryPort,
    SourceExecution,
)
from app.domain.models.audit import AuditStatus
from app.domain.models.party import PartyRef
from app.domain.models.query import StoredSnapshot
from app.infrastructure.outbound.persistence.database import Database
from app.infrastructure.outbound.persistence.mapper import payload_mapper
from app.infrastructure.outbound.persistence.repository.snapshot_sql_repository import (
    SnapshotSqlRepository,
)

logger = logging.getLogger(__name__)

NO_STRUCTURED_DATA_NOTE = "La fuente informó éxito pero sin datos estructurados."


@dataclass(frozen=True, slots=True)
class _PreparedExecution:
    source_name: str
    query_parameter: str
    status: AuditStatus
    duration_ms: int
    details: str | None
    executed_at: Any
    data: dict[str, Any] | None
    data_hash: str | None
    raw: Any | None

    @property
    def is_success(self) -> bool:
        return self.status is AuditStatus.SUCCESS and self.data_hash is not None


def _prepare(execution: SourceExecution) -> _PreparedExecution:
    audit = execution.audit
    data = data_hash = None
    if execution.data is not None:
        data, data_hash = payload_mapper.dump(execution.data)
    status, details = audit.status, audit.details
    # Una foto SUCCESS siempre debe tener contenido (restricción de la tabla). Si la fuente dijo
    # SUCCESS sin datos, se registra como NO_DATA dejando constancia en el detalle.
    if status is AuditStatus.SUCCESS and data_hash is None:
        status = AuditStatus.NO_DATA
        details = f"{details} | {NO_STRUCTURED_DATA_NOTE}" if details else NO_STRUCTURED_DATA_NOTE
    return _PreparedExecution(
        source_name=audit.source_name,
        query_parameter=audit.query_parameter,
        status=status,
        duration_ms=audit.duration_ms,
        details=details,
        executed_at=audit.executed_at_utc,
        data=data,
        data_hash=data_hash,
        raw=None if execution.raw is None else payload_mapper.to_jsonable(execution.raw),
    )


class PostgresSnapshotRepository(SnapshotRepositoryPort):
    def __init__(self, database: Database, default_ttl_hours: int = 720) -> None:
        self._database = database
        self._default_ttl_hours = default_ttl_hours

    async def find_current(
        self, source_names: Collection[str], cache_key: str
    ) -> dict[str, StoredSnapshot]:
        try:
            async with self._database.session() as session:
                repo = SnapshotSqlRepository(session)
                sources = await repo.sources(source_names, create_missing=False)
                rows = await repo.current_snapshots([s.id for s in sources.values()], cache_key)
        except Exception as exc:
            raise PersistenceError(f"No se pudo leer la caché: {type(exc).__name__}: {exc}") from exc

        result: dict[str, StoredSnapshot] = {}
        for row in rows:
            try:
                data = payload_mapper.load(row.data)
            except payload_mapper.PayloadMappingError as exc:
                # Foto ilegible (p.ej. modelo cambiado de forma incompatible): se ignora y la
                # fuente se consultará en vivo, en vez de fallar toda la respuesta.
                logger.warning("Foto %s de %s ignorada: %s", row.snapshot_id, row.source_code, exc)
                continue
            result[row.source_code] = StoredSnapshot(
                snapshot_id=row.snapshot_id,
                source_name=row.source_code,
                data=data,
                executed_at=row.executed_at,
                stale_after=row.expires_at,
            )
        return result

    async def try_begin_refresh(
        self, source_names: Collection[str], cache_key: str, lease: timedelta
    ) -> frozenset[str]:
        try:
            async with self._database.session() as session:
                repo = SnapshotSqlRepository(session)
                sources = await repo.sources(
                    source_names, create_missing=True, default_ttl_hours=self._default_ttl_hours
                )
                claimed = await repo.claim_refresh([s.id for s in sources.values()], cache_key, lease)
        except Exception as exc:
            raise PersistenceError(f"No se pudo reservar el refresco: {type(exc).__name__}: {exc}") from exc
        return frozenset(code for code, info in sources.items() if info.id in claimed)

    async def refreshing(
        self, source_names: Collection[str], cache_key: str, lease: timedelta
    ) -> frozenset[str]:
        try:
            async with self._database.session() as session:
                repo = SnapshotSqlRepository(session)
                sources = await repo.sources(source_names, create_missing=False)
                busy = await repo.refreshing([s.id for s in sources.values()], cache_key, lease)
        except Exception as exc:
            raise PersistenceError(f"No se pudo consultar las reservas: {type(exc).__name__}: {exc}") from exc
        return frozenset(code for code, info in sources.items() if info.id in busy)

    async def end_refresh(self, source_names: Collection[str], cache_key: str) -> None:
        try:
            async with self._database.session() as session:
                repo = SnapshotSqlRepository(session)
                sources = await repo.sources(source_names, create_missing=False)
                await repo.release_refresh([s.id for s in sources.values()], cache_key)
        except Exception as exc:
            raise PersistenceError(f"No se pudo liberar la reserva: {type(exc).__name__}: {exc}") from exc

    async def save_outcome(self, outcome: QueryOutcome) -> None:
        try:
            prepared = [_prepare(execution) for execution in outcome.executions]
        except payload_mapper.PayloadMappingError as exc:
            raise PersistenceError(f"No se pudo convertir el resultado: {exc}") from exc

        try:
            async with self._database.session() as session:
                await self._save(SnapshotSqlRepository(session), outcome, prepared)
        except Exception as exc:
            raise PersistenceError(f"No se pudo guardar la consulta: {type(exc).__name__}: {exc}") from exc

    async def _save(
        self,
        repo: SnapshotSqlRepository,
        outcome: QueryOutcome,
        prepared: list[_PreparedExecution],
    ) -> None:
        party_ids: dict[tuple[str, str], int] = {}

        async def party_id_of(ref: PartyRef, *, is_subject: bool) -> int:
            key = (ref.document_type.value, ref.document_number)
            if key not in party_ids or is_subject:
                party_ids[key] = await repo.upsert_party(ref, is_subject=is_subject)
            return party_ids[key]

        subject_id = (
            await party_id_of(outcome.subject, is_subject=True) if outcome.subject else None
        )
        source_names = {p.source_name for p in prepared} | {l.source_name for l in outcome.links}
        sources = await repo.sources(
            source_names, create_missing=True, default_ttl_hours=self._default_ttl_hours
        )
        query_id = await repo.insert_query(
            query_type=outcome.query_type.value,
            query_parameter=outcome.query_parameter,
            party_id=subject_id,
            fetch_mode=outcome.fetch_mode.value,
            served_from=outcome.served_from.value,
            requested_at=outcome.requested_at,
            completed_at=outcome.completed_at,
        )

        # Fotos nuevas + punteros de caché (y liberación de reservas).
        new_snapshots: dict[str, int] = {}
        # Fuentes cuya foto nueva quedó como vigente. Solo ellas actualizan vínculos: una foto
        # exitosa pero más antigua que la vigente (petición lenta) describe un estado pasado.
        current_sources: set[str] = set()
        for execution in prepared:
            source = sources[execution.source_name]
            if execution.data_hash is not None:
                await repo.ensure_payload(execution.data_hash, execution.data, execution.raw)
            snapshot_id = await repo.insert_snapshot(
                source_id=source.id,
                query_id=query_id,
                party_id=subject_id,
                query_parameter=execution.query_parameter,
                status=execution.status,
                duration_ms=execution.duration_ms,
                details=execution.details,
                executed_at=execution.executed_at,
                data_hash=execution.data_hash,
            )
            new_snapshots[execution.source_name] = snapshot_id
            success_at = execution.executed_at if execution.is_success else None
            became_current = await repo.point_cache(
                source_id=source.id,
                cache_key=outcome.cache_key,
                party_id=subject_id,
                snapshot_id=snapshot_id,
                success_at=success_at,
                expires_at=(
                    success_at + timedelta(hours=source.cache_ttl_hours) if success_at else None
                ),
            )
            if became_current:
                current_sources.add(execution.source_name)
            if outcome.articles and execution.is_success:
                await repo.insert_articles(
                    outcome.articles, source_id=source.id, snapshot_id=snapshot_id
                )

        await repo.link_query_snapshots(
            query_id,
            [(sid, False) for sid in new_snapshots.values()]
            + [(sid, True) for sid in outcome.reused_snapshot_ids],
        )

        # Vínculos: solo los de fuentes cuya foto nueva quedó vigente en esta petición.
        kept_links: dict[str, list[int]] = defaultdict(list)
        for link in outcome.links:
            if link.source_name not in current_sources:
                continue
            holder_id = await party_id_of(link.holder, is_subject=False)
            company_id = await party_id_of(link.company, is_subject=False)
            if holder_id == company_id:
                continue  # p.ej. persona con RUC 10 que figura como su propia representante.
            kept_links[link.source_name].append(
                await repo.upsert_link(
                    holder_id=holder_id,
                    company_id=company_id,
                    link=link,
                    source_id=sources[link.source_name].id,
                    snapshot_id=new_snapshots[link.source_name],
                )
            )

        if subject_id is not None:
            for source_name in current_sources:
                await repo.deactivate_missing_links(
                    source_id=sources[source_name].id,
                    party_id=subject_id,
                    keep_ids=kept_links.get(source_name, ()),
                )
