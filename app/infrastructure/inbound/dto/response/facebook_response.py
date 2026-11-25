from datetime import date, datetime

from pydantic import ConfigDict, Field

from app.domain.models.facebook import FacebookMediaType, MatchResult
from app.domain.models.query import ServedFrom
from app.infrastructure.inbound.docs.examples import FACEBOOK_EXAMPLE
from app.infrastructure.inbound.dto.response.audit_response import AuditResultResponse
from app.infrastructure.inbound.dto.response.base import ResponseModel
from app.infrastructure.inbound.dto.response.served_from import SERVED_FROM_FIELD


class FacebookLinkResponse(ResponseModel):
    url: str = Field(description="Sitio web o red social publicada en la página")
    platform: str = Field(description="Plataforma según el dominio (`WEB`, `INSTAGRAM`, `WHATSAPP`...)")


class FacebookFieldResponse(ResponseModel):
    kind: str = Field(description="Tipo de dato según Facebook")
    value: str = Field(description="Texto publicado")


class FacebookPostResponse(ResponseModel):
    post_id: str = Field(description="ID de la publicación")
    url: str = Field(description="Enlace a la publicación")
    published_at: datetime = Field(description="Fecha y hora de publicación (UTC)")
    media_type: FacebookMediaType = Field(description="`PHOTO`, `VIDEO`, `OTHER` o `NONE` (solo texto)")
    text: str | None = Field(default=None, description="Texto completo")
    reactions: int | None = Field(default=None, description="Cantidad de reacciones")
    comments: int | None = Field(default=None, description="Cantidad de comentarios (no su contenido)")
    shares: int | None = Field(default=None, description="Veces compartida")


class FacebookPageResponse(ResponseModel):
    key: str = Field(description="Clave consultada (username o ID)")
    page_url: str = Field(description="Enlace a la página")
    account_id: str = Field(description="ID numérico: no cambia aunque cambie el username")
    page_id: str | None = Field(default=None, description="Identificador de página (transparencia)")
    name: str = Field(description="Nombre de la página")
    category: str | None = Field(default=None, description="Rubro declarado")
    description: str | None = Field(default=None, description="Descripción")
    city: str | None = Field(default=None, description="Ciudad")
    address: str | None = Field(default=None, description="Dirección publicada")
    responsible: str | None = Field(
        default=None, description="Organización que figura como responsable de la página"
    )
    is_verified: bool | None = Field(
        default=None, description="Insignia de verificación (también puede ser de pago)"
    )
    followers: int | None = Field(default=None, description="Cantidad de seguidores")
    following: int | None = Field(default=None, description="Cantidad de seguidos")
    talking_about: int | None = Field(default=None, description="Personas hablando de la página")
    rating: str | None = Field(default=None, description="Valoración, si la página la muestra")
    business_hours: str | None = Field(default=None, description="Horario publicado")
    phones: list[str] = Field(default_factory=list, description="Teléfonos publicados")
    emails: list[str] = Field(default_factory=list, description="Correos publicados")
    links: list[FacebookLinkResponse] = Field(default_factory=list, description="Webs y redes publicadas")
    other_info: list[FacebookFieldResponse] = Field(
        default_factory=list, description="Otros datos publicados sin campo propio"
    )
    created_on: date | None = Field(default=None, description="Fecha de creación (transparencia)")
    has_active_ads: bool | None = Field(
        default=None, description="Si tenía anuncios en circulación al consultarla (transparencia)"
    )
    photo_url: str | None = Field(default=None, description="URL pública de la copia de la foto")
    photo_path: str | None = Field(default=None, description="Ruta en el servidor (referencia interna)")
    latest_post: FacebookPostResponse | None = Field(
        default=None, description="Publicación más reciente entre las visibles; podría ser la fijada"
    )
    missing_sections: list[str] = Field(
        default_factory=list, description="Pestañas que no se pudieron leer en esa consulta"
    )


class PageVerificationResponse(ResponseModel):
    ruc: str = Field(description="RUC comparado")
    result: MatchResult = Field(
        description=(
            "`PROBABLE`, `POSSIBLE`, `NO_EVIDENCE` o `NOT_EVALUATED`. Es una sugerencia: la confirma un analista"
        )
    )
    reasons: list[str] = Field(description="Coincidencias encontradas")
    warnings: list[str] = Field(description="Diferencias o motivos por los que no se evaluó")


class FacebookPageQueryResponse(ResponseModel):
    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [FACEBOOK_EXAMPLE]})

    requested_page: str = Field(description="Página consultada, normalizada", examples=["codideep"])
    served_from: ServedFrom = SERVED_FROM_FIELD
    page: FacebookPageResponse | None = Field(
        default=None, description="Datos de la página; `null` si no está disponible o falló"
    )
    verification: PageVerificationResponse | None = Field(
        default=None, description="Comparación con la empresa; `null` si no se envió `ruc`"
    )
    audit_entries: list[AuditResultResponse] = Field(
        description="Auditoría de Facebook y, si se envió `ruc`, de las fuentes de la empresa"
    )
