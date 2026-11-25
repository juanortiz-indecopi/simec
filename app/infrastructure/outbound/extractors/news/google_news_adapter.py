"""Google News (RSS) por nombre o tema. Petición HTTP simple: no reintenta y se pausa ante un bloqueo.

Solo se toman título, medio, fecha y enlace; no se visita la noticia ni se guarda su texto.
"""
import asyncio
import re
from typing import ClassVar, Final

import httpx

from app.domain.models.news import NewsSearch
from app.infrastructure.outbound.extractors.news.parser import FEED_LIMIT, NEWS_HOST, FeedError, parse_feed
from app.infrastructure.outbound.extractors.shared.extractor import BaseExtractor, Outcome
from app.infrastructure.outbound.extractors.shared.pace import Pace

FEED_URL: Final = f"https://{NEWS_HOST}/rss/search"
EDITION: Final = {"hl": "es-419", "gl": "PE", "ceid": "PE:es-419"}
REQUEST_TIMEOUT_S: Final = 30.0
BLOCK_STATUS: Final = frozenset({401, 403, 429, 503})

_PACE: Final = Pace()


class GoogleNewsAdapter(BaseExtractor):
    SOURCE_NAME: ClassVar[str] = "GOOGLE_NEWS_RSS"
    PATTERN: ClassVar[re.Pattern[str]] = re.compile(r".{2,300}")
    PARAMETER_HINT: ClassVar[str] = "a news query"

    def __init__(
        self, transport: httpx.AsyncBaseTransport | None = None, pace: Pace | None = None
    ) -> None:
        self._transport = transport
        self._pace = pace or _PACE

    async def _fetch(self, value: str) -> Outcome:
        if self._pace.blocked_for() > 0:
            return self._paused()
        await asyncio.sleep(self._pace.reserve())
        if self._pace.blocked_for() > 0:  # Otra consulta fue bloqueada mientras se esperaba el turno.
            return self._paused()

        async with httpx.AsyncClient(
            transport=self._transport, timeout=REQUEST_TIMEOUT_S, follow_redirects=True
        ) as client:
            response = await client.get(FEED_URL, params={"q": value, **EDITION})

        is_feed = response.url.host == NEWS_HOST and "xml" in response.headers.get("content-type", "")
        if response.status_code in BLOCK_STATUS or (response.is_success and not is_feed):
            self._pace.block()
            return Outcome(
                details=f"Google News bloqueó la consulta (HTTP {response.status_code})", failed=True
            )
        if not response.is_success:
            return Outcome(details=f"Google News respondió HTTP {response.status_code}", failed=True)

        try:
            feed = parse_feed(response.content)
        except FeedError as exc:
            return Outcome(details=f"Respuesta no reconocida: {exc}", failed=True)
        note = (
            f"Se omitieron {feed.social_skipped} publicaciones de redes sociales"
            if feed.social_skipped
            else None
        )
        if not feed.articles:
            return Outcome(details=note or "Sin noticias para esta búsqueda")
        return Outcome(
            data=NewsSearch(query=value, articles=feed.articles, reached_limit=feed.total >= FEED_LIMIT),
            details=note,
        )

    def _paused(self) -> Outcome:
        minutes = int(self._pace.blocked_for() // 60) + 1
        return Outcome(
            details=f"Google News en pausa tras un bloqueo; reintente en {minutes} min", failed=True
        )
