"""Extractor de perfiles de LinkedIn basado en agente LLM + MCP de Playwright.

`iniciar_sesion` hace el login (una persona completa el captcha si aparece) y `extract` descarga el PDF
del perfil, lo convierte en dict y lo borra. La lectura es determinista: el LLM no transcribe datos.
"""
import asyncio
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from langchain_mcp_adapters.tools import load_mcp_tools

from app.application.port.out.extractor_port import ExtractorPort
from app.domain.models.audit import AuditResult, AuditStatus
from app.infrastructure.outbound.extractors.linkedin.pdf_parser import parse_perfil_pdf
from app.infrastructure.outbound.extractors.linkedin.prompts import (
    LOGIN_SYSTEM_PROMPT,
    LOGIN_TAREA,
    MARCA_FALLIDA,
    MARCA_NO_ENCONTRADO,
    MARCA_OK,
    MARCA_SESION,
    MARCA_VERIFICACION,
    SYSTEM_PROMPT,
    TAREA,
)
from app.infrastructure.outbound.extractors.linkedin.tools import (
    JS_CABECERA,
    JS_HAY_SESION,
    crear_herramientas_login,
    crear_herramientas_perfil,
    ejecutar_js,
    filtrar_herramientas,
    sesion_activa,
)
from app.infrastructure.outbound.extractors.linkedin.session import sesion_linkedin
from app.infrastructure.outbound.extractors.shared.browser import run_isolated
from app.infrastructure.outbound.extractors.sunarp.agent_runtime import correr_agente

load_dotenv()

USERNAME_PATTERN = re.compile(r"^[\w-]{3,100}$")
SEGUIDORES_PATTERN = re.compile(r"([\d.,\s ]*\d)\s*(?:seguidores|followers)", re.IGNORECASE)
CONTACTOS_PATTERN = re.compile(
    r"((?:Más de\s*)?\d[\d.,]*\+?)\s*(?:contactos|connections)", re.IGNORECASE
)
_PERFIL_LOCK = threading.Lock()  # compartido entre hilos/loops (run_isolated usa hilos aparte)


def parse_cabecera(datos: dict[str, Any]) -> dict[str, Any]:
    """Datos visibles en la página que el PDF no trae: seguidores, contactos, foto y portada."""
    texto = datos.get("text") or ""
    seguidores = SEGUIDORES_PATTERN.search(texto)
    contactos = CONTACTOS_PATTERN.search(texto)
    return {
        "followers": int(re.sub(r"\D", "", seguidores.group(1))) if seguidores else None,
        "connections": contactos.group(1).strip() if contactos else None,
        "photo_url": datos.get("photo_url"),
        "cover_url": datos.get("cover_url"),
    }


def _causa_raiz(exc: BaseException) -> BaseException:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


class LinkedinAgentExtractor(ExtractorPort):
    SOURCE_NAME = "LINKEDIN_PROFILE"

    def __init__(self, max_pasos: int = 40, verbose: bool = False) -> None:
        self.usuario = os.getenv("LINKEDIN_USER")
        self.clave = os.getenv("LINKEDIN_PASS")
        self.max_pasos = max_pasos
        self.verbose = verbose
        self.headless = os.getenv("LINKEDIN_HEADLESS", "false").lower() == "true"
        self.user_data_dir = os.getenv(
            "LINKEDIN_AGENT_PROFILE_DIR", os.path.join(".cache", "linkedin_mcp_profile")
        )

    @property
    def source_name(self) -> str:
        return self.SOURCE_NAME

    def _registrar(self, linea: str) -> None:
        os.makedirs(".cache", exist_ok=True)
        with open(os.path.join(".cache", "agent_trace.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} [linkedin] {linea}\n")
        if self.verbose:
            print(linea, flush=True)

    async def _tomar_perfil(self) -> None:
        # El perfil persistente de Chrome admite un solo navegador: las consultas se encolan.
        if _PERFIL_LOCK.acquire(blocking=False):
            return
        self._registrar("Otra operación de LinkedIn está usando el navegador; esperando...")
        while not _PERFIL_LOCK.acquire(blocking=False):
            await asyncio.sleep(0.5)

    def _auditoria(
        self, parametro: str, started: float, estado: AuditStatus, detalles: str | None
    ) -> AuditResult:
        return AuditResult(
            source_name=self.SOURCE_NAME,
            query_parameter=parametro,
            duration_ms=int((time.perf_counter() - started) * 1000),
            status=estado,
            details=detalles,
            executed_at_utc=datetime.now(timezone.utc),
        )

    async def iniciar_sesion(self) -> AuditResult:
        """Login con las credenciales del .env; si hay captcha espera a que una persona lo resuelva."""
        return await run_isolated(self._iniciar_sesion_impl)

    async def _iniciar_sesion_impl(self) -> AuditResult:
        started = time.perf_counter()
        estado, detalles = AuditStatus.ERROR, None
        lock_tomado = False
        try:
            if not self.usuario or not self.clave:
                raise ValueError("Credenciales de LinkedIn no configuradas en el entorno (.env).")
            await self._tomar_perfil()
            lock_tomado = True
            async with sesion_linkedin(self.headless, self.user_data_dir) as session:
                if await sesion_activa(session):
                    estado, detalles = AuditStatus.SUCCESS, "La sesión ya estaba activa."
                else:
                    tools = filtrar_herramientas(await load_mcp_tools(session))
                    tools += crear_herramientas_login(
                        session,
                        usuario=self.usuario,
                        clave=self.clave,
                        headless=self.headless,
                        log=self._registrar,
                    )
                    resultado = await correr_agente(
                        tools, LOGIN_SYSTEM_PROMPT, LOGIN_TAREA,
                        max_pasos=self.max_pasos, log=self._registrar,
                    )
                    # No se confía en lo que diga el agente: se comprueba la sesión.
                    if await ejecutar_js(session, JS_HAY_SESION) and await sesion_activa(session):
                        estado, detalles = AuditStatus.SUCCESS, "Sesión iniciada."
                    else:
                        detalles = resultado.final_message.strip() or (
                            f"{MARCA_VERIFICACION}: no se completó el acceso."
                        )
        except Exception as exc:
            causa = _causa_raiz(exc)
            if estado is not AuditStatus.SUCCESS:
                detalles = f"{type(causa).__name__}: {causa}"
        finally:
            if lock_tomado:
                _PERFIL_LOCK.release()
        return self._auditoria("login", started, estado, detalles)

    async def extract(self, parameter: str) -> dict[str, Any]:
        """`parameter`: nombre de usuario, p.ej. "rosanaferrero" de linkedin.com/in/rosanaferrero."""
        return await run_isolated(lambda: self._extract_impl(parameter))

    async def _extract_impl(self, username: str) -> dict[str, Any]:
        started = time.perf_counter()
        detalles: str | None = None
        estado = AuditStatus.ERROR
        perfil: dict[str, Any] | None = None
        pdf_datos: dict[str, Any] | None = None
        temporales: list[str] = []
        lock_tomado = False

        def procesar(ruta: str) -> None:
            """Lee el PDF temporal; nunca se copia a otra ubicación."""
            nonlocal pdf_datos
            temporales.append(ruta)
            with open(ruta, "rb") as f:
                if f.read(5) != b"%PDF-":
                    raise ValueError("el archivo descargado no es un PDF")
            datos = parse_perfil_pdf(ruta)
            if not datos["full_name"]:
                raise ValueError("el PDF no tiene el formato esperado de LinkedIn")
            pdf_datos = datos

        try:
            username = (username or "").strip()
            if not USERNAME_PATTERN.match(username):
                raise ValueError("Nombre de usuario de LinkedIn inválido.")
            await self._tomar_perfil()
            lock_tomado = True
            url_perfil = f"https://www.linkedin.com/in/{quote(username)}/"

            async with sesion_linkedin(self.headless, self.user_data_dir) as session:
                if not await sesion_activa(session):
                    raise PermissionError(f"{MARCA_SESION}: ejecuta primero iniciar_sesion().")
                tools = filtrar_herramientas(await load_mcp_tools(session))
                tools += crear_herramientas_perfil(
                    session, url_perfil=url_perfil, al_descargar=procesar
                )
                resultado = await correr_agente(
                    tools, SYSTEM_PROMPT, TAREA, max_pasos=self.max_pasos, log=self._registrar
                )
                final = resultado.final_message.strip()

                if pdf_datos is not None:
                    cabecera: dict[str, Any] = {}
                    try:
                        cabecera = await ejecutar_js(session, JS_CABECERA)
                    except Exception as exc:  # datos complementarios: no invalidan el PDF
                        detalles = f"Cabecera no disponible: {str(exc)[:200]}"
                    perfil = {
                        "username": username,
                        "profile_url": url_perfil,
                        **pdf_datos,
                        **parse_cabecera(cabecera),
                    }
                    estado = AuditStatus.SUCCESS
                elif final.startswith(MARCA_NO_ENCONTRADO):
                    estado, detalles = AuditStatus.NO_DATA, final
                elif final.startswith(MARCA_OK):
                    detalles = "El agente informó éxito, pero no se descargó ningún PDF."
                else:
                    detalles = final or (
                        f"{MARCA_FALLIDA}: el agente no terminó dentro de {self.max_pasos} pasos."
                    )
        except Exception as exc:
            causa = _causa_raiz(exc)
            # Un fallo al cerrar el navegador no invalida un perfil ya extraído.
            if estado is not AuditStatus.SUCCESS:
                detalles = f"{type(causa).__name__}: {causa}"
                perfil = None
        finally:
            for ruta in temporales:
                try:
                    os.remove(ruta)
                except FileNotFoundError:
                    pass  # ya borrado al cerrar el navegador
                except OSError as exc:
                    self._registrar(f"No se pudo borrar el PDF temporal: {exc}")
            if lock_tomado:
                _PERFIL_LOCK.release()

        return {
            "audit": self._auditoria(username, started, estado, detalles),
            "data": perfil,
            "raw": perfil,
        }
