import asyncio
import os
import time
from typing import Any, Final

from playwright.async_api import Browser, Page, Playwright, Response, async_playwright

from app.domain.models.instagram import USERNAME_PATTERN, InstagramProfile, normalize_username
from app.infrastructure.outbound.extractors.instagram.parser import PageReading, PageState, read_page
from app.infrastructure.outbound.extractors.instagram.photo import photos_dir
from app.infrastructure.outbound.extractors.shared.browser import run_isolated
from app.infrastructure.outbound.extractors.shared.extractor import BaseExtractor, Outcome
from app.infrastructure.outbound.extractors.shared.pace import Pace
from app.infrastructure.outbound.extractors.shared.photo import download_photo

PROFILE_URL: Final = "https://www.instagram.com/{username}/"
LOCALE: Final = "es-PE"
VIEWPORT: Final = {"width": 1366, "height": 768}
NAVIGATION_TIMEOUT_MS: Final = 45_000
READ_DEADLINE_S: Final = 15.0
POLL_MS: Final = 700
POSTS_GRACE_S: Final = 4.0  # Espera extra por las publicaciones, que pueden cargar después.

READ_PAGE_JS: Final = """() => {
  const metas = {};
  for (const e of document.querySelectorAll('meta[property], meta[name]'))
    metas[e.getAttribute('property') || e.getAttribute('name')] = e.content;
  const main = document.querySelector('main');
  return {
    url: location.href,
    title: document.title,
    metas,
    body: document.body ? document.body.innerText : '',
    main: main ? main.innerText : '',
    password: !!document.querySelector('input[type=password]'),
    json: [...document.querySelectorAll('script[type="application/json"]')].map(s => s.textContent),
  };
}"""


_PACE = Pace()


class InstagramUsernameAdapter(BaseExtractor):
    SOURCE_NAME = "INSTAGRAM_PROFILE"
    PATTERN = USERNAME_PATTERN
    PARAMETER_HINT = "an Instagram username"

    def __init__(self, pace: Pace = _PACE) -> None:
        self._pace = pace
        self._headless = os.getenv("INSTAGRAM_HEADLESS", "true").lower() == "true"

    async def extract(self, parameter: str) -> dict[str, Any]:
        return await super().extract(normalize_username(parameter))

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
            details=f"Consultas en pausa por un bloqueo de Instagram; faltan {int(remaining)} s",
            failed=True,
        )

    async def _scrape(self, username: str) -> Outcome:
        async with async_playwright() as playwright:
            browser = await self._launch(playwright)
            try:
                context = await browser.new_context(locale=LOCALE, viewport=VIEWPORT)
                page = await context.new_page()
                response = await page.goto(
                    PROFILE_URL.format(username=username),
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT_MS,
                )
                reading = await self._read(page, response, username)
                if reading.state is PageState.NOT_FOUND:
                    return Outcome(details=reading.details)
                if reading.state is PageState.BLOCKED:
                    self._pace.block()
                if reading.state is not PageState.OK or reading.user is None:
                    return Outcome(details=reading.details, failed=True)

                user = reading.user
                fields = {k: v for k, v in user.items() if k != "photo_url"}
                photo_path, details = None, None
                try:
                    photo_path = await download_photo(
                        context, user["photo_url"], username, photos_dir()
                    )
                except Exception as exc:  # Sin foto, el perfil sigue siendo válido.
                    details = f"Foto no descargada: {type(exc).__name__}: {exc}"
                return Outcome(
                    data=InstagramProfile(
                        **fields,
                        profile_url=PROFILE_URL.format(username=username),
                        photo_path=photo_path,
                    ),
                    raw=user,
                    details=details,
                )
            finally:
                await browser.close()

    async def _launch(self, playwright: Playwright) -> Browser:
        try:
            return await playwright.chromium.launch(channel="chrome", headless=self._headless)
        except Exception:  # Sin Chrome instalado (p.ej. Docker): Chromium de Playwright.
            return await playwright.chromium.launch(headless=self._headless)

    @staticmethod
    async def _read(page: Page, response: Response | None, username: str) -> PageReading:
        """Relee la misma carga hasta que esté completa; nunca vuelve a pedir la página."""
        deadline = time.monotonic() + READ_DEADLINE_S
        posts_deadline: float | None = None
        while True:
            content = await page.evaluate(READ_PAGE_JS)
            content["status"] = response.status if response else None
            reading = read_page(content, username)
            now = time.monotonic()
            if reading.state is PageState.NOT_FOUND or now >= deadline:
                return reading
            if reading.state is PageState.OK:
                posts_deadline = posts_deadline or now + POSTS_GRACE_S
                if not reading.posts_pending or now >= posts_deadline:
                    return reading
            await page.wait_for_timeout(POLL_MS)
