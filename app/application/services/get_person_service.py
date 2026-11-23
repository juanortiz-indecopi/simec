from datetime import datetime, timezone

from app.application.dto.command.get_person_command import GetPersonCommand
from app.application.dto.result.person_result import PersonResult
from app.application.port.out.extractor_port import ExtractorPort
from app.application.port.out.snapshot_repository_port import QueryOutcome, SnapshotRepositoryPort
from app.application.port.usecase.get_person_use_case import GetPersonUseCase
from app.application.services.cached_source_runner import run_cached_sources
from app.application.services.source_cache import SourceCache
from app.application.services.source_runner import DEFAULT_TIMEOUT_S
from app.domain.models.party import PartyLink, PartyRef, dni_from_natural_person_ruc
from app.domain.models.profile import PersonProfile
from app.domain.models.query import FetchMode, QueryType
from app.domain.models.seace import SeacePersonRecord
from app.domain.models.sunat import SunatProfile
from app.domain.services.link_extraction import (
    links_from_seace_person,
    links_from_sunat,
    unique_links,
)


class GetPersonService(GetPersonUseCase):
    def __init__(
        self,
        profile: ExtractorPort,
        seace: ExtractorPort,
        sunat: ExtractorPort,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        snapshots: SnapshotRepositoryPort | None = None,
    ) -> None:
        self._sources = {"profile": profile, "seace": seace, "sunat": sunat}
        self._timeout_s = timeout_s
        self._cache = SourceCache(snapshots)

    async def execute(self, command: GetPersonCommand) -> PersonResult:
        requested_at = datetime.now(timezone.utc)
        run = await run_cached_sources(
            self._sources,
            command.dni,
            command.dni,
            refresh=command.refresh,
            cache=self._cache,
            timeout_s=self._timeout_s,
        )
        results = run.results
        profile = results["profile"].data_as(PersonProfile)
        seace = results["seace"].data_as(SeacePersonRecord)
        sunat = results["sunat"].data_as(SunatProfile)

        # El RUC 10 de SUNAT se asocia a la persona solo si contiene este mismo DNI.
        tax_id = sunat.tax_id if sunat and dni_from_natural_person_ruc(sunat.tax_id) == command.dni else None
        subject = PartyRef.person(
            command.dni, profile.full_name if profile and profile.full_name else command.dni, tax_id
        )
        links: list[PartyLink] = []
        if sunat is not None and tax_id and "sunat" in run.live_keys:
            # Representantes del negocio de la persona (RUC 10). Ella misma se descarta al guardar.
            links += links_from_sunat(sunat, subject, self._sources["sunat"].source_name)
        if seace is not None and "seace" in run.live_keys:
            links += links_from_seace_person(seace, subject, self._sources["seace"].source_name)

        await self._cache.save(
            QueryOutcome(
                query_type=QueryType.PERSON_BY_DNI,
                query_parameter=command.dni,
                cache_key=command.dni,
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

        return PersonResult(
            dni=command.dni,
            profile=profile,
            seace=seace,
            sunat=sunat,
            audit_entries=tuple(result.audit for result in results.values()),
            served_from=run.served_from,
            data_origins=run.origins,
        )
