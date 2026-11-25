from dataclasses import dataclass

from app.domain.models.audit import AuditResult
from app.domain.models.instagram import InstagramProfile
from app.domain.models.query import ServedFrom, SourceOrigin


@dataclass(frozen=True, slots=True)
class InstagramResult:
    username: str
    profile: InstagramProfile | None = None
    audit_entries: tuple[AuditResult, ...] = ()
    served_from: ServedFrom = ServedFrom.LIVE
    data_origins: tuple[SourceOrigin, ...] = ()
