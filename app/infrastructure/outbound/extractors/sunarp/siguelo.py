"""Descarga de asientos de inscripción desde Síguelo Plus con el agente LLM + MCP de Playwright.

Por cada título (año + número) obtenido en SPRL se ejecuta una corrida del agente sobre la misma
sesión MCP (mismo Chrome real, así Cloudflare Turnstile se resuelve solo):
  formulario (oficina, año, número) -> BUSCAR -> /siguelo/titulo -> "Acceder al asiento de
  inscripción y TIVE" -> modal con una fila por partida -> herramienta `descargar_asientos_inscripcion`.

El agente navega mirando snapshots (cierra el anuncio y los Términos y Condiciones, que aparecen con
retraso y apilados). Solo la lectura del PDF es una herramienta local, porque vive en una pestaña
blob: que el LLM no puede leer. Una corrida por título aísla las fallas y acota el contexto.
"""
import base64
import logging
import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession

from app.core.files import FILES_DIR
from app.domain.models.audit import AuditResult, AuditStatus
from app.domain.models.sunarp import SunarpDocumentStatus
from app.infrastructure.outbound.extractors.sunarp.agent_runtime import correr_agente
from app.infrastructure.outbound.extractors.sunarp.prompts import (
    SIGUELO_ANIO_NO_DISPONIBLE,
    SIGUELO_FALLIDA,
    SIGUELO_NO_ENCONTRADO,
    SIGUELO_OFICINA_NO_DISPONIBLE,
    SIGUELO_OK,
    SIGUELO_SIN_ASIENTO,
    SIGUELO_SYSTEM_PROMPT,
    construir_tarea_siguelo,
)
from app.infrastructure.outbound.extractors.sunarp.tools import (
    crear_herramienta_buscar_siguelo,
    crear_herramienta_descarga_asientos,
    filtrar_herramientas,
)

logger = logging.getLogger(__name__)

SOURCE_NAME_SIGUELO = "SUNARP_SIGUELO"
MAX_PASOS_TITULO = 35

_YEAR_RE = re.compile(r"^\d{4}$")
_NUMBER_RE = re.compile(r"^\d{1,10}$")

_MARCAS = {
    SIGUELO_OK: SunarpDocumentStatus.DOWNLOADED,
    SIGUELO_NO_ENCONTRADO: SunarpDocumentStatus.NOT_FOUND,
    SIGUELO_OFICINA_NO_DISPONIBLE: SunarpDocumentStatus.OFFICE_NOT_AVAILABLE,
    SIGUELO_ANIO_NO_DISPONIBLE: SunarpDocumentStatus.YEAR_NOT_AVAILABLE,
    SIGUELO_SIN_ASIENTO: SunarpDocumentStatus.NO_INSCRIPTION_SEAT,
    SIGUELO_FALLIDA: SunarpDocumentStatus.ERROR,
}


def directorio_archivos() -> str:
    # Bajo FILES_DIR para que FastAPI lo publique en /files (ver app/core/files.py).
    return os.getenv("SUNARP_FILES_DIR", os.path.join(FILES_DIR, "sunarp"))


def _seguro(texto: str) -> str:
    """Fragmento apto para nombres de archivo/carpeta."""
    return re.sub(r"[^A-Za-z0-9]+", "_", texto).strip("_") or "x"


def _guardar_pdfs(destino: Path, year: str, number: str, documentos: list[dict]) -> list[dict]:
    guardados = []
    for doc in documentos:
        contenido = base64.b64decode(doc.get("b64") or "")
        if not contenido.startswith(b"%PDF"):
            logger.warning("Síguelo Plus: el archivo de la partida %s no es un PDF.", doc.get("partida"))
            continue
        destino.mkdir(parents=True, exist_ok=True)
        ruta = destino / f"titulo_{year}-{number}_partida_{_seguro(str(doc['partida']))}.pdf"
        ruta.write_bytes(contenido)
        guardados.append({
            "partida": str(doc["partida"]),
            "file_path": ruta.as_posix(),
            "size_bytes": len(contenido),
        })
    return guardados


def _estado_desde_mensaje(final: str) -> SunarpDocumentStatus:
    final = final.strip()
    for marca, estado in _MARCAS.items():
        if final.startswith(marca):
            return estado
    return SunarpDocumentStatus.ERROR


async def descargar_asientos_siguelo(
    session: ClientSession,
    oficina: str,
    partida: str,
    seats: list[dict[str, Any]],
    *,
    files_dir: str,
    log: Callable[[str], None],
    max_pasos: int = MAX_PASOS_TITULO,
) -> tuple[list[dict[str, Any]], AuditResult]:
    """Enriquece cada asiento con `documents`, `document_status` y `document_detail`.

    Devuelve los asientos enriquecidos y una entrada de auditoría propia (SUNARP_SIGUELO).
    """
    started = time.perf_counter()
    destino = Path(files_dir) / f"{_seguro(oficina)}_{_seguro(partida)}"
    herramientas_mcp = filtrar_herramientas(await load_mcp_tools(session))
    enriquecidos: list[dict[str, Any]] = []
    oficina_no_disponible: str | None = None

    for seat in seats:
        year, number = seat["year"], seat["number"]
        documentos: list[dict] = []
        detalle: str | None = None

        if oficina_no_disponible:
            # Misma oficina para todos los títulos: no se repite la consulta.
            estado, detalle = SunarpDocumentStatus.OFFICE_NOT_AVAILABLE, oficina_no_disponible
        elif not (_YEAR_RE.match(year) and _NUMBER_RE.match(number)):
            estado, detalle = SunarpDocumentStatus.ERROR, "Año o número de título con formato inválido."
        else:
            def al_descargar(docs: list[dict], _y=year, _n=number) -> list[dict]:
                guardados = _guardar_pdfs(destino, _y, _n, docs)
                documentos.extend(guardados)
                return guardados

            herramientas = [
                *herramientas_mcp,
                crear_herramienta_buscar_siguelo(session),
                crear_herramienta_descarga_asientos(session, al_descargar),
            ]
            log(f"[siguelo] título {year}-{number}: inicio del agente")
            try:
                resultado = await correr_agente(
                    herramientas,
                    SIGUELO_SYSTEM_PROMPT,
                    construir_tarea_siguelo(oficina, year, number),
                    max_pasos=max_pasos,
                    log=log,
                )
                final = resultado.final_message.strip()
                estado = _estado_desde_mensaje(final)
                detalle = final or f"{SIGUELO_FALLIDA}: el agente no terminó dentro de {max_pasos} pasos."
            except Exception as exc:
                estado, detalle = SunarpDocumentStatus.ERROR, f"{type(exc).__name__}: {exc}"

            # Los archivos guardados mandan sobre lo que diga el agente.
            if documentos:
                estado = SunarpDocumentStatus.DOWNLOADED
            elif estado == SunarpDocumentStatus.DOWNLOADED:
                estado = SunarpDocumentStatus.ERROR
                detalle = f"El agente reportó éxito pero no se guardó ningún PDF. {detalle or ''}".strip()

            if estado == SunarpDocumentStatus.OFFICE_NOT_AVAILABLE:
                oficina_no_disponible = (
                    f"La oficina \"{oficina}\" no está disponible en Síguelo Plus; "
                    "el título debe consultarse manualmente."
                )
                detalle = oficina_no_disponible
                logger.warning("Síguelo Plus: %s", oficina_no_disponible)

            log(f"[siguelo] título {year}-{number} -> {estado.value} ({len(documentos)} PDF)")

        enriquecidos.append({
            **seat,
            "documents": documentos,
            "document_status": estado.value,
            "document_detail": detalle,
        })

    return enriquecidos, _construir_auditoria(oficina, partida, enriquecidos, started)


def _construir_auditoria(
    oficina: str, partida: str, seats: list[dict[str, Any]], started: float
) -> AuditResult:
    total = len(seats)
    descargado = SunarpDocumentStatus.DOWNLOADED.value
    con_pdf = sum(1 for s in seats if s["document_status"] == descargado)
    archivos = sum(len(s["documents"]) for s in seats)
    pendientes = [f"{s['year']}-{s['number']}: {s['document_status']}" for s in seats if s["document_status"] != descargado]
    errores = {
        SunarpDocumentStatus.ERROR.value,
        SunarpDocumentStatus.OFFICE_NOT_AVAILABLE.value,
        SunarpDocumentStatus.YEAR_NOT_AVAILABLE.value,
    }

    if con_pdf:
        estado = AuditStatus.SUCCESS
    elif any(s["document_status"] in errores for s in seats):
        estado = AuditStatus.ERROR
    else:
        estado = AuditStatus.NO_DATA

    detalle = f"{con_pdf}/{total} títulos con PDF ({archivos} archivos)."
    if pendientes:
        detalle += " Pendientes: " + "; ".join(pendientes)

    return AuditResult(
        source_name=SOURCE_NAME_SIGUELO,
        query_parameter=f"{oficina} | {partida} | {total} títulos",
        duration_ms=int((time.perf_counter() - started) * 1000),
        status=estado,
        details=detalle,
        executed_at_utc=datetime.now(timezone.utc),
    )
