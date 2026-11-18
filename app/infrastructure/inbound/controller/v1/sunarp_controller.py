import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

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
        "Consulta en tiempo real la SPRL de SUNARP resolviendo los controles "
        "de seguridad para extraer los títulos (asientos) de una partida registral específica."
    ),
    response_model=SunarpResponse,
    status_code=status.HTTP_200_OK,
)
async def get_sunarp_partida(
    oficina: OficinaQuery,
    area: AreaQuery,
    partida: PartidaQuery,
    use_case: Annotated[GetSunarpUseCase, Depends(get_sunarp_use_case)],
) -> SunarpResponse:
    try:
        command = sunarp_mapper.to_command(oficina=oficina, area=area, partida=partida)
        result = await use_case.execute(command)
    except Exception as exc:
        logger.exception("Unexpected error fetching SUNARP for partida %s", partida)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching SUNARP data",
        ) from exc
        
    return sunarp_mapper.to_response(result)