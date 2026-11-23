from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_database
from app.infrastructure.inbound.dto.response.health_response import HealthResponse
from app.infrastructure.outbound.persistence.database import Database

router = APIRouter()


@router.get(
    "",
    operation_id="get_health",
    summary="Estado del servicio",
    description=(
        "Indica si la API está en línea y si la base de datos responde. Con la base de datos caída "
        "la API sigue atendiendo consultas en vivo, sin guardar resultados."
    ),
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
async def get_health(
    database: Annotated[Database | None, Depends(get_database)],
) -> HealthResponse:
    if database is None:
        return HealthResponse(status="ok", database="disabled")
    if await database.ping():
        return HealthResponse(status="ok", database="up")
    return HealthResponse(status="degraded", database="down")
