from dataclasses import dataclass

from app.domain.models.audit import AuditResult
from app.domain.models.sunarp import SunarpRecord

@dataclass(frozen=True, slots=True)
class SunarpResult:
    oficina: str
    area: str
    partida: str
    record: SunarpRecord | None = None
    audit_entries: tuple[AuditResult, ...] = ()