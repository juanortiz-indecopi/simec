import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError

from app.application.port.usecase.get_news_use_case import GetNewsUseCase
from app.core.dependencies import get_news_use_case
from app.infrastructure.inbound.docs.responses import NEWS_RESPONSES
from app.infrastructure.inbound.dto.request.news_request import NameQuery, TopicQuery
from app.infrastructure.inbound.dto.request.refresh_request import RefreshQuery
from app.infrastructure.inbound.dto.response.news_response import NewsResponse
from app.infrastructure.inbound.mapper import news_mapper

logger = logging.getLogger(__name__)

router = APIRouter()

DESCRIPTION = """
Busca noticias en Google News por **nombre** (empresa o persona), por **tema** o por ambos.

| Petición | Qué busca |
|---|---|
| `/news?name=Backus` | La frase exacta "Backus" |
| `/news?topic=concertación de precios` | Noticias sobre un mercado o conducta |
| `/news?name=Backus&topic=Indecopi` | La empresa dentro de ese tema |

**Parámetros** (todos van en la URL)

| Parámetro | Tipo | Obligatorio | Por defecto | Límites |
|---|---|---|---|---|
| `name` | string | Al menos uno: `name` o `topic` | – | 2 a 120 caracteres |
| `topic` | string | Al menos uno: `name` o `topic` | – | 2 a 120 caracteres |
| `refresh` | boolean | No | `false` | `true` o `false` |

**Qué devuelve:** título, medio, fecha y enlace de cada noticia; **no** su texto.

**Cómo leer el resultado**

| `audit_entries[].status` | Significado |
|---|---|
| `SUCCESS` | Hay noticias |
| `NO_DATA` | No se encontraron: **no** equivale a "sin antecedentes" |
| `ERROR` | Bloqueo o respuesta no reconocida. Tras un bloqueo, la web se pausa 15 min |

- Puede haber **homónimos**: nada se vincula a un RUC o DNI; lo confirma un analista.
- Los resultados varían entre consultas: no constituyen una búsqueda exhaustiva.
- Se omiten publicaciones de redes sociales. Las consultas a la web se espacian 10 s.
"""


@router.get(
    "",
    operation_id="search_news",
    summary="Buscar noticias por nombre o tema",
    description=DESCRIPTION,
    response_model=NewsResponse,
    status_code=status.HTTP_200_OK,
    responses=NEWS_RESPONSES,
)
async def search_news(
    use_case: Annotated[GetNewsUseCase, Depends(get_news_use_case)],
    name: NameQuery = None,
    topic: TopicQuery = None,
    refresh: RefreshQuery = False,
) -> NewsResponse:
    if name is None and topic is None:
        raise RequestValidationError(
            [
                {
                    "type": "missing",
                    "loc": ("query", "name"),
                    "msg": "Indique `name`, `topic` o ambos",
                    "input": None,
                }
            ]
        )
    try:
        result = await use_case.execute(news_mapper.to_command(name, topic, refresh))
    except Exception as exc:
        logger.exception("Unexpected error searching news")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while searching news",
        ) from exc
    return news_mapper.to_response(result)
