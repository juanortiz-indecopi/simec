from typing import Annotated

from fastapi import Query
from pydantic import AfterValidator

from app.domain.models.facebook import normalize_page


def _validate_page(value: str) -> str:
    key = normalize_page(value)
    if key is None:
        raise ValueError(
            "Página no válida: use el username, el ID o la URL de la página (no un nombre, un RUC, "
            "un grupo ni el enlace de una publicación)"
        )
    return key


FacebookPageQuery = Annotated[
    str,
    Query(
        min_length=2,
        max_length=500,
        description=(
            "Página de Facebook: username (`codideep`), ID numérico o URL "
            "(`https://www.facebook.com/codideep`, `https://www.facebook.com/profile.php?id=...`). "
            "Si la URL contiene `&`, envíela codificada."
        ),
        openapi_examples={
            "username": {"summary": "Username", "value": "codideep"},
            "url": {"summary": "URL", "value": "https://www.facebook.com/codideep"},
            "url_parametros": {
                "summary": "URL con parámetros",
                "value": "https://www.facebook.com/InternetApurimacAmericaServices/?locale=es_LA",
            },
            "id": {
                "summary": "URL con ID",
                "value": "https://www.facebook.com/profile.php?id=100063518592455",
            },
        },
    ),
    AfterValidator(_validate_page),
]

OptionalRucQuery = Annotated[
    str | None,
    Query(
        pattern=r"^[0-9]{11}$",
        description="RUC de la empresa con la que se compara la página. Solo se evalúan RUC 20.",
        examples=["20603687478"],
    ),
]
