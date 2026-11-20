from typing import Any, Final

DESCRIPTION: Final = """
Backend para el monitoreo de mercados y conductas anticompetitivas.

Agrega fuentes públicas peruanas (**SEACE**, **SUNAT**, **RNP**, **SUNARP** y **apis.net.pe**),
normaliza la información de personas naturales y jurídicas, y devuelve un reporte consolidado con
auditoría por fuente.

* Consultas independientes: por **RUC** (empresas), por **DNI** (personas) y por **partida
  registral** (SUNARP).
* Sin base de datos: cada consulta se resuelve en vivo contra las fuentes.
* Los archivos obtenidos (p.ej. PDFs de asientos de SUNARP) se publican en `/files/...`.
* Cada fuente queda auditada con duración, estado y detalle. Una fuente caída no bloquea a las demás.
"""

TAGS_METADATA: Final[list[dict[str, Any]]] = [
    {
        "name": "Companies",
        "description": (
            "Consulta por **RUC** (11 dígitos). Fuentes: apis.net.pe, SEACE, SUNAT y RNP."
        ),
    },
    {
        "name": "Persons",
        "description": (
            "Consulta por **DNI** (8 dígitos). Fuentes: apis.net.pe, SEACE y SUNAT. "
            "El RNP no admite consultas por DNI."
        ),
    },
    {
        "name": "SUNARP",
        "description": (
            "Consulta por **partida registral** (oficina, área y número). Fuentes: SPRL (asientos de "
            "la partida) y Síguelo Plus (PDF del asiento de inscripción de cada título). Lo resuelve "
            "un agente LLM que controla un navegador vía MCP de Playwright: puede tardar varios minutos."
        ),
    },
]

API_METADATA: Final[dict[str, Any]] = {
    "title": "SIMEC Backend",
    "version": "0.1.0",
    "summary": "API de monitoreo de proveedores y mercados",
    "description": DESCRIPTION,
    "openapi_tags": TAGS_METADATA,
}
