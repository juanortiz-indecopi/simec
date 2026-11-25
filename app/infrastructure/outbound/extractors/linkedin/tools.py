import asyncio
import json
import re
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Literal
from urllib.parse import urlsplit

from langchain_core.tools import BaseTool, tool
from mcp import ClientSession

# Sin browser_navigate (solo URLs fijas vía abrir_perfil/abrir_login), sin browser_type (lo único
# que se escribe son las credenciales) y sin ejecución de código.
HERRAMIENTAS_PERMITIDAS = {
    "browser_snapshot", "browser_click", "browser_wait_for", "browser_press_key", "browser_find",
}
URL_LOGIN = "https://www.linkedin.com/login"
URL_FEED = "https://www.linkedin.com/feed/"
RUTAS_SIN_SESION = ("/login", "/checkpoint", "/uas", "/authwall", "/signup")
ESPERA_VERIFICACION_S = 300

_RESULT_RE = re.compile(r"### Result\s*\n(.*?)(?:\n### |\Z)", re.DOTALL)

JS_URL = "async (page) => page.url()"

# Solo informa de si existe la cookie de sesión; nunca devuelve su valor.
JS_HAY_SESION = """async (page) => (await page.context().cookies('https://www.linkedin.com'))
  .some(c => c.name === 'li_at' && c.value)"""

JS_DESCARGAR_PDF = r"""async (page) => {
  const opciones = page.getByText(/^\s*(Guardar en PDF|Guardar como PDF|Save to PDF)\s*$/i);
  let opcion = null;
  for (let i = 0; i < await opciones.count(); i++) {
    if (await opciones.nth(i).isVisible()) { opcion = opciones.nth(i); break; }
  }
  if (!opcion) throw new Error('la opcion "Guardar en PDF" no esta visible: abre antes el menu Mas');
  const espera = page.waitForEvent('download', { timeout: 60000 });
  espera.catch(() => {});
  await opcion.click({ timeout: 10000 });
  const descarga = await espera;
  const fallo = await descarga.failure();
  if (fallo) throw new Error('la descarga fallo: ' + fallo);
  return { path: await descarga.path(), name: descarga.suggestedFilename() };
}"""

# Datos de la cabecera que el PDF no incluye.
JS_CABECERA = r"""async (page) => page.evaluate(() => {
  const main = document.querySelector('main') || document.body;
  const foto = main.querySelector('img[src*="profile-displayphoto"]');
  const portada = main.querySelector('img[src*="profile-displaybackgroundimage"]');
  return {
    url: location.href,
    text: main.innerText.slice(0, 3000),
    photo_url: foto ? foto.src : null,
    cover_url: portada ? portada.src : null,
  };
})"""


def filtrar_herramientas(mcp_tools: list[BaseTool]) -> list[BaseTool]:
    return [t for t in mcp_tools if t.name in HERRAMIENTAS_PERMITIDAS]


def _texto(res) -> str:
    return "\n".join(getattr(c, "text", "") for c in res.content)


def _hay_error(res) -> bool:
    return bool(getattr(res, "is_error", getattr(res, "isError", False)))


async def ejecutar_js(session: ClientSession, codigo: str, timeout_s: int = 90) -> Any:
    """Ejecuta un script fijo (nunca con contenido del LLM) y devuelve su resultado JSON."""
    res = await session.call_tool(
        "browser_run_code_unsafe", {"code": codigo}, read_timeout_seconds=timedelta(seconds=timeout_s)
    )
    texto = _texto(res)
    m = _RESULT_RE.search(texto)
    if _hay_error(res) or texto.lstrip().startswith("### Error") or not m:
        raise RuntimeError(" ".join(texto.split())[:300] or "sin resultado")
    return json.loads(m.group(1).strip())


def es_linkedin(url: str) -> bool:
    partes = urlsplit(url)
    host = partes.hostname or ""
    return partes.scheme == "https" and (host == "linkedin.com" or host.endswith(".linkedin.com"))


async def sesion_activa(session: ClientSession) -> bool:
    """LinkedIn mantiene /feed solo si hay sesión; si no, redirige al acceso."""
    await session.call_tool("browser_navigate", {"url": URL_FEED})
    await asyncio.sleep(2)
    url = await ejecutar_js(session, JS_URL)
    return es_linkedin(url) and urlsplit(url).path.startswith("/feed")


async def esperar_sesion(session: ClientSession, log: Callable[[str], None]) -> bool:
    """Espera a que una persona complete el acceso (verificación incluida) en la ventana de Chrome."""
    log(
        ">>> ACCIÓN REQUERIDA: completa el acceso a LinkedIn en la ventana de Chrome "
        f"(verificación e Iniciar sesión). Tienes {ESPERA_VERIFICACION_S // 60} minutos."
    )
    limite = time.monotonic() + ESPERA_VERIFICACION_S
    while time.monotonic() < limite:
        await asyncio.sleep(3)
        try:
            url = await ejecutar_js(session, JS_URL)
            hay_sesion = await ejecutar_js(session, JS_HAY_SESION)
        except Exception:
            continue  # la página está navegando
        if hay_sesion and es_linkedin(url) and not urlsplit(url).path.startswith(RUTAS_SIN_SESION):
            return True
    return False


async def _navegar(session: ClientSession, url: str) -> str:
    res = await session.call_tool("browser_navigate", {"url": url})
    if _hay_error(res):
        return f"ERROR al navegar: {_texto(res)[:300]}"
    return f"OK: URL actual: {await ejecutar_js(session, JS_URL)}"


def crear_herramientas_login(
    session: ClientSession, *, usuario: str, clave: str, headless: bool, log: Callable[[str], None]
) -> list[BaseTool]:
    secretos = {"usuario": usuario, "clave": clave}

    @tool
    async def abrir_login() -> str:
        """Abre la página de inicio de sesión de LinkedIn. No requiere argumentos."""
        return await _navegar(session, URL_LOGIN)

    @tool
    async def escribir_credencial(
        campo: Literal["usuario", "clave"], target: str, element: str = "campo de texto"
    ) -> str:
        """Escribe el usuario o la clave de LinkedIn en un cuadro de texto, sin revelarlos.

        Args:
            campo: "usuario" o "clave".
            target: ref del textbox según el último snapshot.
            element: descripción legible del campo.
        """
        if not es_linkedin(await ejecutar_js(session, JS_URL)):
            return "ERROR: la página actual no es de LinkedIn; no se escriben credenciales."
        res = await session.call_tool(
            "browser_type", {"target": target, "element": element, "text": secretos[campo]}
        )
        if _hay_error(res):
            # El detalle del error puede incluir el texto escrito: no se devuelve al LLM.
            return f"ERROR al escribir {campo}: revisa el target con un nuevo snapshot."
        return f"OK: {campo} escrito."

    @tool
    async def esperar_verificacion_humana() -> str:
        """Espera a que una persona complete la verificación de seguridad en la ventana del navegador."""
        if headless:
            return "ERROR: navegador sin ventana; ejecuta con LINKEDIN_HEADLESS=false para verificar a mano."
        if await esperar_sesion(session, log):
            return "OK: verificación completada."
        return f"ERROR: nadie completó la verificación en {ESPERA_VERIFICACION_S} s."

    return [abrir_login, escribir_credencial, esperar_verificacion_humana]


def crear_herramientas_perfil(
    session: ClientSession, *, url_perfil: str, al_descargar: Callable[[str], None]
) -> list[BaseTool]:
    @tool
    async def abrir_perfil() -> str:
        """Abre el perfil de LinkedIn a consultar. No requiere argumentos."""
        return await _navegar(session, url_perfil)

    @tool
    async def descargar_pdf() -> str:
        """Pulsa "Guardar en PDF" y procesa el archivo. Requiere el menú "Más" del perfil abierto."""
        try:
            datos = await ejecutar_js(session, JS_DESCARGAR_PDF)
            al_descargar(datos["path"])
            return "OK: PDF procesado."
        except Exception as exc:
            return f"ERROR: {type(exc).__name__}: {str(exc)[:300]}"

    return [abrir_perfil, descargar_pdf]
