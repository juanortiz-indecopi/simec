from datetime import date

from pydantic import ConfigDict, Field

from app.domain.models.instagram import InstagramMediaType
from app.domain.models.query import ServedFrom
from app.infrastructure.inbound.docs.examples import INSTAGRAM_EXAMPLE
from app.infrastructure.inbound.dto.response.audit_response import AuditResultResponse
from app.infrastructure.inbound.dto.response.base import ResponseModel
from app.infrastructure.inbound.dto.response.served_from import SERVED_FROM_FIELD


class InstagramLinkResponse(ResponseModel):
    url: str = Field(description="Enlace declarado en el perfil, sin parámetros de rastreo")
    platform: str = Field(
        description=(
            "Plataforma según el dominio: `FACEBOOK`, `INSTAGRAM`, `THREADS`, `LINKEDIN`, `TIKTOK`, "
            "`YOUTUBE`, `X`, `WHATSAPP`, `TELEGRAM`, `LINK_AGGREGATOR` (Linktree y similares) o `WEB`"
        ),
        examples=["WEB"],
    )
    title: str | None = Field(default=None, description="Título que le puso el usuario")


class InstagramPostResponse(ResponseModel):
    url: str = Field(description="Enlace a la publicación")
    media_type: InstagramMediaType = Field(description="`PHOTO`, `VIDEO`, `CAROUSEL` u `OTHER`")
    published_on: date | None = Field(default=None, description="Día de publicación según Instagram")
    caption: str | None = Field(default=None, description="Texto; `null` si no tiene")


class InstagramProfileResponse(ResponseModel):
    username: str = Field(description="Nombre de usuario", examples=["nasa"])
    full_name: str | None = Field(default=None, description="Nombre visible; `null` si no tiene")
    biography: str | None = Field(default=None, description="Descripción; `null` si no tiene")
    is_private: bool = Field(
        description="`true` si la cuenta es privada: solo se devuelve lo que Instagram muestra a cualquiera"
    )
    profile_url: str = Field(description="Enlace al perfil en Instagram")
    photo_url: str | None = Field(
        default=None, description="URL pública de la copia local de la foto; `null` si no se obtuvo"
    )
    photo_path: str | None = Field(
        default=None, description="Ruta de la foto en el servidor (referencia interna)"
    )
    account_id: str | None = Field(
        default=None, description="ID numérico de la cuenta: no cambia aunque cambie el username"
    )
    is_verified: bool | None = Field(
        default=None, description="Insignia de verificación (también puede ser de pago)"
    )
    followers: int | None = Field(default=None, description="Cantidad de seguidores")
    following: int | None = Field(default=None, description="Cantidad de cuentas seguidas")
    posts_count: int | None = Field(
        default=None, description="Cantidad de publicaciones; `null` si Instagram solo la muestra abreviada"
    )
    links: list[InstagramLinkResponse] | None = Field(
        default=None,
        description=(
            "Enlaces declarados por el usuario: indicios, no vínculos confirmados. `[]` si no tiene; "
            "`null` si no se obtuvo (use `refresh=true` en perfiles guardados antes de este campo)"
        ),
    )
    mentions: list[str] | None = Field(
        default=None, description="Cuentas mencionadas en la descripción (sin `@`); `[]` si no hay"
    )
    threads_username: str | None = Field(default=None, description="Usuario de Threads, si lo muestra")
    latest_post: InstagramPostResponse | None = Field(
        default=None,
        description="Publicación propia más reciente entre las visibles; `null` si no hay o no se puede asegurar",
    )
    latest_photo: InstagramPostResponse | None = Field(
        default=None, description="Foto individual más reciente entre las visibles; no incluye carruseles"
    )


class InstagramResponse(ResponseModel):
    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [INSTAGRAM_EXAMPLE]})

    username: str = Field(description="Nombre de usuario consultado", examples=["nasa"])
    served_from: ServedFrom = SERVED_FROM_FIELD
    profile: InstagramProfileResponse | None = Field(
        default=None, description="Datos del perfil; `null` si no está disponible o la consulta falló"
    )
    audit_entries: list[AuditResultResponse] = Field(description="Auditoría de `INSTAGRAM_PROFILE`")
