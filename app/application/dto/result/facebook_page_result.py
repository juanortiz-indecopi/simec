from dataclasses import dataclass

from app.domain.models.audit import AuditResult
from app.domain.models.facebook import FacebookPage, PageVerification
from app.domain.models.query import ServedFrom, SourceOrigin


@dataclass(frozen=True, slots=True)
class FacebookPageResult:
    requested_page: str
    page: FacebookPage | None = None
    verification: PageVerification | None = None
    audit_entries: tuple[AuditResult, ...] = ()
    served_from: ServedFrom = ServedFrom.LIVE
    data_origins: tuple[SourceOrigin, ...] = ()
