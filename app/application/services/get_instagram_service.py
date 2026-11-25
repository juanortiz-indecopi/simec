from datetime import datetime, timezone

from app.application.dto.command.get_instagram_command import GetInstagramCommand
from app.application.dto.result.instagram_result import InstagramResult
from app.application.port.out.extractor_port import ExtractorPort
from app.application.port.out.snapshot_repository_port import QueryOutcome, SnapshotRepositoryPort
from app.application.port.usecase.get_instagram_use_case import GetInstagramUseCase
from app.application.services.cached_source_runner import run_cached_sources
from app.application.services.source_cache import SourceCache
from app.application.services.source_runner import DEFAULT_TIMEOUT_S
from app.domain.models.instagram import InstagramProfile
from app.domain.models.query import FetchMode, QueryType


class GetInstagramService(GetInstagramUseCase):
    def __init__(
        self,
        profile: ExtractorPort,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        snapshots: SnapshotRepositoryPort | None = None,
    ) -> None:
        self._sources = {"profile": profile}
        self._timeout_s = timeout_s
        self._cache = SourceCache(snapshots)

    async def execute(self, command: GetInstagramCommand) -> InstagramResult:
        requested_at = datetime.now(timezone.utc)
        run = await run_cached_sources(
            self._sources,
            command.username,
            command.username,
            refresh=command.refresh,
            cache=self._cache,
            timeout_s=self._timeout_s,
        )
        # Sin `subject`: un username no identifica por sí solo a una persona con documento.
        await self._cache.save(
            QueryOutcome(
                query_type=QueryType.INSTAGRAM_PROFILE,
                query_parameter=command.username,
                cache_key=command.username,
                fetch_mode=FetchMode.REFRESH if command.refresh else FetchMode.CACHE,
                served_from=run.served_from,
                requested_at=requested_at,
                completed_at=datetime.now(timezone.utc),
                executions=run.executions,
                reused_snapshot_ids=run.reused_snapshot_ids,
            )
        )
        return InstagramResult(
            username=command.username,
            profile=run.results["profile"].data_as(InstagramProfile),
            audit_entries=tuple(result.audit for result in run.results.values()),
            served_from=run.served_from,
            data_origins=run.origins,
        )
