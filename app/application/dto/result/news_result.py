from dataclasses import dataclass

from app.domain.models.audit import AuditResult
from app.domain.models.news import NewsSearch
from app.domain.models.query import ServedFrom, SourceOrigin


@dataclass(frozen=True, slots=True)
class NewsResult:
    query: str
    name: str | None = None
    topic: str | None = None
    search: NewsSearch | None = None
    audit_entries: tuple[AuditResult, ...] = ()
    served_from: ServedFrom = ServedFrom.LIVE
    data_origins: tuple[SourceOrigin, ...] = ()
