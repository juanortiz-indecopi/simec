from app.domain.models.audit import AuditResult, AuditStatus
from app.domain.models.query import SourceOrigin
from app.infrastructure.inbound.dto.response.audit_response import AuditResultResponse


def to_audit_responses(
    audits: tuple[AuditResult, ...], origins: tuple[SourceOrigin, ...]
) -> list[AuditResultResponse]:
    """Une cada auditoría con el origen de sus datos (BD o web) para la respuesta HTTP.

    Una auditoría sin origen propio (p.ej. SUNARP_SIGUELO, que complementa a SUNARP_SPRL) se
    informa como consulta en vivo.
    """
    by_source = {origin.source_name: origin for origin in origins}
    responses = []
    for audit in audits:
        origin = by_source.get(audit.source_name)
        if origin is not None:
            extra = {
                "from_cache": origin.from_cache,
                "data_fetched_at": origin.data_fetched_at,
                "is_stale": origin.is_stale,
            }
        else:
            extra = {
                "data_fetched_at": (
                    audit.executed_at_utc if audit.status is AuditStatus.SUCCESS else None
                )
            }
        responses.append(AuditResultResponse.model_validate(audit).model_copy(update=extra))
    return responses
