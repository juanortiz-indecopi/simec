import asyncio
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from app.core.files import FILES_DIR
from app.domain.models.facebook import PAGE_KEY_PATTERN, FacebookPage, normalize_page
from app.infrastructure.outbound.extractors.facebook.parser import (
    PageReading,
    PageState,
    merge,
    read_main,
    read_section,
)
from app.infrastructure.outbound.extractors.shared.browser import run_isolated
from app.infrastructure.outbound.extractors.shared.extractor import BaseExtractor, Outcome
from app.infrastructure.outbound.extractors.shared.pace import Pace
from app.infrastructure.outbound.extractors.shared.photo import download_photo

BASE_URL: Final = "https://www.facebook.com"
SECTIONS: Final = ("about", "about_profile_transparency")
LOCALE: Final = "es-PE"  # El parser interpreta fechas y avisos en español.
VIEWPORT: Final = {"width": 1366, "height": 768}
NAVIGATION_TIMEOUT_MS: Final = 30_000
READ_DEADLINE_S: Final = 12.0
PENDING_GRACE_S: Final = 5.0  # Espera extra por detalles y publicación, que cargan después.
SECTION_PAUSE_S: Final = 3.0
POLL_MS: Final = 700

READ_PAGE_JS: Final = """() => {
  const metas = {};
  for (const e of document.querySelectorAll('meta[property], meta[name]'))
    metas[e.getAttribute('property') || e.getAttribute('name')] = e.content;
  return {
    url: location.href,
    metas,
    body: document.body ? document.body.innerText : '',
    json: [...document.querySelectorAll('script[type="application/json"]')].map(s => s.textContent),
  };
}"""

_PACE = Pace()


def photos_dir() -> Path:
    return Path(os.getenv("FACEBOOK_FILES_DIR", os.path.join(FILES_DIR, "facebook")))


class FacebookPageAdapter(BaseExtractor):
    SOURCE_NAME = "FACEBOOK_PAGE"
    PATTERN = PAGE_KEY_PATTERN
    PARAMETER_HINT = "a Facebook page username, ID or URL"

    def __init__(self, pace: Pace = _PACE) -> None:
        self._pace = pace
        self._headless = os.getenv("FACEBOOK_HEADLESS", "true").lower() == "true"

    async def extract(self, parameter: str) -> dict[str, Any]:
        return await super().extract(normalize_page(parameter) or "")

    async def _fetch(self, value: str) -> Outcome:
        if (paused := self._paused()) is not None:
            return paused
        await asyncio.sleep(self._pace.reserve())
        # Otra consulta pudo ser bloqueada durante la espera.
        if (paused := self._paused()) is not None:
            return paused
        return await run_isolated(lambda: self._scrape(value))

    def _paused(self) -> Outcome | None:
        remaining = self._pace.blocked_for()
        if remaining <= 0:
            return None
        return Outcome(
            details=f"Consultas en pausa por un bloqueo de Facebook; faltan {int(remaining)} s",
            failed=True,
        )

    async def _scrape(self, key: str) -> Outcome:
        async with async_playwright() as playwright:
            browser = await self._launch(playwright)
            try:
                context = await browser.new_context(locale=LOCALE, viewport=VIEWPORT)
                url = f"{BASE_URL}/profile.php?id={key}" if key.isdigit() else f"{BASE_URL}/{key}"
                main = await self._load(context, url, lambda page: read_main(page, key))
                if main.state in (PageState.NOT_FOUND, PageState.NOT_A_PAGE):
                    return Outcome(details=main.details)
                if main.state is not PageState.OK:
                    return Outcome(details=main.details, failed=True)

                fields, notes = main.fields, []
                missing: list[str] = []
                for section in SECTIONS:
                    if self._pace.blocked_for() > 0:
                        missing.append(section)
                        continue
                    await asyncio.sleep(SECTION_PAUSE_S)
                    try:
                        reading = await self._load(
                            context,
                            self._section_url(fields, section),
                            lambda page: read_section(page, fields["account_id"]),
                        )
                    except Exception as exc:  # Las pestañas son opcionales.
                        reading = PageReading(PageState.ERROR, type(exc).__name__)
                    if reading.state is PageState.OK:
                        fields = merge(fields, reading.fields)
                    else:
                        missing.append(section)
                        notes.append(f"Pestaña {section} no leída: {reading.details}")

                photo_path = None
                try:
                    photo_path = await download_photo(
                        context, main.photo_url, fields["account_id"], photos_dir()
                    )
                except Exception as exc:  # Sin foto, la página sigue siendo válida.
                    notes.append(f"Foto no descargada: {type(exc).__name__}: {exc}")
                return Outcome(
                    data=FacebookPage(
                        key=key, photo_path=photo_path, missing_sections=tuple(missing), **fields
                    ),
                    raw=fields | {"photo_url": main.photo_url},
                    details=" | ".join(notes) or None,
                )
            finally:
                await browser.close()

    @staticmethod
    def _section_url(fields: dict[str, Any], section: str) -> str:
        username = normalize_page(fields["page_url"])
        if username is None or username.isdigit():
            return f"{BASE_URL}/profile.php?id={fields['account_id']}&sk={section}"
        return f"{BASE_URL}/{username}/{section}"

    async def _launch(self, playwright: Playwright) -> Browser:
        try:
            return await playwright.chromium.launch(channel="chrome", headless=self._headless)
        except Exception:  # Sin Chrome instalado (p.ej. Docker): Chromium de Playwright.
            return await playwright.chromium.launch(headless=self._headless)

    async def _load(
        self, context: BrowserContext, url: str, read: Callable[[dict[str, Any]], PageReading]
    ) -> PageReading:
        """Carga la URL una vez y la relee hasta que esté completa; nunca la vuelve a pedir."""
        page = await context.new_page()
        try:
            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS
            )
            deadline = time.monotonic() + READ_DEADLINE_S
            grace: float | None = None
            while True:
                content = await page.evaluate(READ_PAGE_JS)
                content["status"] = response.status if response else None
                reading = read(content)
                now = time.monotonic()
                if reading.state is PageState.OK:
                    grace = grace or now + PENDING_GRACE_S
                    if not reading.pending or now >= grace:
                        return reading
                if reading.state is PageState.NOT_A_PAGE or now >= deadline:
                    break
                await page.wait_for_timeout(POLL_MS)
            if reading.state is PageState.BLOCKED:
                self._pace.block()
            return reading
        finally:
            await page.close()
