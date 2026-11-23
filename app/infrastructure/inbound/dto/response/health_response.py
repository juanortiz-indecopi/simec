from typing import Literal

from pydantic import Field

from app.infrastructure.inbound.dto.response.base import ResponseModel


class HealthResponse(ResponseModel):
    status: Literal["ok", "degraded"] = Field(
        description="`degraded` si la base de datos está configurada pero no responde."
    )
    database: Literal["up", "down", "disabled"] = Field(
        description="`disabled` si DATABASE_URL no está configurada (modo puente, sin persistencia)."
    )
