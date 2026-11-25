import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.port.usecase.get_facebook_page_use_case import GetFacebookPageUseCase
from app.core.dependencies import get_facebook_page_use_case
from app.infrastructure.inbound.docs.responses import FACEBOOK_RESPONSES
from app.infrastructure.inbound.dto.request.facebook_request import FacebookPageQuery, OptionalRucQuery
from app.infrastructure.inbound.dto.request.refresh_request import RefreshQuery
from app.infrastructure.inbound.dto.response.facebook_response import FacebookPageQueryResponse
from app.infrastructure.inbound.mapper import facebook_mapper

logger = logging.getLogger(__name__)

router = APIRouter()

DESCRIPTION = """
Lee una **página de empresa** de Facebook, sin iniciar sesión, y opcionalmente la compara con un RUC.
Los perfiles personales no se leen.

**Cómo usarlo**

| Parámetro | Obligatorio | Valor |
|---|---|---|
| `page` | Sí | Username, ID o URL de la página. Si la URL lleva `&`, envíela codificada |
| `ruc` | No | RUC 20 con el que se compara. Los demás responden `NOT_EVALUATED` |
| `refresh` | No | `true`: vuelve a Facebook (no a SUNAT); si falla, mantiene lo guardado |

`page` no acepta razones sociales, RUC, grupos ni enlaces a publicaciones. La primera consulta tarda unos
10 a 15 s; las siguientes salen de la base de datos.

**Qué devuelve:** nombre, rubro, descripción, dirección, teléfonos, correos, webs y redes, responsable,
seguidores, valoración, fecha de creación, anuncios activos, foto y última publicación visible (texto y
cantidad de reacciones, comentarios y compartidos). Cada dato aparece solo si la página lo publica.

**Verificación** (`verification.result`): es una sugerencia con motivos; **la confirma un analista** y nunca
vincula la página al RUC.

| Resultado | Significado |
|---|---|
| `PROBABLE` | Señales fuertes: RUC, responsable, dirección, o nombre distintivo y ciudad |
| `POSSIBLE` | Señales parciales o alguna contradicción |
| `NO_EVIDENCE` | Sin coincidencias suficientes. No demuestra que sea de otra empresa |
| `NOT_EVALUATED` | Faltan datos o no es RUC 20 |

**Resultados de prueba** (24/11/2026; pueden cambiar)

| `page` | `ruc` | Resultado |
|---|---|---|
| `codideep` | `20603687478` | `PROBABLE`: nombre, EIRL, dominio, ciudad y rubro |
| `InternetApurimacAmericaServices` | `20601590175` | `PROBABLE`: calle, número, ciudad y rubro |
| `inkafarmaperu` | `20331066703` | `PROBABLE`: responsable |
| `bembos` | `20101087647` | `PROBABLE`: responsable, nombre, dominio y rubro |
| `falabellacom.pe` | `20100128056` | `POSSIBLE`: una palabra distintiva |
| `codideep` | `20601590175` | `NO_EVIDENCE`: RUC de otra empresa |

**Estados** (`audit_entries[].status`): `NO_DATA` = página no disponible, restringida o perfil personal (**no**
significa que la empresa no tenga Facebook); `ERROR` = bloqueo o datos no verificables. Tras un bloqueo, la
web se pausa 15 min. `served_from=MIXED` es normal: Facebook de la web y SUNAT de la base de datos, o al revés.
"""


@router.get(
    "/pages",
    operation_id="get_facebook_page",
    summary="Consultar una página de Facebook y compararla con una empresa",
    description=DESCRIPTION,
    response_model=FacebookPageQueryResponse,
    status_code=status.HTTP_200_OK,
    responses=FACEBOOK_RESPONSES,
)
async def get_facebook_page(
    request: Request,
    page: FacebookPageQuery,
    use_case: Annotated[GetFacebookPageUseCase, Depends(get_facebook_page_use_case)],
    ruc: OptionalRucQuery = None,
    refresh: RefreshQuery = False,
) -> FacebookPageQueryResponse:
    try:
        result = await use_case.execute(facebook_mapper.to_command(page, ruc, refresh))
    except Exception as exc:
        logger.exception("Unexpected error fetching Facebook page %s", page)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching Facebook page",
        ) from exc
    return facebook_mapper.to_response(result, base_url=str(request.base_url))
