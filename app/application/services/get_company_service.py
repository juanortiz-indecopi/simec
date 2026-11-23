from datetime import datetime, timezone

from app.application.dto.command.get_company_command import GetCompanyCommand
from app.application.dto.result.company_result import CompanyResult
from app.application.port.out.extractor_port import ExtractorPort
from app.application.port.out.snapshot_repository_port import QueryOutcome, SnapshotRepositoryPort
from app.application.port.usecase.get_company_use_case import GetCompanyUseCase
from app.application.services.cached_source_runner import run_cached_sources
from app.application.services.source_cache import SourceCache
from app.application.services.source_runner import DEFAULT_TIMEOUT_S
from app.domain.models.party import PartyLink, PartyRef
from app.domain.models.profile import CompanyProfile
from app.domain.models.query import FetchMode, QueryType
from app.domain.models.rnp import RnpRecord
from app.domain.models.seace import SeaceProviderRecord
from app.domain.models.sunat import SunatProfile
from app.domain.services.link_extraction import (
    links_from_seace_provider,
    links_from_sunat,
    unique_links,
)


class GetCompanyService(GetCompanyUseCase):
    def __init__(
        self,
        profile: ExtractorPort,
        seace: ExtractorPort,
        sunat: ExtractorPort,
        rnp: ExtractorPort,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        snapshots: SnapshotRepositoryPort | None = None,
    ) -> None:
        self._sources = {"profile": profile, "seace": seace, "sunat": sunat, "rnp": rnp}
        self._timeout_s = timeout_s
        self._cache = SourceCache(snapshots)

    async def execute(self, command: GetCompanyCommand) -> CompanyResult:
        requested_at = datetime.now(timezone.utc)
        run = await run_cached_sources(
            self._sources,
            command.ruc,
            command.ruc,
            refresh=command.refresh,
            cache=self._cache,
            timeout_s=self._timeout_s,
        )
        results = run.results
        profile = results["profile"].data_as(CompanyProfile)
        seace = results["seace"].data_as(SeaceProviderRecord)
        sunat = results["sunat"].data_as(SunatProfile)
        rnp = results["rnp"].data_as(RnpRecord)

        subject = PartyRef.from_ruc(
            command.ruc,
            _first_name(
                profile.legal_name if profile else None,
                rnp.business_name if rnp else None,
                sunat.commercial_name if sunat else None,
            )
            or command.ruc,
        )
        links: list[PartyLink] = []
        if sunat is not None and "sunat" in run.live_keys:
            links += links_from_sunat(sunat, subject, self._sources["sunat"].source_name)
        if seace is not None and "seace" in run.live_keys:
            links += links_from_seace_provider(seace, subject, self._sources["seace"].source_name)

        await self._cache.save(
            QueryOutcome(
                query_type=QueryType.COMPANY_BY_RUC,
                query_parameter=command.ruc,
                cache_key=command.ruc,
                fetch_mode=FetchMode.REFRESH if command.refresh else FetchMode.CACHE,
                served_from=run.served_from,
                requested_at=requested_at,
                completed_at=datetime.now(timezone.utc),
                subject=subject,
                executions=run.executions,
                reused_snapshot_ids=run.reused_snapshot_ids,
                links=tuple(unique_links(links)),
            )
        )

        return CompanyResult(
            ruc=command.ruc,
            profile=profile,
            seace=seace,
            sunat=sunat,
            rnp=rnp,
            audit_entries=tuple(result.audit for result in results.values()),
            served_from=run.served_from,
            data_origins=run.origins,
        )


def _first_name(*candidates: str | None) -> str | None:
    return next((name.strip() for name in candidates if name and name.strip()), None)
