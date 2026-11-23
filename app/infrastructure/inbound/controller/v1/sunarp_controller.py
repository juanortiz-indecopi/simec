import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.infrastructure.inbound.docs.responses import SUNARP_RESPONSES
from app.infrastructure.inbound.dto.request.refresh_request import RefreshQuery
from app.infrastructure.inbound.dto.request.sunarp_request import AreaQuery, OficinaQuery, PartidaQuery
from app.infrastructure.inbound.dto.response.sunarp_response import SunarpResponse
from app.infrastructure.inbound.mapper import sunarp_mapper
from app.application.port.usecase.get_sunarp_use_case import GetSunarpUseCase
from app.core.dependencies import get_sunarp_use_case

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/partidas",
    operation_id="get_sunarp_partida",
    summary="Consultar asientos de una partida en SUNARP",
    description=(
        "Consulta una partida registral y descarga el asiento de inscripción de cada título.\n\n"
        "**Datos guardados:** la primera consulta de una partida va a la web (varios minutos) y se "
        "guarda; las siguientes se responden desde la base de datos al instante. Use `refresh=true` "
        "solo para obtener asientos nuevos: vuelve a ejecutar toda la consulta en vivo. Si falla, se "
        "mantienen los asientos guardados. Si otra petición ya está consultando la misma partida, "
        "esta espera su resultado en lugar de repetir el proceso.\n\n"
        "- **SPRL:** inicia sesión, resuelve el CAPTCHA y extrae los títulos (año y número) de la "
        "Lista de Asientos de la partida.\n"
        "- **Síguelo Plus:** por cada título busca su seguimiento y descarga el PDF del asiento de "
        "inscripción (uno por partida vinculada). Cada PDF se publica en `documents[].url`.\n\n"
        "La navegación la realiza un agente LLM sobre un navegador real (MCP de Playwright), por lo que "
        "la consulta puede tardar **varios minutos** (unos 7 min en SPRL más 2 a 5 min por título). "
        "Configure un timeout de cliente acorde.\n\n"
        "Cada título informa su resultado en `document_status`: `DOWNLOADED`, `NOT_FOUND`, "
        "`OFFICE_NOT_AVAILABLE` (la oficina no existe en Síguelo Plus; consultar manualmente), "
        "`YEAR_NOT_AVAILABLE`, `NO_INSCRIPTION_SEAT` o `ERROR`. Una falla en Síguelo Plus no anula los "
        "asientos obtenidos en SPRL: queda registrada en `audit_entries` con la fuente `SUNARP_SIGUELO`."
    ),
    response_model=SunarpResponse,
    status_code=status.HTTP_200_OK,
    responses=SUNARP_RESPONSES,
)
async def get_sunarp_partida(
    request: Request,
    oficina: OficinaQuery,
    area: AreaQuery,
    partida: PartidaQuery,
    use_case: Annotated[GetSunarpUseCase, Depends(get_sunarp_use_case)],
    refresh: RefreshQuery = False,
) -> SunarpResponse:
    try:
        command = sunarp_mapper.to_command(oficina=oficina, area=area, partida=partida, refresh=refresh)
        result = await use_case.execute(command)
    except Exception as exc:
        logger.exception("Unexpected error fetching SUNARP for partida %s", partida)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching SUNARP data",
        ) from exc

    return sunarp_mapper.to_response(result, base_url=str(request.base_url))
