import json
import re
from collections.abc import Callable
from datetime import timedelta
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool, tool
from mcp import ClientSession

# Solo herramientas de navegación; se excluyen evaluate / run_code_unsafe (ejecución arbitraria)
# y browser_take_screenshot (las imágenes las maneja la herramienta local del captcha).
HERRAMIENTAS_PERMITIDAS = {
    "browser_navigate", "browser_snapshot", "browser_click", "browser_type",
    "browser_fill_form", "browser_wait_for", "browser_press_key", "browser_find",
    "browser_select_option", "browser_tabs", "browser_handle_dialog", "browser_navigate_back",
}

LONGITUD_CAPTCHA = 6
PROMPT_CAPTCHA = (
    f"Transcribe los {LONGITUD_CAPTCHA} caracteres alfanuméricos (letras mayúsculas y dígitos) "
    "de esta imagen captcha. Responde SOLO con los caracteres, sin espacios ni explicación."
)


def filtrar_herramientas(mcp_tools: list[BaseTool]) -> list[BaseTool]:
    return [t for t in mcp_tools if t.name in HERRAMIENTAS_PERMITIDAS]


def _hay_error(res) -> bool:
    return bool(getattr(res, "is_error", getattr(res, "isError", False)))


def _texto_error(res) -> str:
    return " ".join(getattr(c, "text", "") for c in res.content)[:300]


def crear_herramienta_credenciales(session: ClientSession, usuario: str, clave: str) -> BaseTool:
    """Escribe usuario/clave en el navegador sin que el LLM los vea."""
    secretos = {"usuario": usuario, "clave": clave}

    @tool
    async def escribir_credencial(
        campo: Literal["usuario", "clave"], target: str, element: str = "campo de texto"
    ) -> str:
        """Escribe el usuario o la clave de SUNARP en un cuadro de texto, sin revelarlos.

        Args:
            campo: "usuario" o "clave".
            target: ref del textbox según el último snapshot.
            element: descripción legible del campo.
        """
        res = await session.call_tool(
            "browser_type", {"target": target, "element": element, "text": secretos[campo]}
        )
        if _hay_error(res):
            return f"ERROR al escribir {campo}: {_texto_error(res)}"
        return f"OK: {campo} escrito."

    return escribir_credencial


# El captcha no aparece en el árbol de accesibilidad (el único `img "number"` es el icono "#" del
# campo), así que se localiza por CSS. Estos scripts son fijos: nada del LLM se interpola en ellos.
# `.first()` = sección "Búsqueda Directa por Número de Partida o de Ficha" (primera del DOM).
JS_CAPTURAR_CAPTCHA = """async (page) => {
  const img = page.locator('app-captcha-sunarp img.img-captcha').first();
  await img.waitFor({ state: 'visible', timeout: 10000 });
  await page.waitForTimeout(500);
  const buf = await img.screenshot({ type: 'png' });
  return buf.toString('base64');
}"""

JS_RECARGAR_CAPTCHA = """async (page) => {
  await page.locator('app-captcha-sunarp a[color="warn"]').first().click({ force: true });
  await page.waitForTimeout(1200);
  return 'recargado';
}"""

JS_ESCRIBIR_CAPTCHA = """async (page) => {
  const input = page.locator('app-captcha-sunarp input').first();
  await input.click();
  await input.fill('');
  await input.pressSequentially('%s', { delay: 50 });
  return 'escrito';
}"""

# Desplegables nz-select: 0 = Oficina Registral, 1 = Área registral. Las opciones se renderizan en
# un overlay al final del body. Se compara sin tildes ("Personas Jurídicas" vs "Personas Juridicas").
# Los valores se inyectan con json.dumps (escapado) tras validarse en el extractor.
JS_SELECCIONAR = """async (page) => {
  const idx = %(idx)d;
  const wanted = %(wanted)s;
  const norm = s => s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().replace(/\\s+/g, ' ').trim();
  const target = norm(wanted);
  const select = page.locator('nz-select').nth(idx);
  await select.waitFor({ state: 'visible', timeout: 10000 });
  await select.click();
  await page.waitForTimeout(500);
  const search = select.locator('input').first();
  // Solo la oficina tiene buscador editable; en el resto se omite sin esperar.
  if (await search.count() > 0) {
    await search.fill(wanted.normalize('NFD').replace(/[\\u0300-\\u036f]/g, ''), { timeout: 1500 }).catch(() => {});
  }
  await page.waitForTimeout(700);
  const items = page.locator('nz-option-item');
  // La lista es virtual (solo renderiza las opciones visibles): si no aparece, se desplaza y reintenta.
  const viewport = page.locator('cdk-virtual-scroll-viewport, .ant-select-dropdown .rc-virtual-list-holder').first();
  let pick = -1, n = 0;
  for (let paso = 0; paso < 8 && pick < 0; paso++) {
    n = await items.count();
    for (let i = 0; i < n; i++) {
      const t = norm((await items.nth(i).getAttribute('title')) || (await items.nth(i).innerText()));
      if (t === target) { pick = i; break; }
      if (pick < 0 && t.includes(target)) pick = i;
    }
    if (pick >= 0 || await viewport.count() === 0) break;
    await viewport.evaluate(el => { el.scrollTop += el.clientHeight * 0.8; });
    await page.waitForTimeout(400);
  }
  if (pick < 0) throw new Error('No existe la opcion "' + wanted + '" (' + n + ' opciones visibles)');
  await items.nth(pick).evaluate(el => el.click());
  await page.waitForTimeout(1500);
  const actual = (await select.innerText()).trim();
  if (!norm(actual).includes(target)) throw new Error('La seleccion no se aplico; el campo muestra: ' + actual);
  return 'seleccionado: ' + actual;
}"""

CAMPOS_DESPLEGABLE = {"oficina": 0, "area": 1}

BASE64_PATTERN = re.compile(r"[A-Za-z0-9+/=]{500,}")
MAX_INTENTOS_LECTURA = 3


async def _ejecutar_js(session: ClientSession, codigo: str) -> str:
    res = await session.call_tool("browser_run_code_unsafe", {"code": codigo})
    texto = "\n".join(getattr(c, "text", "") for c in res.content)
    if _hay_error(res) or "### Error" in texto:
        raise RuntimeError(texto[:300])
    return texto


def _texto_de(respuesta) -> str:
    c = respuesta.content
    return c if isinstance(c, str) else " ".join(b.get("text", "") for b in c if isinstance(b, dict))


def crear_herramienta_desplegable(session: ClientSession) -> BaseTool:
    """Selecciona Oficina o Área en los desplegables del formulario de forma determinista."""

    @tool
    async def seleccionar_desplegable(campo: Literal["oficina", "area"], texto: str) -> str:
        """Selecciona una opción en el desplegable "Oficina Registral" o "Area registral".

        Abre el desplegable, filtra, elige la opción (ignora tildes y mayúsculas) y verifica que
        el campo la muestre. Úsala en lugar de hacer clics manuales en esos desplegables.

        Args:
            campo: "oficina" o "area".
            texto: nombre de la opción, p.ej. "CUSCO" o "Personas Juridicas".
        """
        if not re.fullmatch(r"[\w .\-()áéíóúñÁÉÍÓÚÑ]{1,100}", texto):
            return "ERROR: texto de opción inválido."
        codigo = JS_SELECCIONAR % {"idx": CAMPOS_DESPLEGABLE[campo], "wanted": json.dumps(texto)}
        try:
            return "OK: " + (await _ejecutar_js(session, codigo)).replace("\n", " ")[:200]
        except Exception as exc:
            return f"ERROR: {exc}"

    return seleccionar_desplegable


# Síguelo Plus: el botón "ojo" de cada fila abre una pestaña blob: con el PDF ya descifrado (la API
# lo entrega cifrado con AES de CryptoJS). El LLM no puede leer un blob, así que esta parte es una
# herramienta fija: abre cada fila, lee el blob desde la pestaña que lo creó y lo devuelve en base64
# (el sandbox de browser_run_code_unsafe no tiene `require` para escribir archivos).
JS_DESCARGAR_ASIENTOS = r"""async (page) => {
  const ctx = page.context();
  const filas = page.locator('mat-dialog-container tbody tr');
  try {
    await filas.first().waitFor({ state: 'visible', timeout: 15000 });
  } catch (e) {
    return { documents: [], fallos: ['el modal "Asientos de Inscripción" no está abierto o no lista partidas'] };
  }
  const documents = [], fallos = [];
  const total = await filas.count();
  for (let i = 0; i < total; i++) {
    const fila = filas.nth(i);
    const celdas = await fila.locator('td').allInnerTexts();
    const partida = (celdas[1] || '').trim() || ('fila' + (i + 1));
    const ojo = fila.locator('button').first();
    if (await ojo.count() === 0) { fallos.push(partida + ': sin botón de visualización'); continue; }
    try {
      const popupPromesa = ctx.waitForEvent('page', { timeout: 120000 });
      await ojo.click({ timeout: 10000 });
      const popup = await popupPromesa;
      await popup.waitForURL(/^blob:/, { timeout: 30000 }).catch(() => {});
      const url = popup.url();
      const leer = async (pagina) => pagina.evaluate(async (u) => {
        const blob = await (await fetch(u)).blob();
        const dataUrl = await new Promise((ok, ko) => {
          const r = new FileReader();
          r.onload = () => ok(r.result);
          r.onerror = () => ko(r.error);
          r.readAsDataURL(blob);
        });
        return { b64: dataUrl.slice(dataUrl.indexOf(',') + 1), size: blob.size };
      }, url);
      let pdf;
      try { pdf = await leer(page); } catch (e) { pdf = await leer(popup); }
      await popup.close().catch(() => {});
      documents.push({ partida, b64: pdf.b64, size: pdf.size });
    } catch (e) {
      fallos.push(partida + ': ' + String((e && e.message) || e).split('\n')[0].slice(0, 160));
    }
  }
  for (const p of ctx.pages()) if (p !== page) await p.close().catch(() => {});
  return { documents, fallos };
}"""

_RESULT_RE = re.compile(r"### Result\s*\n(.*?)(?:\n### |\Z)", re.DOTALL)


def crear_herramienta_descarga_asientos(
    session: ClientSession, al_descargar: Callable[[list[dict]], list[dict]]
) -> BaseTool:
    """Descarga los PDF del modal "Asientos de Inscripción" de Síguelo Plus.

    `al_descargar` recibe [{partida, b64, size}], persiste los PDF y devuelve lo guardado.
    """

    @tool
    async def descargar_asientos_inscripcion() -> str:
        """Descarga y guarda el PDF de cada partida del modal "Asientos de Inscripción".

        Úsala cuando el modal "Asientos de Inscripción" esté abierto. No requiere argumentos:
        pulsa por sí misma el botón del ojo de cada fila y guarda los PDF.
        """
        try:
            res = await session.call_tool(
                "browser_run_code_unsafe",
                {"code": JS_DESCARGAR_ASIENTOS},
                read_timeout_seconds=timedelta(seconds=300),
            )
            texto = "\n".join(getattr(c, "text", "") for c in res.content)
            if _hay_error(res) or "### Error" in texto:
                return f"ERROR: {' '.join(texto.split())[:300]}"
            m = _RESULT_RE.search(texto)
            if not m:
                return "ERROR: la herramienta no devolvió resultado."
            datos = json.loads(m.group(1).strip())
            guardados = al_descargar(datos.get("documents") or [])
            fallos = datos.get("fallos") or []
            if not guardados:
                return "ERROR: no se obtuvo ningún PDF. " + " | ".join(fallos)
            partidas = ", ".join(g["partida"] for g in guardados)
            extra = (" Fallos: " + " | ".join(fallos)) if fallos else ""
            return f"OK: {len(guardados)} PDF guardado(s) (partidas: {partidas}).{extra}"
        except Exception as exc:
            return f"ERROR: {type(exc).__name__}: {exc}"

    return descargar_asientos_inscripcion


def crear_herramienta_captcha(session: ClientSession, modelo_vision: BaseChatModel) -> BaseTool:
    """Fotografía el captcha, lo lee con un LLM de visión y lo escribe en su campo."""

    @tool
    async def resolver_captcha() -> str:
        """Lee el captcha de imagen de la búsqueda por partida y escribe su valor en su campo.

        No requiere argumentos: localiza la imagen y el campo por sí misma y, si no logra leer el
        captcha, lo recarga y reintenta internamente. Después de un OK, pulsa Buscar.
        """
        ultimo_error = ""
        for intento in range(1, MAX_INTENTOS_LECTURA + 1):
            try:
                crudo = await _ejecutar_js(session, JS_CAPTURAR_CAPTCHA)
                m = BASE64_PATTERN.search(crudo)
                if not m:
                    raise RuntimeError("la captura no devolvió datos de imagen")
                respuesta = await modelo_vision.ainvoke([HumanMessage(content=[
                    {"type": "text", "text": PROMPT_CAPTCHA},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{m.group(0)}"}},
                ])])
                bruto = _texto_de(respuesta)
                valor = re.sub(r"[^A-Z0-9]", "", bruto.upper())
                if len(valor) == LONGITUD_CAPTCHA:
                    await _ejecutar_js(session, JS_ESCRIBIR_CAPTCHA % valor)
                    return f"OK: captcha '{valor}' escrito. Ahora pulsa Buscar."
                ultimo_error = f"ilegible (respuesta del modelo: '{' '.join(bruto.split())[:60]}')"
            except Exception as exc:
                ultimo_error = f"{type(exc).__name__}: {exc}"
            if intento < MAX_INTENTOS_LECTURA:
                try:
                    await _ejecutar_js(session, JS_RECARGAR_CAPTCHA)
                except Exception:
                    pass
        return f"ERROR: no se pudo resolver el captcha tras {MAX_INTENTOS_LECTURA} intentos: {ultimo_error}"

    return resolver_captcha
