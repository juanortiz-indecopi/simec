from typing import Any, Final

from fastapi import status

from app.infrastructure.inbound.dto.response.error_response import ErrorResponse

COMPANY_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    status.HTTP_200_OK: {
        "description": "Reporte generado. Revise `audit_entries` para ver el estado de cada fuente."
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "`ruc` no tiene exactamente 11 dígitos."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "Error inesperado al generar el reporte.",
    },
}

SUNARP_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    status.HTTP_200_OK: {
        "description": (
            "Consulta procesada. Revise `audit_entries` (`SUNARP_SPRL` y `SUNARP_SIGUELO`) y el "
            "`document_status` de cada asiento para ver qué PDFs se obtuvieron."
        )
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "description": "`oficina`, `area` o `partida` faltan o tienen un formato inválido."
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "Error inesperado al consultar SUNARP.",
    },
}

FACEBOOK_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    status.HTTP_200_OK: {
        "description": "Consulta procesada. Revise `audit_entries` para ver el estado de cada fuente."
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "`page` o `ruc` tienen un formato inválido."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "Error inesperado al consultar Facebook.",
    },
}

INSTAGRAM_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    status.HTTP_200_OK: {
        "description": "Consulta procesada. Revise `audit_entries` para ver el estado de la fuente."
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "`username` tiene un formato inválido."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "Error inesperado al consultar Instagram.",
    },
}

PERSON_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    status.HTTP_200_OK: {
        "description": "Reporte generado. Revise `audit_entries` para ver el estado de cada fuente."
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "`dni` no tiene exactamente 8 dígitos."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "Error inesperado al generar el reporte.",
    },
}
