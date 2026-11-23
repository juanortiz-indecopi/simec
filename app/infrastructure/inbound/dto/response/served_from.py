from pydantic import Field

from app.domain.models.query import ServedFrom

SERVED_FROM_FIELD = Field(
    default=ServedFrom.LIVE,
    description=(
        "Origen de la respuesta: `DATABASE` (todo desde datos guardados), `LIVE` (todo consultado "
        "en la web en esta petición) o `MIXED` (parte y parte). El detalle por fuente está en "
        "`audit_entries[].from_cache`"
    ),
    examples=["DATABASE"],
)
