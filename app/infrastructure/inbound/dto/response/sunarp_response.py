from pydantic import ConfigDict, Field

from app.domain.models.query import ServedFrom
from app.domain.models.sunarp import SunarpDocumentStatus
from app.infrastructure.inbound.docs.examples import SUNARP_EXAMPLE
from app.infrastructure.inbound.dto.response.served_from import SERVED_FROM_FIELD
from app.infrastructure.inbound.dto.response.audit_response import AuditResultResponse
from app.infrastructure.inbound.dto.response.base import ResponseModel


class SunarpSeatDocumentResponse(ResponseModel):
    partida: str = Field(description="Partida vinculada al asiento de inscripción", examples=["11156404"])
    url: str | None = Field(
        default=None,
        description="URL pública del PDF para abrirlo o descargarlo desde el front",
        examples=["http://localhost:8000/files/sunarp/CUSCO_11156404/titulo_2015-00076288_partida_11156404.pdf"],
    )
    file_path: str = Field(
        description="Ruta del PDF en el servidor (referencia interna)",
        examples=["files/sunarp/CUSCO_11156404/titulo_2015-00076288_partida_11156404.pdf"],
    )
    size_bytes: int = Field(description="Tamaño del PDF en bytes", examples=[346200])


class SunarpSeatResponse(ResponseModel):
    year: str = Field(description="Año del título/asiento", examples=["2015"])
    number: str = Field(description="Número correlativo del título", examples=["00076288"])
    original_text: str = Field(description="Texto original extraído", examples=["Titulo: 2015 - 00076288"])
    documents: list[SunarpSeatDocumentResponse] = Field(
        default_factory=list,
        description="PDFs del asiento de inscripción descargados desde Síguelo Plus (uno por partida)",
    )
    document_status: SunarpDocumentStatus | None = Field(
        default=None,
        description=(
            "Resultado de la descarga en Síguelo Plus para este título: `DOWNLOADED`, `NOT_FOUND`, "
            "`OFFICE_NOT_AVAILABLE` (consultar manualmente), `YEAR_NOT_AVAILABLE`, "
            "`NO_INSCRIPTION_SEAT` o `ERROR`"
        ),
        examples=["DOWNLOADED"],
    )
    document_detail: str | None = Field(
        default=None, description="Detalle del resultado o motivo de la falla en Síguelo Plus"
    )


class SunarpRecordResponse(ResponseModel):
    partida: str = Field(description="Número de partida registral", examples=["11156404"])
    seats: list[SunarpSeatResponse] = Field(description="Lista de asientos registrales extraídos de la partida")


class SunarpResponse(ResponseModel):
    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [SUNARP_EXAMPLE]})

    oficina: str = Field(description="Oficina registral consultada", examples=["CUSCO"])
    area: str = Field(description="Área registral consultada", examples=["Personas Juridicas"])
    partida: str = Field(description="Número de partida consultado", examples=["11156404"])
    served_from: ServedFrom = SERVED_FROM_FIELD
    record: SunarpRecordResponse | None = Field(
        default=None,
        description="Datos de la partida si la extracción fue exitosa"
    )
    audit_entries: list[AuditResultResponse] = Field(
        description="Auditoría por fuente: `SUNARP_SPRL` (asientos) y `SUNARP_SIGUELO` (PDFs)"
    )
