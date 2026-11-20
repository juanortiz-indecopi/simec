from typing import Annotated

from fastapi import Query
from pydantic import AfterValidator

from app.domain.models.sunarp import AREAS_REGISTRALES, normalizar_area

NAME_PATTERN = r"^[\w .\-áéíóúñÁÉÍÓÚÑ]+$"


def _validar_area(valor: str) -> str:
    area = normalizar_area(valor)
    if area is None:
        raise ValueError(
            "Área registral no válida. Use una de: " + "; ".join(AREAS_REGISTRALES)
        )
    return area


OficinaQuery = Annotated[
    str,
    Query(
        min_length=2,
        max_length=60,
        pattern=NAME_PATTERN,
        description="Nombre de la oficina registral.",
        examples=["CUSCO"],
    ),
]

AreaQuery = Annotated[
    str,
    Query(
        min_length=2,
        max_length=100,
        description=(
            "Área registral. Solo se admiten las áreas del buscador de SPRL; se ignoran mayúsculas, "
            "tildes y signos (\"PERSONAS JURÍDICAS\" equivale a \"Personas Juridicas\"). "
            "Se responde con el nombre canónico."
        ),
        examples=["Personas Juridicas"],
        json_schema_extra={"enum": list(AREAS_REGISTRALES)},
    ),
    AfterValidator(_validar_area),
]

PartidaQuery = Annotated[
    str,
    Query(
        pattern=r"^[0-9]+$",
        description="Número de la partida registral (solo dígitos).",
        examples=["11156404"],
    ),
]
