from dataclasses import asdict

from app.application.dto.command.get_news_command import GetNewsCommand
from app.application.dto.result.news_result import NewsResult
from app.domain.models.news import NewsArticle, words
from app.infrastructure.inbound.dto.response.news_response import NewsArticleResponse, NewsResponse
from app.infrastructure.inbound.mapper.audit_mapper import to_audit_responses


def to_command(name: str | None, topic: str | None, refresh: bool = False) -> GetNewsCommand:
    return GetNewsCommand(name=name, topic=topic, refresh=refresh)


def to_response(result: NewsResult) -> NewsResponse:
    articles = result.search.articles if result.search else ()
    return NewsResponse(
        query=result.query,
        name=result.name,
        topic=result.topic,
        served_from=result.served_from,
        total=len(articles),
        reached_limit=result.search.reached_limit if result.search else False,
        articles=[_to_article(article, result.name) for article in articles],
        audit_entries=to_audit_responses(result.audit_entries, result.data_origins),
    )


def _to_article(article: NewsArticle, name: str | None) -> NewsArticleResponse:
    found = f" {words(name)} " in f" {words(article.title)} " if name else None
    return NewsArticleResponse(**asdict(article), name_in_title=found)
