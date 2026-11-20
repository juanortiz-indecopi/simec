import asyncio
import time
from datetime import datetime, timezone

from app.application.dto.command.get_sunarp_command import GetSunarpCommand
from app.application.dto.result.sunarp_result import SunarpResult
from app.application.port.out.sunarp_port import SunarpPort
from app.application.port.usecase.get_sunarp_use_case import GetSunarpUseCase
from app.application.services.source_runner import DEFAULT_TIMEOUT_S
from app.domain.models.audit import AuditResult, AuditStatus
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
    ) -> None:
        self._sunarp = sunarp
        self._timeout_s = timeout_s

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
        started = time.perf_counter()
        
        try:
            response = await asyncio.wait_for(
                self._sunarp.extract(command.oficina, command.area, command.partida),
                timeout=self._timeout_s
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

            return SunarpResult(
                oficina=command.oficina,
                area=command.area,
                partida=command.partida,
                record=record,
                audit_entries=(audit, *extra_audits),
            )
            
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
            
            return SunarpResult(
                oficina=command.oficina,
                area=command.area,
                partida=command.partida,
                record=None,
                audit_entries=(error_audit,),
            )