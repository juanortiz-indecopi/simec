"""Extractor SUNARP (SPRL) basado en agente LLM + MCP de Playwright.

El agente navega (login si hace falta, formulario, captcha, Buscar, Visualizar) y deja abierta la
"Lista de Asientos". La extracción del array es determinista: se toma un snapshot de la página y se
leen los títulos con una expresión regular, sin depender de que el LLM transcriba números.
"""
import asyncio
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from langchain_mcp_adapters.tools import load_mcp_tools

from app.application.port.out.sunarp_port import SunarpPort
from app.domain.models.audit import AuditResult, AuditStatus
from app.infrastructure.outbound.extractors.shared.browser import run_isolated
from app.infrastructure.outbound.extractors.sunarp.agent_runtime import (
    crear_modelo,
    correr_agente,
    sesion_playwright_mcp,
)
from app.infrastructure.outbound.extractors.sunarp.prompts import (
    MARCA_FALLIDA,
    MARCA_OK,
    MARCA_SIN_RESULTADOS,
    SYSTEM_PROMPT,
    construir_tarea_consulta,
)
from app.infrastructure.outbound.extractors.sunarp.tools import (
    crear_herramienta_captcha,
    crear_herramienta_credenciales,
    crear_herramienta_desplegable,
    filtrar_herramientas,
)

load_dotenv()

TITULO_PATTERN = re.compile(r"T[ií]tulo\s*:\s*(\d{4})\s*-\s*(\d+)", re.IGNORECASE)
TEXTO_PATTERN = re.compile(r"^[\w .\-áéíóúñÁÉÍÓÚÑ]{1,60}$")
PARTIDA_PATTERN = re.compile(r"^[A-Za-z0-9]{1,15}$")
_PERFIL_LOCK = threading.Lock()  # compartido entre hilos/loops (run_isolated usa hilos aparte)


def parse_titulos(texto: str) -> list[dict[str, str]]:
    """Extrae [{year, number, original_text}] de 'Titulo: 2015 - 00076288' sin duplicados."""
    vistos: set[tuple[str, str]] = set()
    titulos: list[dict[str, str]] = []
    for m in TITULO_PATTERN.finditer(texto):
        clave = (m.group(1), m.group(2))
        if clave in vistos:
            continue
        vistos.add(clave)
        titulos.append({"year": m.group(1), "number": m.group(2), "original_text": m.group(0)})
    return titulos


def _causa_raiz(exc: BaseException) -> BaseException:
    """anyio/mcp envuelven los fallos en ExceptionGroup: se muestra el error real."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def _validar_parametros(oficina: str, area: str, partida: str) -> None:
    # Los valores se insertan en el prompt del agente: se restringen para evitar inyección.
    if not TEXTO_PATTERN.match(oficina or ""):
        raise ValueError("Oficina registral inválida.")
    if not TEXTO_PATTERN.match(area or ""):
        raise ValueError("Área registral inválida.")
    if not PARTIDA_PATTERN.match(partida or ""):
        raise ValueError("Número de partida inválido.")


class SunarpAgentExtractor(SunarpPort):
    SOURCE_NAME = "SUNARP_SPRL"

    def __init__(self, max_pasos: int = 60, verbose: bool = False) -> None:
        self.sunarp_user = os.getenv("SUNARP_USER")
        self.sunarp_pass = os.getenv("SUNARP_PASS")
        self.max_pasos = max_pasos
        self.verbose = verbose
        self.headless = os.getenv("SUNARP_HEADLESS", "false").lower() == "true"
        # Un perfil persistente solo admite un navegador a la vez: no ejecutar consultas en paralelo.
        self.user_data_dir = os.getenv("SUNARP_AGENT_PROFILE_DIR", os.path.join(".cache", "sunarp_mcp_profile"))

    @property
    def source_name(self) -> str:
        return self.SOURCE_NAME

    def _registrar(self, linea: str) -> None:
        # La extracción corre en un hilo aparte y Jupyter no siempre muestra su print:
        # la traza se guarda siempre en .cache/agent_trace.log.
        with open(os.path.join(".cache", "agent_trace.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} {linea}\n")
        if self.verbose:
            print(linea, flush=True)

    async def extract(self, oficina: str, area: str, partida: str) -> dict[str, Any]:
        return await run_isolated(lambda: self._extract_impl(oficina, area, partida))

    async def _extract_impl(self, oficina: str, area: str, partida: str) -> dict[str, Any]:
        started = time.perf_counter()
        detalles: str | None = None
        titulos: list[dict[str, str]] = []
        estado = AuditStatus.ERROR
        lock_tomado = False

        try:
            _validar_parametros(oficina, area, partida)
            if not self.sunarp_user or not self.sunarp_pass:
                raise ValueError("Credenciales de SUNARP no configuradas en el entorno (.env).")

            # El perfil persistente de Chrome admite un solo navegador: las consultas se encolan.
            # Espera por sondeo (no bloquea el loop y es seguro ante cancelaciones).
            while not _PERFIL_LOCK.acquire(blocking=False):
                await asyncio.sleep(0.5)
            lock_tomado = True

            os.makedirs(self.user_data_dir, exist_ok=True)
            async with sesion_playwright_mcp(self.headless, self.user_data_dir) as session:
                tools = filtrar_herramientas(await load_mcp_tools(session))
                tools.append(crear_herramienta_credenciales(session, self.sunarp_user, self.sunarp_pass))
                tools.append(crear_herramienta_desplegable(session))
                tools.append(crear_herramienta_captcha(session, crear_modelo()))

                resultado = await correr_agente(
                    tools,
                    SYSTEM_PROMPT,
                    construir_tarea_consulta(oficina, area, partida),
                    max_pasos=self.max_pasos,
                    log=self._registrar,
                )
                final = resultado.final_message.strip()

                if final.startswith(MARCA_SIN_RESULTADOS):
                    estado = AuditStatus.NO_DATA
                    detalles = final
                elif final.startswith(MARCA_OK):
                    snapshot = await session.call_tool("browser_snapshot", {})
                    texto = "\n".join(getattr(c, "text", "") for c in snapshot.content)
                    titulos = parse_titulos(texto)
                    estado = AuditStatus.SUCCESS if titulos else AuditStatus.NO_DATA
                    if not titulos:
                        detalles = "La Lista de Asientos no contiene títulos legibles."
                else:
                    detalles = final or (
                        f"{MARCA_FALLIDA}: el agente no terminó dentro de {self.max_pasos} pasos."
                    )
        except Exception as exc:
            causa = _causa_raiz(exc)
            detalles = f"{type(causa).__name__}: {causa}"
            estado = AuditStatus.ERROR
        finally:
            if lock_tomado:
                _PERFIL_LOCK.release()

        return {
            "audit": AuditResult(
                source_name=self.SOURCE_NAME,
                query_parameter=f"{oficina} | {area} | {partida}",
                duration_ms=int((time.perf_counter() - started) * 1000),
                status=estado,
                details=detalles,
                executed_at_utc=datetime.now(timezone.utc),
            ),
            "data": {"seats": titulos},
        }
