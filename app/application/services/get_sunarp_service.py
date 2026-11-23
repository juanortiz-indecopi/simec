import asyncio
import time
from datetime import datetime, timezone

from app.application.dto.command.get_sunarp_command import GetSunarpCommand
from app.application.dto.result.sunarp_result import SunarpResult
from app.application.port.out.snapshot_repository_port import (
    QueryOutcome,
    SnapshotRepositoryPort,
    SourceExecution,
)
from app.application.port.out.sunarp_port import SunarpPort
from app.application.port.usecase.get_sunarp_use_case import GetSunarpUseCase
from app.application.services.cached_source_runner import (
    WAIT_MARGIN_S,
    cached_audit,
    with_fallback_note,
)
from app.application.services.source_cache import SourceCache, lease_for
from app.application.services.source_runner import DEFAULT_TIMEOUT_S
from app.domain.models.audit import AuditResult, AuditStatus
from app.domain.models.query import (
    FetchMode,
    QueryType,
    SourceOrigin,
    StoredSnapshot,
    served_from,
)
from app.domain.models.sunarp import (
    SunarpDocumentStatus,
    SunarpRecord,
    SunarpSeat,
    SunarpSeatDocument,
)


class GetSunarpService(GetSunarpUseCase):
    def __init__(
        self,
        sunarp: SunarpPort,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        snapshots: SnapshotRepositoryPort | None = None,
    ) -> None:
        self._sunarp = sunarp
        self._timeout_s = timeout_s
        self._cache = SourceCache(snapshots)

    @staticmethod
    def _to_seat(s: dict) -> SunarpSeat:
        status = s.get("document_status")
        return SunarpSeat(
            year=s["year"],
            number=s["number"],
            original_text=s["original_text"],
            documents=tuple(
                SunarpSeatDocument(
                    partida=d["partida"],
                    file_path=d["file_path"],
                    size_bytes=d["size_bytes"],
                )
                for d in s.get("documents", ())
            ),
            document_status=SunarpDocumentStatus(status) if status else None,
            document_detail=s.get("document_detail"),
        )

    async def execute(self, command: GetSunarpCommand) -> SunarpResult:
        requested_at = datetime.now(timezone.utc)
        source = self._sunarp.source_name
        key = command.cache_key
        parameter = f"{command.oficina} | {command.area} | {command.partida}"
        lease = lease_for(self._timeout_s)

        stored = (await self._cache.lookup([source], key)).get(source)

        # Partida ya guardada y sin pedido de actualización: se responde desde la BD.
        if stored is not None and not command.refresh:
            return await self._from_database(command, requested_at, stored, parameter)

        if source not in await self._cache.claim([source], key, lease):
            # Otra petición ya está consultando esta partida: se espera y se usa su resultado.
            await self._cache.wait_for_others([source], key, lease, self._timeout_s + WAIT_MARGIN_S)
            fresh = (await self._cache.lookup([source], key)).get(source)
            if fresh is not None and (stored is None or fresh.snapshot_id != stored.snapshot_id):
                return await self._from_database(command, requested_at, fresh, parameter)

        try:
            record, audits = await self._extract_live(command)
        except BaseException:
            await asyncio.shield(self._cache.release([source], key))
            raise

        executions = tuple(
            SourceExecution(
                audit,
                record if record is not None and audit.status is AuditStatus.SUCCESS else None,
            )
            for audit in audits
        )
        reused: tuple[int, ...] = ()
        if record is not None:
            origin = SourceOrigin(source, False, audits[0].executed_at_utc)
        elif stored is not None:
            # La actualización falló: se muestran los datos guardados, avisando del error.
            record = stored.data_as(SunarpRecord)
            audits = (with_fallback_note(audits[0], stored), *audits[1:])
            origin = SourceOrigin(
                source, True, stored.executed_at, stored.is_stale(datetime.now(timezone.utc))
            )
            reused = (stored.snapshot_id,)
        else:
            origin = SourceOrigin(source, False, None)

        result = SunarpResult(
            oficina=command.oficina,
            area=command.area,
            partida=command.partida,
            record=record,
            audit_entries=audits,
            served_from=served_from((origin,)),
            data_origins=(origin,),
        )
        await self._save(command, requested_at, result, executions, reused)
        return result

    async def _from_database(
        self,
        command: GetSunarpCommand,
        requested_at: datetime,
        snapshot: StoredSnapshot,
        parameter: str,
    ) -> SunarpResult:
        origin = SourceOrigin(
            snapshot.source_name,
            True,
            snapshot.executed_at,
            snapshot.is_stale(datetime.now(timezone.utc)),
        )
        result = SunarpResult(
            oficina=command.oficina,
            area=command.area,
            partida=command.partida,
            record=snapshot.data_as(SunarpRecord),
            audit_entries=(cached_audit(snapshot, parameter),),
            served_from=served_from((origin,)),
            data_origins=(origin,),
        )
        await self._save(command, requested_at, result, (), (snapshot.snapshot_id,))
        return result

    async def _save(
        self,
        command: GetSunarpCommand,
        requested_at: datetime,
        result: SunarpResult,
        executions: tuple[SourceExecution, ...],
        reused: tuple[int, ...],
    ) -> None:
        await self._cache.save(
            QueryOutcome(
                query_type=QueryType.SUNARP_PARTIDA,
                query_parameter=f"{command.oficina}|{command.area}|{command.partida}",
                cache_key=command.cache_key,
                fetch_mode=FetchMode.REFRESH if command.refresh else FetchMode.CACHE,
                served_from=result.served_from,
                requested_at=requested_at,
                completed_at=datetime.now(timezone.utc),
                executions=executions,
                reused_snapshot_ids=reused,
            )
        )

    async def _extract_live(
        self, command: GetSunarpCommand
    ) -> tuple[SunarpRecord | None, tuple[AuditResult, ...]]:
        """Consulta SUNARP en la web (SPRL + Síguelo Plus). Nunca lanza: los fallos quedan en
        la auditoría. Devuelve el registro (o None) y las auditorías, la de SPRL primero."""
        started = time.perf_counter()

        try:
            response = await asyncio.wait_for(
                self._sunarp.extract(command.oficina, command.area, command.partida),
                timeout=self._timeout_s,
            )

            audit = response.get("audit")
            data = response.get("data", {})

            if not isinstance(audit, AuditResult):
                raise ValueError("Extractor response lacks a valid 'audit'")

            record = None
            if data and "seats" in data and data["seats"]:
                seats_tuple = tuple(self._to_seat(s) for s in data["seats"])
                record = SunarpRecord(partida=command.partida, seats=seats_tuple)

            extra_audits = tuple(
                a for a in response.get("additional_audits", ()) if isinstance(a, AuditResult)
            )
            return record, (audit, *extra_audits)

        except Exception as exc:
            details = (
                f"Timed out after {self._timeout_s:g}s"
                if isinstance(exc, TimeoutError)
                else f"{type(exc).__name__}: {exc}"
            )
            error_audit = AuditResult(
                source_name=self._sunarp.source_name,
                query_parameter=f"{command.oficina} | {command.area} | {command.partida}",
                duration_ms=int((time.perf_counter() - started) * 1000),
                status=AuditStatus.ERROR,
                details=details,
                executed_at_utc=datetime.now(timezone.utc),
            )
            return None, (error_audit,)
