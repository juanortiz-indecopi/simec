from datetime import datetime

from pydantic import Field

from app.domain.models.audit import AuditStatus
from app.infrastructure.inbound.dto.response.base import ResponseModel


class AuditResultResponse(ResponseModel):
    source_name: str = Field(description="Fuente que generó esta entrada", examples=["SEACE_PENTAHO_CDA_RUC"])
    query_parameter: str = Field(description="Parámetro enviado a la fuente", examples=["20607524476"])
    duration_ms: int = Field(
        description="Duración de la consulta en milisegundos (0 si se sirvió desde la base de datos)",
        examples=[779],
    )
    status: AuditStatus = Field(
        description="`SUCCESS` si la fuente devolvió datos, `NO_DATA` si no hay información y `ERROR` si falló"
    )
    details: str | None = Field(description="Detalle del fallo o de los datos parciales, si aplica")
    executed_at_utc: datetime = Field(description="Fecha y hora de la consulta a la fuente (UTC)")
    from_cache: bool = Field(
        default=False,
        description=(
            "`true` si los datos de esta fuente se sirvieron desde la base de datos (consulta previa) "
            "en lugar de consultarse en la web en esta petición"
        ),
    )
    data_fetched_at: datetime | None = Field(
        default=None,
        description="Cuándo se obtuvieron de la fuente los datos mostrados (UTC); `null` si no hay datos",
    )
    is_stale: bool = Field(
        default=False,
        description=(
            "`true` si los datos guardados superaron su vigencia (p.ej. 7 días en SUNAT): conviene "
            "ofrecer al usuario actualizarlos con `refresh=true`. Nunca se re-consulta automáticamente"
        ),
    )
