import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def generar_sesion():
    print("Abriendo navegador con camuflaje de grado militar...")
    async with async_playwright() as p:
        # Usamos tu Chrome real, pero le quitamos todas las banderas de automatización
        browser = await p.chromium.launch(
            channel="chrome", 
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"]  # Esto quita el aviso de "Software automatizado"
        )
        
        context = await browser.new_context(viewport={"width": 1366, "height": 768})
        page = await context.new_page()
        
        # Aplicamos el camuflaje para borrar rastros de Playwright
        await Stealth().apply_stealth_async(page)
        
        await page.goto("https://sprl.sunarp.gob.pe/sprl/main/partidas-base-grafica-registral")
        
        print("\n=======================================================")
        print(" ACCIÓN REQUERIDA: INICIA SESIÓN MANUALMENTE")
        print(" 1. Ingresa tu usuario y contraseña REALES.")
        print(" 2. Resuelve el Cloudflare Turnstile con tu mouse.")
        print(" 3. Haz clic en INGRESAR.")
        print(" Tienes 2 minutos para hacerlo...")
        print("=======================================================\n")
        
        try:
            # Esperamos a que la página de bienvenida de SUNARP cargue
            await page.locator("text=/Hola,/i").first.wait_for(state="visible", timeout=120000)
            
            # Guardamos las cookies y tokens de acceso
            await context.storage_state(path="sunarp_auth.json")
            print("✅ ¡ÉXITO! Sesión guardada en 'sunarp_auth.json'. Ya puedes cerrar esto.")
            
        except Exception as e:
            print(f"❌ Error o tiempo agotado: {e}")
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(generar_sesion())