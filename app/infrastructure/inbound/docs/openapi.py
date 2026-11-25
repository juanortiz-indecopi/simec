from typing import Any, Final

DESCRIPTION: Final = """
Backend para el monitoreo de mercados y conductas anticompetitivas.

Agrega fuentes públicas peruanas (**SEACE**, **SUNAT**, **RNP**, **SUNARP** y **apis.net.pe**) y
redes sociales (**Instagram** y páginas de **Facebook**) y noticias (**Google News**),
normaliza la información de personas naturales y jurídicas, y devuelve un reporte consolidado con
auditoría por fuente.

* Consultas independientes: por **RUC** (empresas), por **DNI** (personas), por **partida
  registral** (SUNARP), por **username** (Instagram), por **página** (Facebook) y por
  **nombre o tema** (noticias).
* Datos guardados en PostgreSQL: la primera consulta se resuelve en vivo contra las fuentes y se
  guarda; las siguientes se responden desde la base de datos. Con `refresh=true` se actualizan
  desde la web sin perder lo guardado si una fuente falla. Cada consulta queda registrada con su
  fecha y las fuentes usadas (trazabilidad).
* `served_from` (`DATABASE`, `LIVE`, `MIXED`) y `audit_entries[].from_cache` / `data_fetched_at` /
  `is_stale` indican el origen y la antigüedad de cada dato.
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
    {
        "name": "Facebook",
        "description": "Consulta de **páginas de empresa**, con comparación opcional contra un RUC.",
    },
    {
        "name": "Instagram",
        "description": "Consulta de un perfil por **username**, sin login.",
    },
    {
        "name": "News",
        "description": "Búsqueda de noticias por **nombre** o **tema** en Google News.",
    },
    {
        "name": "Health",
        "description": "Estado de la API y de la conexión a PostgreSQL.",
    },
]

API_METADATA: Final[dict[str, Any]] = {
    "title": "SIMEC Backend",
    "version": "0.1.0",
    "summary": "API de monitoreo de proveedores y mercados",
    "description": DESCRIPTION,
    "openapi_tags": TAGS_METADATA,
}
