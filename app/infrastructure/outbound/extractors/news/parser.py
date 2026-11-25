import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Final
from urllib.parse import urlsplit

from app.domain.models.news import NewsArticle

FEED_LIMIT: Final = 100
NEWS_HOST: Final = "news.google.com"
_SOCIAL: Final = (
    "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com", "youtube.com", "linkedin.com",
)


class FeedError(ValueError):
    """El feed no tiene la forma esperada: no se entrega ningún dato."""


@dataclass(frozen=True, slots=True)
class ParsedFeed:
    articles: tuple[NewsArticle, ...]
    social_skipped: int
    total: int


def parse_feed(content: bytes) -> ParsedFeed:
    if b"<!DOCTYPE" in content or b"<!ENTITY" in content:
        raise FeedError("XML con DTD o entidades")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise FeedError(f"XML inválido: {exc}") from exc
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise FeedError("La respuesta no es un RSS")

    items = channel.findall("item")
    articles: dict[str, NewsArticle] = {}
    skipped = 0
    for item in items:
        source = item.find("source")
        outlet_url = source.get("url") if source is not None else None
        if _is_social(outlet_url):
            skipped += 1
            continue
        article = _article(item, source, outlet_url)
        articles.setdefault(article.article_id, article)
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    ordered = sorted(articles.values(), key=lambda a: a.published_at or oldest, reverse=True)
    return ParsedFeed(tuple(ordered), skipped, len(items))


def _article(item: ET.Element, source: ET.Element | None, outlet_url: str | None) -> NewsArticle:
    title, link, guid = (_text(item.findtext(tag)) for tag in ("title", "link", "guid"))
    if not title or not link or not guid:
        raise FeedError("Noticia sin título, enlace o identificador")
    url = urlsplit(link)
    if url.scheme != "https" or url.hostname != NEWS_HOST:
        raise FeedError("Noticia con un enlace inesperado")
    outlet = _text(source.text) if source is not None else None
    if outlet:
        title = title.removesuffix(f" - {outlet}")
    return NewsArticle(
        title=title,
        url=url._replace(query="", fragment="").geturl(),
        article_id=guid,
        outlet=outlet,
        outlet_url=outlet_url,
        published_at=_date(item.findtext("pubDate")),
    )


def _is_social(url: str | None) -> bool:
    host = urlsplit(url or "").hostname or ""
    return any(host == domain or host.endswith("." + domain) for domain in _SOCIAL)


def _text(value: str | None) -> str | None:
    return " ".join((value or "").split()) or None


def _date(value: str | None) -> datetime | None:
    try:
        moment = parsedate_to_datetime(value) if value else None
    except ValueError:
        return None
    if moment is None:
        return None
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)
