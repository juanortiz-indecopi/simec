from typing import Annotated

from fastapi import Query

NAME_PATTERN = r"^[\w .\-áéíóúñÁÉÍÓÚÑ]+$"

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
        max_length=60,
        pattern=NAME_PATTERN,
        description="Nombre del área registral.",
        examples=["Personas Jurídicas"],
    ),
]

PartidaQuery = Annotated[
    str,
    Query(
        pattern=r"^[0-9]+$",
        description="Número de la partida registral (solo dígitos).",
        examples=["11156404"],
    ),
]