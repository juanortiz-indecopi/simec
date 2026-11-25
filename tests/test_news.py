"""Noticias: normalización, feed, extractor y endpoint, sin red ni base de datos."""
import asyncio
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.application.services.get_news_service import GetNewsService
from app.core.dependencies import get_news_use_case
from app.domain.models.audit import AuditResult, AuditStatus
from app.domain.models.news import NewsArticle, NewsSearch, build_query, normalize_term
from app.infrastructure.outbound.extractors.news.google_news_adapter import GoogleNewsAdapter
from app.infrastructure.outbound.extractors.news.parser import FeedError, parse_feed
from app.infrastructure.outbound.extractors.shared.pace import Pace
from app.infrastructure.outbound.persistence.mapper import payload_mapper
from app.main import app
from tests.test_instagram_endpoint import BrokenRepository, FakeRepository

URL = "/api/v1/news"


def item(guid="a", title="Backus crece - Gestión", outlet="Gestión", site="https://gestion.pe",
         date="Tue, 24 Nov 2026 15:00:00 GMT", link=None):
    link = link or f"https://news.google.com/rss/articles/{guid}?oc=5"
    return (f"<item><title>{title}</title><link>{link}</link><guid>{guid}</guid>"
            f'<pubDate>{date}</pubDate><source url="{site}">{outlet}</source></item>')


def feed(*items):
    return f"<rss><channel>{''.join(items)}</channel></rss>".encode()


@pytest.mark.parametrize("raw, expected", [
    ("  BACKUS  ", "backus"), ("Coca-Cola", "coca-cola"), ("a -b c", "a b c"), ("", None), (None, None),
])
def test_normalize(raw, expected):
    assert normalize_term(raw) == expected


@pytest.mark.parametrize("raw", ['"backus"', "site:gob.pe", "(a b)", "x", "--", "...", "a" * 121])
def test_normalize_rejects(raw):
    with pytest.raises(ValueError):
        normalize_term(raw)


def test_query_quotes_only_the_name():
    assert build_query("backus", "indecopi") == '"backus" indecopi'
    assert build_query(None, "cartel pollo") == "cartel pollo"


def test_parse_orders_dedupes_and_skips_social():
    parsed = parse_feed(feed(
        item("old", date="Mon, 06 Jan 2025 10:00:00 GMT"), item("new"), item("new"),
        item("fb", outlet="Facebook", site="https://www.facebook.com"),
        item("nodate", date="sin fecha"),
    ))
    assert [a.article_id for a in parsed.articles] == ["new", "old", "nodate"]
    assert (parsed.social_skipped, parsed.total) == (1, 5)
    first = parsed.articles[0]
    assert (first.title, first.outlet) == ("Backus crece", "Gestión")
    assert first.url == "https://news.google.com/rss/articles/new"
    assert first.published_at == datetime(2026, 11, 24, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize("content", [
    b"<html></html>", b"no xml", b"<!DOCTYPE x><rss><channel/></rss>",
    feed(item(title="")), feed(item(link="https://otro.example/x")),
])
def test_parse_rejects_unexpected(content):
    with pytest.raises(FeedError):
        parse_feed(content)


def run(handler, pace=None):
    adapter = GoogleNewsAdapter(httpx.MockTransport(handler), pace or Pace(min_interval_s=0))
    return asyncio.run(adapter.extract('"backus"'))


def xml(content):
    return lambda request: httpx.Response(200, content=content, headers={"content-type": "application/xml"})


def test_extractor_success_and_limit():
    out = run(xml(feed(*(item(str(i)) for i in range(100)))))
    assert out["audit"].status is AuditStatus.SUCCESS
    assert len(out["data"].articles) == 100 and out["data"].reached_limit
    assert out["raw"] is None


def test_extractor_no_news():
    assert run(xml(feed()))["audit"].status is AuditStatus.NO_DATA


@pytest.mark.parametrize("response", [
    httpx.Response(429), httpx.Response(200, text="captcha", headers={"content-type": "text/html"}),
])
def test_block_pauses_without_retry(response):
    calls, pace = [], Pace(min_interval_s=0)

    def handler(request):
        calls.append(request)
        return response

    assert run(handler, pace)["audit"].status is AuditStatus.ERROR
    second = run(handler, pace)["audit"]
    assert second.status is AuditStatus.ERROR and "pausa" in second.details
    assert len(calls) == 1


def test_bad_feed_is_error():
    assert run(xml(b"<rss/>"))["audit"].status is AuditStatus.ERROR


def test_payload_round_trip():
    data = NewsSearch("q", (NewsArticle("t", "https://u", "id", published_at=datetime.now(timezone.utc)),), True)
    assert payload_mapper.load(payload_mapper.dump(data)[0]) == data


class FakeNews:
    source_name = "GOOGLE_NEWS_RSS"

    def __init__(self):
        self.calls, self.ok = [], True

    async def extract(self, parameter):
        self.calls.append(parameter)
        status = AuditStatus.SUCCESS if self.ok else AuditStatus.ERROR
        titles = ("Multa a Backús", "Otra noticia")
        articles = tuple(NewsArticle(t, f"https://news.google.com/{i}", str(i)) for i, t in enumerate(titles))
        return {"audit": AuditResult(self.source_name, parameter, 1, status, None, datetime.now(timezone.utc)),
                "data": NewsSearch(parameter, articles) if self.ok else None, "raw": None}


@pytest.fixture
def env():
    news, repository = FakeNews(), FakeRepository()
    app.dependency_overrides[get_news_use_case] = lambda: GetNewsService(news, snapshots=repository)
    yield TestClient(app), news, repository
    app.dependency_overrides.clear()


def test_live_then_database(env):
    client, news, repository = env
    first = client.get(URL, params={"name": "BACKUS", "topic": "Indecopi"}).json()
    second = client.get(URL, params={"name": " backus", "topic": "indecopi"}).json()
    assert (first["served_from"], second["served_from"]) == ("LIVE", "DATABASE")
    assert first["query"] == '"backus" indecopi' and first["total"] == 2
    assert [a["name_in_title"] for a in first["articles"]] == [True, False]
    assert news.calls == ['"backus" indecopi']
    # Las noticias solo se guardan al obtenerlas en vivo, y nunca se vinculan a nadie.
    assert [len(o.articles) for o in repository.saved] == [2, 0]
    assert all(o.subject is None and o.links == () for o in repository.saved)


def test_failed_refresh_keeps_stored(env):
    client, news, repository = env
    client.get(URL, params={"topic": "cartel"})
    news.ok = False
    body = client.get(URL, params={"topic": "cartel", "refresh": True}).json()
    assert body["served_from"] == "DATABASE" and body["total"] == 2
    assert body["articles"][0]["name_in_title"] is None
    assert repository.saved[-1].articles == ()


def test_works_without_database():
    app.dependency_overrides[get_news_use_case] = lambda: GetNewsService(FakeNews(), snapshots=BrokenRepository())
    try:
        assert TestClient(app).get(URL, params={"name": "backus"}).json()["served_from"] == "LIVE"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("params", [{}, {"name": " "}, {"name": "site:x"}, {"topic": "x"}])
def test_invalid_parameters(env, params):
    client, news, _ = env
    response = client.get(URL, params=params)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][0] == "query"  # Formato declarado en OpenAPI.
    assert news.calls == []
