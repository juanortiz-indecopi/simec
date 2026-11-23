import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.infrastructure.inbound.docs.responses import COMPANY_RESPONSES
from app.infrastructure.inbound.dto.request.company_request import RucPathParam
from app.infrastructure.inbound.dto.request.refresh_request import RefreshQuery
from app.infrastructure.inbound.dto.response.company_response import CompanyResponse
from app.infrastructure.inbound.mapper import company_mapper
from app.application.port.usecase.get_company_use_case import GetCompanyUseCase
from app.core.dependencies import get_company_use_case

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/{ruc}",
    operation_id="get_company",
    summary="Consultar una empresa por RUC",
    description=(
        "Consulta en paralelo todas las fuentes disponibles para un RUC y devuelve un reporte "
        "consolidado.\n\n"
        "**Datos guardados:** la primera consulta de un RUC va a la web y se guarda; las siguientes "
        "se responden desde la base de datos al instante. Con `refresh=true` se vuelve a consultar "
        "la web y, si una fuente falla, se mantienen sus datos guardados. `served_from` y "
        "`audit_entries[].from_cache` indican de dónde salió cada dato.\n\n"
        "- **apis.net.pe:** datos tributarios básicos y domicilio fiscal.\n"
        "- **SEACE:** vigencias en el RNP, accionistas y historial de adjudicaciones.\n"
        "- **SUNAT:** ficha RUC, representantes legales y establecimientos anexos.\n"
        "- **RNP:** inscripciones por capítulo (requiere un solucionador de CAPTCHA configurado).\n\n"
        "Una fuente caída o lenta no bloquea a las demás: su resultado queda en `audit_entries` "
        "con estado `ERROR` o `NO_DATA`, y el resto se devuelve igual."
    ),
    response_model=CompanyResponse,
    status_code=status.HTTP_200_OK,
    responses=COMPANY_RESPONSES,
)
async def get_company(
    ruc: RucPathParam,
    use_case: Annotated[GetCompanyUseCase, Depends(get_company_use_case)],
    refresh: RefreshQuery = False,
) -> CompanyResponse:
    try:
        result = await use_case.execute(company_mapper.to_command(ruc, refresh))
    except Exception as exc:
        logger.exception("Unexpected error fetching company %s", ruc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching company",
        ) from exc
    return company_mapper.to_response(result)
