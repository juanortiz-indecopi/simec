from datetime import datetime, timezone

from app.application.dto.command.get_news_command import GetNewsCommand
from app.application.dto.result.news_result import NewsResult
from app.application.port.out.extractor_port import ExtractorPort
from app.application.port.out.snapshot_repository_port import QueryOutcome, SnapshotRepositoryPort
from app.application.port.usecase.get_news_use_case import GetNewsUseCase
from app.application.services.cached_source_runner import run_cached_sources
from app.application.services.source_cache import SourceCache
from app.application.services.source_runner import DEFAULT_TIMEOUT_S
from app.domain.models.news import NewsSearch, build_query
from app.domain.models.query import FetchMode, QueryType


class GetNewsService(GetNewsUseCase):
    def __init__(
        self,
        news: ExtractorPort,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        snapshots: SnapshotRepositoryPort | None = None,
    ) -> None:
        self._sources = {"news": news}
        self._timeout_s = timeout_s
        self._cache = SourceCache(snapshots)

    async def execute(self, command: GetNewsCommand) -> NewsResult:
        query = build_query(command.name, command.topic)
        requested_at = datetime.now(timezone.utc)
        run = await run_cached_sources(
            self._sources,
            query,
            query,
            refresh=command.refresh,
            cache=self._cache,
            timeout_s=self._timeout_s,
        )
        search = run.results["news"].data_as(NewsSearch)
        # Sin `subject`: una coincidencia de nombre no identifica a una persona ni a una empresa.
        await self._cache.save(
            QueryOutcome(
                query_type=QueryType.NEWS_SEARCH,
                query_parameter=query,
                cache_key=query,
                fetch_mode=FetchMode.REFRESH if command.refresh else FetchMode.CACHE,
                served_from=run.served_from,
                requested_at=requested_at,
                completed_at=datetime.now(timezone.utc),
                executions=run.executions,
                reused_snapshot_ids=run.reused_snapshot_ids,
                articles=search.articles if search and "news" in run.live_keys else (),
            )
        )
        return NewsResult(
            query=query,
            name=command.name,
            topic=command.topic,
            search=search,
            audit_entries=tuple(result.audit for result in run.results.values()),
            served_from=run.served_from,
            data_origins=run.origins,
        )
