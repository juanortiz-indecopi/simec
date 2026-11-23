"""Ejecuta un grupo de fuentes decidiendo, por cada una, si sale de la BD o de la web.

Por cada fuente:
  - refresh=False y hay foto válida guardada  -> se sirve desde la BD (sin scraping).
  - refresh=True o no hay foto                -> se consulta en la web.
      * si otra petición ya la está consultando, se espera y se usa su resultado;
      * si la consulta web falla pero había foto guardada, se sirve la foto (con aviso).
"""
import asyncio
import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from app.application.port.out.extractor_port import ExtractorPort
from app.application.port.out.snapshot_repository_port import SourceExecution
from app.application.services.source_cache import SourceCache, lease_for
from app.application.services.source_runner import SourceResult, run_sources
from app.domain.models.audit import AuditResult, AuditStatus
from app.domain.models.query import (
    ServedFrom,
    SourceOrigin,
    StoredSnapshot,
    served_from,
)

# Tiempo extra que una petición espera a otra que ya está consultando la misma fuente.
WAIT_MARGIN_S = 60.0


def cached_audit(snapshot: StoredSnapshot, query_parameter: str) -> AuditResult:
    """Entrada de auditoría para una fuente servida desde la BD (no se consultó en esta petición)."""
    return AuditResult(
        source_name=snapshot.source_name,
        query_parameter=query_parameter,
        duration_ms=0,
        status=AuditStatus.SUCCESS,
        details=f"Servido desde la base de datos; obtenido de la fuente el {_fmt(snapshot.executed_at)}.",
        executed_at_utc=snapshot.executed_at,
    )


def with_fallback_note(audit: AuditResult, snapshot: StoredSnapshot) -> AuditResult:
    """La actualización falló: se informa el error y que se muestran los datos guardados."""
    note = f"Se muestran los datos guardados del {_fmt(snapshot.executed_at)}."
    details = f"{audit.details} | {note}" if audit.details else note
    return dataclasses.replace(audit, details=details)


def _fmt(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@dataclass(frozen=True, slots=True)
class CachedSourcesResult:
    # Resultado final por clave ("profile", "sunat"...): datos en vivo o recuperados de la BD.
    results: dict[str, SourceResult]
    origins: tuple[SourceOrigin, ...]
    # Lo consultado en la web en esta petición (se guarda como fotos nuevas).
    executions: tuple[SourceExecution, ...]
    # Fotos de la BD servidas en esta petición (trazabilidad).
    reused_snapshot_ids: tuple[int, ...]
    # Claves cuyos datos se obtuvieron en vivo en esta petición (para derivar vínculos).
    live_keys: frozenset[str]

    @property
    def served_from(self) -> ServedFrom:
        return served_from(self.origins)


async def run_cached_sources(
    sources: Mapping[str, ExtractorPort],
    parameter: str,
    cache_key: str,
    *,
    refresh: bool,
    cache: SourceCache,
    timeout_s: float,
) -> CachedSourcesResult:
    names = {key: extractor.source_name for key, extractor in sources.items()}
    lease = lease_for(timeout_s)

    # 1. Lectura corta: fotos guardadas.
    stored = await cache.lookup(names.values(), cache_key)

    # 2. Qué hay que consultar en la web y qué reservamos nosotros.
    wanted = [key for key in sources if refresh or names[key] not in stored]
    claimed = await cache.claim([names[key] for key in wanted], cache_key, lease)
    mine = [key for key in wanted if names[key] in claimed]
    others = [key for key in wanted if names[key] not in claimed]

    # 3. Scraping (sin conexión a la BD) y, en paralelo, espera de las que consulta otra petición.
    try:
        live, _ = await asyncio.gather(
            run_sources({key: sources[key] for key in mine}, parameter, timeout_s),
            cache.wait_for_others(
                [names[key] for key in others], cache_key, lease, timeout_s + WAIT_MARGIN_S
            ),
        )
    except BaseException:
        # Petición cancelada (p.ej. el cliente cerró la conexión): liberar las reservas.
        await asyncio.shield(cache.release([names[key] for key in mine], cache_key))
        raise

    # 4. Las que consultó otra petición: si dejó una foto nueva se usa; si no, se consultan aquí.
    if others:
        fresh = await cache.lookup([names[key] for key in others], cache_key)
        retry = []
        for key in others:
            before, after = stored.get(names[key]), fresh.get(names[key])
            if after is not None and (before is None or after.snapshot_id != before.snapshot_id):
                stored[names[key]] = after
            else:
                retry.append(key)
        if retry:
            live |= await run_sources({key: sources[key] for key in retry}, parameter, timeout_s)

    # 5. Resultado final por fuente.
    now = datetime.now(timezone.utc)
    results: dict[str, SourceResult] = {}
    origins: list[SourceOrigin] = []
    executions: list[SourceExecution] = []
    reused: list[int] = []
    live_keys: set[str] = set()

    for key in sources:
        name = names[key]
        snapshot = stored.get(name)
        if key in live:
            result = live[key]
            executions.append(SourceExecution(result.audit, result.data, result.raw))
            if result.data is not None:
                results[key] = result
                origins.append(SourceOrigin(name, False, result.audit.executed_at_utc))
                live_keys.add(key)
            elif snapshot is not None:
                results[key] = SourceResult(with_fallback_note(result.audit, snapshot), snapshot.data)
                origins.append(SourceOrigin(name, True, snapshot.executed_at, snapshot.is_stale(now)))
                reused.append(snapshot.snapshot_id)
            else:
                results[key] = result
                origins.append(SourceOrigin(name, False, None))
        else:
            results[key] = SourceResult(cached_audit(snapshot, parameter), snapshot.data)
            origins.append(SourceOrigin(name, True, snapshot.executed_at, snapshot.is_stale(now)))
            reused.append(snapshot.snapshot_id)

    return CachedSourcesResult(
        results=results,
        origins=tuple(origins),
        executions=tuple(executions),
        reused_snapshot_ids=tuple(reused),
        live_keys=frozenset(live_keys),
    )
