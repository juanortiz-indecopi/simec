"""Operaciones SQL sobre las tablas de consultas, fotos, caché y vínculos.

Cada método ejecuta sentencias sobre la sesión recibida; NO confirma ni abre transacciones: eso lo
decide el adaptador, que agrupa todo un guardado en una única transacción corta.
"""
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Interval, and_, bindparam, case, func, null, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.audit import AuditStatus
from app.domain.models.party import PartyLink, PartyRef
from app.infrastructure.outbound.persistence.entity import (
    PartyEntity,
    PartyLinkEntity,
    QueryEntity,
    QuerySnapshotEntity,
    SnapshotPayloadEntity,
    SourceCacheEntity,
    SourceEntity,
    SourceSnapshotEntity,
)

UNCLASSIFIED_CATEGORY = "UNCLASSIFIED"


@dataclass(frozen=True, slots=True)
class SourceInfo:
    id: int
    code: str
    cache_ttl_hours: int


@dataclass(frozen=True, slots=True)
class CurrentSnapshotRow:
    source_code: str
    snapshot_id: int
    executed_at: datetime
    expires_at: datetime | None
    data: dict[str, Any]


class SnapshotSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ fuentes
    async def sources(
        self, codes: Collection[str], *, create_missing: bool, default_ttl_hours: int = 720
    ) -> dict[str, SourceInfo]:
        """Fuentes por código. Con create_missing, registra las desconocidas (extractor nuevo
        aún no cargado en el catálogo) para no perder sus fotos; quedan como UNCLASSIFIED."""
        if not codes:
            return {}
        found = await self._select_sources(codes)
        missing = set(codes) - found.keys()
        if missing and create_missing:
            await self._session.execute(
                pg_insert(SourceEntity)
                .values(
                    [
                        {
                            "code": code,
                            "name": code,
                            "category": UNCLASSIFIED_CATEGORY,
                            "cache_ttl_hours": default_ttl_hours,
                        }
                        for code in sorted(missing)
                    ]
                )
                .on_conflict_do_nothing(index_elements=["code"])
            )
            found |= await self._select_sources(missing)
        return found

    async def _select_sources(self, codes: Iterable[str]) -> dict[str, SourceInfo]:
        rows = await self._session.execute(
            select(SourceEntity.id, SourceEntity.code, SourceEntity.cache_ttl_hours).where(
                SourceEntity.code.in_(list(codes))
            )
        )
        return {row.code: SourceInfo(row.id, row.code, row.cache_ttl_hours) for row in rows}

    # ------------------------------------------------------------------ lectura de caché
    async def current_snapshots(
        self, source_ids: Collection[int], cache_key: str
    ) -> list[CurrentSnapshotRow]:
        if not source_ids:
            return []
        stmt = (
            select(
                SourceEntity.code,
                SourceSnapshotEntity.id,
                SourceSnapshotEntity.executed_at,
                SourceCacheEntity.expires_at,
                SnapshotPayloadEntity.data,
            )
            .select_from(SourceCacheEntity)
            .join(SourceEntity, SourceEntity.id == SourceCacheEntity.source_id)
            .join(
                SourceSnapshotEntity,
                SourceSnapshotEntity.id == SourceCacheEntity.last_success_snapshot_id,
            )
            .join(
                SnapshotPayloadEntity,
                SnapshotPayloadEntity.data_hash == SourceSnapshotEntity.data_hash,
            )
            .where(
                SourceCacheEntity.source_id.in_(list(source_ids)),
                SourceCacheEntity.cache_key == cache_key,
            )
        )
        return [CurrentSnapshotRow(*row) for row in await self._session.execute(stmt)]

    # ------------------------------------------------------------------ reservas de refresco
    async def claim_refresh(
        self, source_ids: Collection[int], cache_key: str, lease: timedelta
    ) -> set[int]:
        """Reserva (source_id, cache_key) si está libre o si su reserva venció. Devuelve las
        fuentes reservadas. Es atómico: dos peticiones simultáneas no reservan la misma."""
        if not source_ids:
            return set()
        stmt = pg_insert(SourceCacheEntity).values(
            [
                {"source_id": sid, "cache_key": cache_key, "refreshing_since": func.now()}
                for sid in source_ids
            ]
        )
        expired = func.now() - bindparam("lease", lease, type_=Interval())
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_id", "cache_key"],
            set_={"refreshing_since": func.now(), "updated_at": func.now()},
            where=or_(
                SourceCacheEntity.refreshing_since.is_(None),
                SourceCacheEntity.refreshing_since < expired,
            ),
        ).returning(SourceCacheEntity.source_id)
        return set((await self._session.execute(stmt)).scalars())

    async def refreshing(
        self, source_ids: Collection[int], cache_key: str, lease: timedelta
    ) -> set[int]:
        if not source_ids:
            return set()
        expired = func.now() - bindparam("lease", lease, type_=Interval())
        rows = await self._session.execute(
            select(SourceCacheEntity.source_id).where(
                SourceCacheEntity.source_id.in_(list(source_ids)),
                SourceCacheEntity.cache_key == cache_key,
                SourceCacheEntity.refreshing_since.is_not(None),
                SourceCacheEntity.refreshing_since >= expired,
            )
        )
        return set(rows.scalars())

    async def release_refresh(self, source_ids: Collection[int], cache_key: str) -> None:
        if not source_ids:
            return
        await self._session.execute(
            update(SourceCacheEntity)
            .where(
                SourceCacheEntity.source_id.in_(list(source_ids)),
                SourceCacheEntity.cache_key == cache_key,
            )
            .values(refreshing_since=None, updated_at=func.now())
        )

    # ------------------------------------------------------------------ personas y empresas
    async def upsert_party(self, ref: PartyRef, *, is_subject: bool) -> int:
        """Crea o actualiza una party por su documento.

        - El nombre solo se actualiza cuando la party es el sujeto consultado: los nombres que
          llegan como vínculo (p.ej. "RUIZ AUCCAPIÑA RONALD" en SEACE) no pisan al oficial.
        - tax_id e is_query_subject nunca se pierden una vez conocidos.
        """
        stmt = pg_insert(PartyEntity).values(
            party_type=ref.party_type.value,
            document_type=ref.document_type.value,
            document_number=ref.document_number,
            tax_id=ref.tax_id,
            display_name=ref.display_name or ref.document_number,
            is_query_subject=is_subject,
        )
        excluded = stmt.excluded
        set_: dict[str, Any] = {
            "tax_id": func.coalesce(PartyEntity.tax_id, excluded.tax_id),
            "is_query_subject": or_(PartyEntity.is_query_subject, excluded.is_query_subject),
            "updated_at": func.now(),
        }
        if is_subject and ref.display_name:
            set_["display_name"] = excluded.display_name
        stmt = stmt.on_conflict_do_update(
            index_elements=["document_type", "document_number"], set_=set_
        ).returning(PartyEntity.id)
        return (await self._session.execute(stmt)).scalar_one()

    # ------------------------------------------------------------------ consultas y fotos
    async def insert_query(
        self,
        *,
        query_type: str,
        query_parameter: str,
        party_id: int | None,
        fetch_mode: str,
        served_from: str,
        requested_at: datetime,
        completed_at: datetime,
    ) -> int:
        stmt = (
            pg_insert(QueryEntity)
            .values(
                query_type=query_type,
                query_parameter=query_parameter,
                party_id=party_id,
                fetch_mode=fetch_mode,
                served_from=served_from,
                requested_at=requested_at,
                completed_at=completed_at,
            )
            .returning(QueryEntity.id)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def ensure_payload(self, data_hash: str, data: dict[str, Any], raw: Any | None) -> None:
        """Guarda el contenido si es nuevo. Si ya existía (mismo hash), no se duplica."""
        await self._session.execute(
            pg_insert(SnapshotPayloadEntity)
            .values(data_hash=data_hash, data=data, raw=null() if raw is None else raw)
            .on_conflict_do_nothing(index_elements=["data_hash"])
        )

    async def insert_snapshot(
        self,
        *,
        source_id: int,
        query_id: int,
        party_id: int | None,
        query_parameter: str,
        status: AuditStatus,
        duration_ms: int,
        details: str | None,
        executed_at: datetime,
        data_hash: str | None,
    ) -> int:
        stmt = (
            pg_insert(SourceSnapshotEntity)
            .values(
                source_id=source_id,
                query_id=query_id,
                party_id=party_id,
                query_parameter=query_parameter,
                status=status,
                duration_ms=max(duration_ms, 0),
                details=details,
                executed_at=executed_at,
                data_hash=data_hash,
            )
            .returning(SourceSnapshotEntity.id)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def link_query_snapshots(self, query_id: int, items: Iterable[tuple[int, bool]]) -> None:
        rows = [
            {"query_id": query_id, "snapshot_id": snapshot_id, "from_cache": from_cache}
            for snapshot_id, from_cache in items
        ]
        if rows:
            await self._session.execute(
                pg_insert(QuerySnapshotEntity).values(rows).on_conflict_do_nothing()
            )

    # ------------------------------------------------------------------ puntero de caché
    async def point_cache(
        self,
        *,
        source_id: int,
        cache_key: str,
        party_id: int | None,
        snapshot_id: int,
        success_at: datetime | None,
        expires_at: datetime | None,
    ) -> bool:
        """Registra el último intento y libera la reserva. Si fue exitoso, mueve además el
        puntero de la foto válida, salvo que ya apunte a una foto más reciente (una petición
        lenta que termina tarde no retrocede los datos).

        Devuelve True si esta foto quedó como la vigente."""
        values: dict[str, Any] = {
            "source_id": source_id,
            "cache_key": cache_key,
            "party_id": party_id,
            "last_snapshot_id": snapshot_id,
            "refreshing_since": None,
        }
        if success_at is not None:
            values |= {
                "last_success_snapshot_id": snapshot_id,
                "last_success_at": success_at,
                "expires_at": expires_at,
            }
        stmt = pg_insert(SourceCacheEntity).values(**values)
        excluded = stmt.excluded
        set_: dict[str, Any] = {
            "last_snapshot_id": excluded.last_snapshot_id,
            "party_id": func.coalesce(excluded.party_id, SourceCacheEntity.party_id),
            "refreshing_since": None,
            "updated_at": func.now(),
        }
        if success_at is not None:
            is_newer = or_(
                SourceCacheEntity.last_success_at.is_(None),
                SourceCacheEntity.last_success_at <= excluded.last_success_at,
            )
            for column in ("last_success_snapshot_id", "last_success_at", "expires_at"):
                set_[column] = case(
                    (is_newer, getattr(excluded, column)),
                    else_=getattr(SourceCacheEntity, column),
                )
        current = await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=["source_id", "cache_key"], set_=set_
            ).returning(SourceCacheEntity.last_success_snapshot_id)
        )
        return success_at is not None and current.scalar_one() == snapshot_id

    # ------------------------------------------------------------------ vínculos
    async def upsert_link(
        self,
        *,
        holder_id: int,
        company_id: int,
        link: PartyLink,
        source_id: int,
        snapshot_id: int,
    ) -> int:
        stmt = pg_insert(PartyLinkEntity).values(
            from_party_id=holder_id,
            to_party_id=company_id,
            link_type=link.link_type.value,
            role=link.role,
            share_percentage=link.share_percentage,
            start_date=link.start_date,
            source_id=source_id,
            snapshot_id=snapshot_id,
            is_active=True,
        )
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["from_party_id", "to_party_id", "link_type", "source_id"],
            set_={
                "role": excluded.role,
                "share_percentage": excluded.share_percentage,
                "start_date": excluded.start_date,
                "snapshot_id": excluded.snapshot_id,
                "is_active": True,
                "last_seen_at": func.now(),
            },
        ).returning(PartyLinkEntity.id)
        return (await self._session.execute(stmt)).scalar_one()

    async def deactivate_missing_links(
        self, *, source_id: int, party_id: int, keep_ids: Collection[int]
    ) -> int:
        """Desactiva los vínculos del sujeto que esta fuente ya no reporta. Devuelve cuántos."""
        conditions = [
            PartyLinkEntity.source_id == source_id,
            PartyLinkEntity.is_active.is_(True),
            or_(PartyLinkEntity.from_party_id == party_id, PartyLinkEntity.to_party_id == party_id),
        ]
        if keep_ids:
            conditions.append(PartyLinkEntity.id.not_in(list(keep_ids)))
        result = await self._session.execute(
            update(PartyLinkEntity).where(and_(*conditions)).values(is_active=False)
        )
        return result.rowcount or 0
