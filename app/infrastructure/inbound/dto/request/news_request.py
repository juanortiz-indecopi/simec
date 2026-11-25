from typing import Annotated

from fastapi import Query
from pydantic import AfterValidator

from app.domain.models.news import MAX_TERM_LENGTH, normalize_term

NameQuery = Annotated[
    str | None,
    Query(
        title="Nombre",
        min_length=2,
        max_length=MAX_TERM_LENGTH,
        description=(
            "Nombre de la empresa o persona. **Opcional si se envía `topic`.**\n\n"
            "- Se busca como **frase exacta**; en personas, use el nombre completo.\n"
            "- No distingue mayúsculas ni espacios repetidos.\n"
            "- Admite letras, números, espacios y `& . , ' / + -`. No admite comillas ni operadores "
            "como `site:`.\n"
            "- No es un RUC ni un DNI: no se valida contra ningún registro."
        ),
        openapi_examples={
            "ninguno": {"summary": "Sin nombre (solo tema)", "value": None},
            "empresa": {"summary": "Empresa", "value": "Backus"},
            "persona": {"summary": "Persona (nombre completo)", "value": "Juan Pérez Quispe"},
        },
    ),
    AfterValidator(normalize_term),
]

TopicQuery = Annotated[
    str | None,
    Query(
        title="Tema",
        min_length=2,
        max_length=MAX_TERM_LENGTH,
        description=(
            "Tema, mercado o conducta. **Opcional si se envía `name`.**\n\n"
            "- Se busca por **palabras**, sin exigir el orden ni la frase exacta.\n"
            "- Si también se envía `name`, acota la búsqueda de ese nombre.\n"
            "- Mismos caracteres admitidos que `name`."
        ),
        openapi_examples={
            "ninguno": {"summary": "Sin tema (solo nombre)", "value": None},
            "conducta": {"summary": "Posible conducta anticompetitiva", "value": "concertación de precios"},
            "mercado": {"summary": "Mercado", "value": "mercado cervecero"},
            "entidad": {"summary": "Entidad relacionada", "value": "Indecopi"},
        },
    ),
    AfterValidator(normalize_term),
]
