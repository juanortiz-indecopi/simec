import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import ddddocr
from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright

load_dotenv()

from app.infrastructure.outbound.extractors.shared.browser import run_isolated
from app.domain.models.audit import AuditResult, AuditStatus
from app.application.port.out.sunarp_port import SunarpPort

ocr_engine = ddddocr.DdddOcr(show_ad=False)


def resolver_captcha_imagen(imagen_bytes: bytes) -> str:
    texto = ocr_engine.classification(imagen_bytes)
    return re.sub(r'[^A-Z0-9]', '', texto.upper())


async def cerrar_modal_publicitario(page: Page):
    await page.wait_for_timeout(1000)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(400)
    selectores_x = ["nz-modal-close", "button[aria-label*='Close' i]", "span:has-text('×')"]
    for sel in selectores_x:
        loc = page.locator(sel).first
        if await loc.count() > 0 and await loc.is_visible():
            try:
                await loc.click(timeout=1000)
                await page.wait_for_timeout(500)
                return
            except Exception:
                pass
    await page.mouse.click(15, 15)


async def clicar_checkbox_turnstile(page: Page) -> bool:
    selectores = ["iframe[src*='cloudflare']", "iframe[src*='turnstile']", "div.cf-turnstile"]
    for sel in selectores:
        loc = page.locator(sel).first
        if await loc.count() > 0 and await loc.is_visible():
            box = await loc.bounding_box()
            if box:
                x = box["x"] + 32
                y = box["y"] + (box["height"] / 2)
                await page.mouse.move(x, y, steps=10)
                await page.wait_for_timeout(150)
                await page.mouse.click(x, y)
                return True
    return False


class SunarpExtractor(SunarpPort):
    SOURCE_NAME = "SUNARP_SPRL"

    def __init__(self):
        self.url_objetivo = "https://sprl.sunarp.gob.pe/sprl/main/partidas-base-grafica-registral"
        self.sunarp_user = os.getenv("SUNARP_USER")
        self.sunarp_pass = os.getenv("SUNARP_PASS")

    @property
    def source_name(self) -> str:
        return self.SOURCE_NAME

    async def extract(self, oficina: str, area: str, partida: str) -> dict[str, Any]:
        return await run_isolated(lambda: self._extract_impl(oficina, area, partida))

    async def _extract_impl(self, oficina: str, area: str, partida: str) -> dict[str, Any]:
        started = time.perf_counter()
        detalles_error = None
        titulos_asientos = []
        estado_auditoria = AuditStatus.ERROR

        try:
            async with async_playwright() as p:
                # Chrome real + perfil persistente, sin UA falso ni parches stealth:
                # Cloudflare compara UA, client hints y TLS, y un Chrome genuino pasa solo.
                # En servidor Linux usar Xvfb (display virtual) en vez de headless.
                modo_oculto = os.getenv("SUNARP_HEADLESS", "false").lower() == "true"
                perfil_dir = os.getenv("SUNARP_PROFILE_DIR", os.path.join(".cache", "sunarp_profile"))
                os.makedirs(perfil_dir, exist_ok=True)

                context = await p.chromium.launch_persistent_context(
                    user_data_dir=perfil_dir,
                    channel="chrome",
                    headless=modo_oculto,
                    viewport={"width": 1366, "height": 768},
                    locale="es-PE",
                    ignore_default_args=["--enable-automation"],
                )
                page = context.pages[0] if context.pages else await context.new_page()

                try:
                    await page.goto(self.url_objetivo, wait_until="domcontentloaded", timeout=30000)

                    # Esperar a que la SPA decida: sesión activa (formulario) o redirección al login.
                    sesion_activa = page.get_by_text("Búsqueda Directa por Número de Partida").first
                    portada = page.get_by_role("button", name=re.compile("INGRESAR"))
                    for _ in range(40):
                        if await sesion_activa.count() > 0 or await portada.count() > 0 or "autorizacion" in page.url:
                            break
                        await page.wait_for_timeout(500)

                    if await sesion_activa.count() == 0:
                        if not self.sunarp_user or not self.sunarp_pass:
                            raise ValueError("Credenciales de SUNARP no configuradas en el entorno (.env).")

                        if "autorizacion" not in page.url:
                            await cerrar_modal_publicitario(page)
                            await portada.first.click()
                            await page.wait_for_url(re.compile("autorizacion"), timeout=20000)

                        await page.get_by_role("textbox", name="Usuario").fill(self.sunarp_user)
                        await page.get_by_role("textbox", name="Contraseña").fill(self.sunarp_pass)

                        # Turnstile: con Chrome real se resuelve solo; el clic es solo respaldo.
                        for intento in range(20):
                            if await page.evaluate("() => { const el = document.querySelector('input[name=\"cf-turnstile-response\"]'); return el ? el.value : ''; }"):
                                break
                            if intento in (8, 14):
                                await clicar_checkbox_turnstile(page)
                            await page.wait_for_timeout(1000)

                        await page.get_by_role("button", name="INGRESAR", exact=True).click()

                        try:
                            await page.wait_for_url(re.compile(r"sprl\.sunarp\.gob\.pe/sprl/(oauth|main)"), timeout=25000)
                        except Exception:
                            alerta_error = page.locator(".ant-message-custom-content, nz-message, .swal2-html-container, [role='alert']").first
                            if await alerta_error.count() > 0 and await alerta_error.is_visible():
                                raise ValueError(f"SUNARP rechazó el acceso: {await alerta_error.inner_text()}")
                            raise ValueError("El login no avanzó. SUNARP está lento o Cloudflare bloqueó el acceso.")

                    if "partidas-base-grafica-registral" not in page.url:
                        await page.goto(self.url_objetivo, wait_until="domcontentloaded", timeout=30000)
                    
                    await page.locator("text=Búsqueda Directa por Número de Partida").first.wait_for(state="visible", timeout=20000)
                    await page.wait_for_timeout(1000)

                    for intento in range(15):
                        if await page.evaluate("() => { const el = document.querySelector('input[name=\"cf-turnstile-response\"]'); return el ? el.value : ''; }"):
                            break
                        if intento in (2, 5, 8):
                            await clicar_checkbox_turnstile(page)
                        await page.wait_for_timeout(1000)

                    cajas_select = page.locator("nz-select")
                    await cajas_select.first.wait_for(state="visible", timeout=15000)

                    await cajas_select.nth(0).click()
                    await page.wait_for_timeout(1000)
                    await page.keyboard.type(oficina, delay=50)
                    await page.wait_for_timeout(800)
                    
                    opc_oficina = page.locator(f"nz-option-item[title*='{oficina}' i]").first
                    if await opc_oficina.count() > 0:
                        await opc_oficina.evaluate("el => el.click()")
                    else:
                        await page.keyboard.press("Enter")
                    await page.wait_for_timeout(1000)

                    await cajas_select.nth(1).click()
                    await page.wait_for_timeout(1000)
                    
                    param_area_safe = "Personas Jur" if "Jur" in area else area
                    await page.keyboard.type(param_area_safe, delay=50)
                    await page.wait_for_timeout(800)
                    
                    opc_area = page.locator(f"nz-option-item[title*='{param_area_safe}' i]").first
                    if await opc_area.count() > 0:
                        await opc_area.evaluate("el => el.click()")
                    else:
                        await page.keyboard.press("Enter")
                        
                    await page.wait_for_timeout(2500) 

                    radio_partida = page.locator("label:has-text('Partida')").first
                    await radio_partida.wait_for(state="attached", timeout=5000)
                    await radio_partida.scroll_into_view_if_needed()
                    await page.wait_for_timeout(800)
                    await radio_partida.evaluate("el => el.click()")
                    await page.wait_for_timeout(1500)

                    input_numero = page.locator("#numero").first
                    await input_numero.wait_for(state="visible", timeout=5000)
                    await input_numero.click()
                    await page.keyboard.press("Control+A") 
                    await page.keyboard.press("Backspace")
                    await input_numero.fill("")
                    await input_numero.press_sequentially(partida, delay=50)
                    await input_numero.press("Tab")  
                    await page.wait_for_timeout(500)

                    contenedor_captcha = page.locator("app-captcha-sunarp").first
                    img_captcha_locator = contenedor_captcha.locator("img.img-captcha").first
                    input_captcha = contenedor_captcha.locator("input").first
                    btn_recargar = contenedor_captcha.locator("a[color='warn']").first
                    btn_buscar = page.locator("button:has-text('Buscar')").first

                    tabla_encontrada = False

                    for intento in range(1, 16):
                        await page.wait_for_timeout(1500)
                        await img_captcha_locator.wait_for(state="visible", timeout=10000)
                        
                        img_bytes = await img_captcha_locator.screenshot()
                        texto_captcha = resolver_captcha_imagen(img_bytes)

                        if len(texto_captcha) != 6:
                            if await btn_recargar.is_visible(): 
                                await btn_recargar.click(force=True)
                            continue

                        await input_captcha.click()
                        await page.keyboard.press("Control+A") 
                        await page.keyboard.press("Backspace")
                        await input_captcha.fill("")
                        
                        await input_captcha.press_sequentially(texto_captcha, delay=50)
                        await input_captcha.press("Enter")
                        await page.wait_for_timeout(500)
                        
                        await btn_buscar.click(force=True)

                        try:
                            respuesta = await page.wait_for_selector(".ant-table, table, nz-modal-confirm-container, .ant-modal-wrap, .ant-message", timeout=6000)
                            clase_res = await respuesta.get_attribute("class") or ""
                            tag_name = await respuesta.evaluate("el => el.tagName.toLowerCase()")
                            
                            if "modal" in clase_res or "modal" in tag_name:
                                btn_aceptar = page.locator("button:has-text('Aceptar'), button:has-text('OK')").first
                                if await btn_aceptar.is_visible():
                                    await btn_aceptar.click()
                                await page.wait_for_timeout(2000)
                            elif "message" in clase_res or "notification" in clase_res:
                                if await btn_recargar.is_visible(): 
                                    await btn_recargar.click(force=True)
                                await page.wait_for_timeout(1000)
                            else:
                                tabla_encontrada = True
                                break
                        except Exception:
                            if await btn_recargar.is_visible(): 
                                await btn_recargar.click(force=True)

                    if not tabla_encontrada:
                        raise TimeoutError("Se superó el límite de reintentos del CAPTCHA OCR sin éxito.")

                    try:
                        btn_visualizar = page.locator("app-button#tabla button").first
                        await btn_visualizar.wait_for(state="attached", timeout=10000)
                        await btn_visualizar.evaluate("el => el.click()")
                        
                        await page.wait_for_selector("text='Lista de Asientos'", state="visible", timeout=15000)
                        await page.wait_for_timeout(2000)
                        
                        elementos_titulo = page.locator("div.bg-gray").filter(has_text=re.compile(r"Titulo", re.IGNORECASE))
                        cantidad_titulos = await elementos_titulo.count()
                        
                        for i in range(cantidad_titulos):
                            texto_bruto = await elementos_titulo.nth(i).inner_text()
                            match = re.search(r"Titulo\s*:\s*(\d{4})\s*-\s*(\d+)", texto_bruto, re.IGNORECASE)
                            if match:
                                titulos_asientos.append({
                                    "year": match.group(1),
                                    "number": match.group(2),
                                    "original_text": match.group(0)
                                })
                    except Exception:
                        pass

                    estado_auditoria = AuditStatus.SUCCESS if titulos_asientos else AuditStatus.NO_DATA

                finally:
                    await context.close()

        except Exception as exc:
            detalles_error = f"{type(exc).__name__}: {exc}"
            estado_auditoria = AuditStatus.ERROR

        return {
            "audit": AuditResult(
                source_name=self.SOURCE_NAME,
                query_parameter=f"{oficina} | {area} | {partida}",
                duration_ms=int((time.perf_counter() - started) * 1000),
                status=estado_auditoria,
                details=detalles_error,
                executed_at_utc=datetime.now(timezone.utc),
            ),
            "data": { "seats": titulos_asientos }
        }