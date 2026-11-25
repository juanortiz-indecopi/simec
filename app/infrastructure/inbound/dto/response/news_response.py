from datetime import datetime

from pydantic import ConfigDict, Field

from app.domain.models.query import ServedFrom
from app.infrastructure.inbound.docs.examples import NEWS_EXAMPLE
from app.infrastructure.inbound.dto.response.audit_response import AuditResultResponse
from app.infrastructure.inbound.dto.response.base import ResponseModel
from app.infrastructure.inbound.dto.response.served_from import SERVED_FROM_FIELD


class NewsArticleResponse(ResponseModel):
    title: str = Field(
        description="Título de la noticia, sin el nombre del medio",
        examples=["Indecopi evalúa el mercado de Empresa Demo"],
    )
    url: str = Field(description="Enlace de Google News; redirige al medio")
    article_id: str = Field(description="Identificador de la noticia en Google News")
    outlet: str | None = Field(
        default=None, description="Medio que la publicó; `null` si no se informa", examples=["Medio Demo"]
    )
    outlet_url: str | None = Field(default=None, description="Sitio web del medio")
    published_at: datetime | None = Field(
        default=None, description="Fecha de publicación (ISO 8601, UTC); `null` si no se informa"
    )
    name_in_title: bool | None = Field(
        default=None,
        description="Si `name` aparece en el título; `null` si no se buscó por nombre. No prueba identidad",
    )


class NewsResponse(ResponseModel):
    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [NEWS_EXAMPLE]})

    query: str = Field(
        description="Consulta enviada al buscador: `name` entre comillas, seguido de `topic`",
        examples=['"empresa demo" indecopi'],
    )
    name: str | None = Field(default=None, description="Nombre buscado, en minúsculas; `null` si no se envió")
    topic: str | None = Field(default=None, description="Tema buscado, en minúsculas; `null` si no se envió")
    served_from: ServedFrom = SERVED_FROM_FIELD
    total: int = Field(ge=0, description="Cantidad de noticias devueltas")
    reached_limit: bool = Field(description="`true` si la fuente devolvió su máximo: puede haber más")
    articles: list[NewsArticleResponse] = Field(
        description="Noticias, de la más reciente a la más antigua; `[]` si no hay"
    )
    audit_entries: list[AuditResultResponse] = Field(description="Auditoría de `GOOGLE_NEWS_RSS`")
