from pydantic import Field

from app.infrastructure.inbound.dto.response.audit_response import AuditResultResponse
from app.infrastructure.inbound.dto.response.base import ResponseModel


class SunarpSeatResponse(ResponseModel):
    year: str = Field(description="Año del título/asiento", examples=["2015"])
    number: str = Field(description="Número correlativo del título", examples=["00076288"])
    original_text: str = Field(description="Texto original extraído", examples=["Titulo: 2015 - 00076288"])


class SunarpRecordResponse(ResponseModel):
    partida: str = Field(description="Número de partida registral", examples=["11156404"])
    seats: list[SunarpSeatResponse] = Field(description="Lista de asientos registrales extraídos de la partida")


class SunarpResponse(ResponseModel):
    oficina: str = Field(description="Oficina registral consultada", examples=["CUSCO"])
    area: str = Field(description="Área registral consultada", examples=["Personas Jurídicas"])
    partida: str = Field(description="Número de partida consultado", examples=["11156404"])
    record: SunarpRecordResponse | None = Field(
        default=None, 
        description="Datos de la partida si la extracción fue exitosa"
    )
    audit_entries: list[AuditResultResponse] = Field(
        description="Registro de auditoría con la latencia y estado de la extracción en SPRL"
    )