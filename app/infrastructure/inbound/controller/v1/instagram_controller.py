import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.port.usecase.get_instagram_use_case import GetInstagramUseCase
from app.core.dependencies import get_instagram_use_case
from app.infrastructure.inbound.docs.responses import INSTAGRAM_RESPONSES
from app.infrastructure.inbound.dto.request.instagram_request import UsernamePathParam
from app.infrastructure.inbound.dto.request.refresh_request import RefreshQuery
from app.infrastructure.inbound.dto.response.instagram_response import InstagramResponse
from app.infrastructure.inbound.mapper import instagram_mapper

logger = logging.getLogger(__name__)

router = APIRouter()

DESCRIPTION = """
Lee un perfil de Instagram por **username**, sin iniciar sesión.

**Cómo usarlo**

| Petición | Qué hace |
|---|---|
| `/instagram/nasa` | Primera vez: va a la web y guarda. Después: responde desde la base de datos |
| `/instagram/@NASA` | Igual que la anterior: ignora `@` y mayúsculas |
| `/instagram/nasa?refresh=true` | Vuelve a la web; si falla, mantiene lo guardado |

No acepta nombres de persona ni la URL completa.

**Qué devuelve:** nombre, descripción, foto, ID de cuenta, verificación, contadores, enlaces, menciones,
Threads y última publicación (solo enlace y texto).

**Cómo leer el resultado** (`audit_entries[].status`)

| Estado | Significado |
|---|---|
| `SUCCESS` | Perfil leído. Si `is_private=true`, solo lo que Instagram muestra a cualquiera |
| `NO_DATA` | No existe, fue eliminado o está restringido |
| `ERROR` | Bloqueo o datos que no se pudieron verificar. Tras un bloqueo, la web se pausa 15 min |

- `null` = no se obtuvo; `[]` = no tiene. Los perfiles guardados antes de un campo nuevo se completan con `refresh=true`.
- Las visitas a la web se espacian 10 s.
- Los enlaces y menciones son indicios: **no prueban identidad** ni se vinculan a un DNI.
"""


@router.get(
    "/{username}",
    operation_id="get_instagram_profile",
    summary="Consultar un perfil de Instagram por username",
    description=DESCRIPTION,
    response_model=InstagramResponse,
    status_code=status.HTTP_200_OK,
    responses=INSTAGRAM_RESPONSES,
)
async def get_instagram_profile(
    request: Request,
    username: UsernamePathParam,
    use_case: Annotated[GetInstagramUseCase, Depends(get_instagram_use_case)],
    refresh: RefreshQuery = False,
) -> InstagramResponse:
    try:
        result = await use_case.execute(instagram_mapper.to_command(username, refresh))
    except Exception as exc:
        logger.exception("Unexpected error fetching Instagram profile %s", username)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching Instagram profile",
        ) from exc
    return instagram_mapper.to_response(result, base_url=str(request.base_url))
