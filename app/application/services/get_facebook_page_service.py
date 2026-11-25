import asyncio
from datetime import datetime, timezone

from app.application.dto.command.get_facebook_page_command import GetFacebookPageCommand
from app.application.dto.result.facebook_page_result import FacebookPageResult
from app.application.port.out.extractor_port import ExtractorPort
from app.application.port.out.snapshot_repository_port import QueryOutcome, SnapshotRepositoryPort
from app.application.port.usecase.get_facebook_page_use_case import GetFacebookPageUseCase
from app.application.services.cached_source_runner import CachedSourcesResult, run_cached_sources
from app.application.services.source_cache import SourceCache
from app.application.services.source_runner import DEFAULT_TIMEOUT_S
from app.domain.models.facebook import CompanyFacts, FacebookPage, MatchResult, PageVerification
from app.domain.models.party import PartyRef
from app.domain.models.profile import CompanyProfile
from app.domain.models.query import FetchMode, QueryType, served_from
from app.domain.models.sunat import SunatProfile
from app.domain.services.facebook_verification import verify_page
from app.domain.services.link_extraction import links_from_sunat, unique_links

COMPANY_RUC_PREFIX = "20"


class GetFacebookPageService(GetFacebookPageUseCase):
    def __init__(
        self,
        page: ExtractorPort,
        profile: ExtractorPort,
        sunat: ExtractorPort,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        snapshots: SnapshotRepositoryPort | None = None,
    ) -> None:
        self._page_sources = {"page": page}
        self._company_sources = {"profile": profile, "sunat": sunat}
        self._timeout_s = timeout_s
        self._cache = SourceCache(snapshots)

    async def execute(self, command: GetFacebookPageCommand) -> FacebookPageResult:
        compare = command.ruc is not None and command.ruc.startswith(COMPANY_RUC_PREFIX)
        if compare:
            run, company = await asyncio.gather(self._read_page(command), self._read_company(command.ruc))
        else:
            run, company = await self._read_page(command), None

        page = run.results["page"].data_as(FacebookPage)
        audits = [result.audit for result in run.results.values()]
        origins = run.origins
        if company is not None:
            audits += [result.audit for result in company.results.values()]
            origins += company.origins
        return FacebookPageResult(
            requested_page=command.page,
            page=page,
            verification=self._verify(command.ruc, page, company),
            audit_entries=tuple(audits),
            served_from=served_from(origins),
            data_origins=origins,
        )

    async def _read_page(self, command: GetFacebookPageCommand) -> CachedSourcesResult:
        requested_at = datetime.now(timezone.utc)
        run = await run_cached_sources(
            self._page_sources,
            command.page,
            command.page,
            refresh=command.refresh,
            cache=self._cache,
            timeout_s=self._timeout_s,
        )
        # Sin `subject`: la página no se vincula a un RUC hasta que lo confirme un analista.
        await self._cache.save(
            QueryOutcome(
                query_type=QueryType.FACEBOOK_PAGE,
                query_parameter=command.page,
                cache_key=command.page,
                fetch_mode=FetchMode.REFRESH if command.refresh else FetchMode.CACHE,
                served_from=run.served_from,
                requested_at=requested_at,
                completed_at=datetime.now(timezone.utc),
                executions=run.executions,
                reused_snapshot_ids=run.reused_snapshot_ids,
            )
        )
        return run

    async def _read_company(self, ruc: str) -> CachedSourcesResult:
        """Datos registrales: los guardados por /companies, o en vivo si aún no hay (sin refresh)."""
        requested_at = datetime.now(timezone.utc)
        run = await run_cached_sources(
            self._company_sources, ruc, ruc, refresh=False, cache=self._cache, timeout_s=self._timeout_s
        )
        if run.executions:
            profile = run.results["profile"].data_as(CompanyProfile)
            sunat = run.results["sunat"].data_as(SunatProfile)
            subject = PartyRef.from_ruc(ruc, profile.legal_name if profile else ruc)
            links = []
            if sunat is not None and "sunat" in run.live_keys:
                links = links_from_sunat(sunat, subject, self._company_sources["sunat"].source_name)
            await self._cache.save(
                QueryOutcome(
                    query_type=QueryType.COMPANY_BY_RUC,
                    query_parameter=ruc,
                    cache_key=ruc,
                    fetch_mode=FetchMode.CACHE,
                    served_from=run.served_from,
                    requested_at=requested_at,
                    completed_at=datetime.now(timezone.utc),
                    subject=subject if profile else None,
                    executions=run.executions,
                    reused_snapshot_ids=run.reused_snapshot_ids,
                    links=tuple(unique_links(links)) if profile else (),
                )
            )
        return run

    @staticmethod
    def _verify(
        ruc: str | None, page: FacebookPage | None, company: CachedSourcesResult | None
    ) -> PageVerification | None:
        if ruc is None:
            return None
        if company is None:
            return PageVerification(
                ruc, MatchResult.NOT_EVALUATED, warnings=("Solo se comparan empresas (RUC 20)",)
            )
        if page is None:
            return PageVerification(
                ruc, MatchResult.NOT_EVALUATED, warnings=("No se obtuvo la página de Facebook",)
            )
        profile = company.results["profile"].data_as(CompanyProfile)
        sunat = company.results["sunat"].data_as(SunatProfile)
        names = [profile.legal_name if profile else None, sunat.commercial_name if sunat else None]
        facts = CompanyFacts(
            ruc=ruc,
            names=tuple(dict.fromkeys(n for n in names if n and n.strip(" -"))),
            addresses=tuple(
                a
                for a in (
                    sunat.fiscal_address if sunat else None,
                    profile.address if profile else None,
                    *(b.address for b in (sunat.branch_offices if sunat else ())),
                )
                if a
            ),
            places=tuple(
                p for p in (profile.district, profile.province, profile.department) if p
            )
            if profile
            else (),
            activities=sunat.economic_activities if sunat else (),
        )
        if not facts.names:
            return PageVerification(
                ruc, MatchResult.NOT_EVALUATED, warnings=("No se obtuvieron los datos de la empresa",)
            )
        return verify_page(page, facts)
