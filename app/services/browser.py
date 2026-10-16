"""PhantomAPI — Browser automation engine.

Launches a persistent headless Chrome instance via Playwright
and interacts with chatgpt.com to generate responses.
"""

import asyncio
import queue
import threading
from app.config import settings


class ServerBusyError(Exception):
    """Raised when all browser chat slots are occupied (translate to HTTP 503)."""


class BrowserEngine(threading.Thread):
    """A dedicated thread that runs an async Playwright browser.

    This avoids blocking the FastAPI event loop while still giving
    us a persistent browser instance that can handle sequential requests.
    """

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.browser = None
        self.playwright = None
        # Load control: at most MAX_CONCURRENT_CHATS browser chats at once
        self._slots = threading.Semaphore(settings.MAX_CONCURRENT_CHATS)

    # ------------------------------------------------------------------
    # Thread lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Thread entry point — start browser and run the event loop forever."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._launch())
        self.ready.set()
        print("[PhantomAPI] ⚡ Browser engine ready.")
        self.loop.run_forever()

    async def _launch(self) -> None:
        """Launch a stealth Chromium browser.

        Prefers real Google Chrome; falls back to Playwright's bundled
        Chromium when Chrome isn't installed.
        """
        from playwright.async_api import async_playwright

        print("[PhantomAPI] 🚀 Launching browser...")
        self.playwright = await async_playwright().start()
        launch_kwargs = dict(
            headless=settings.HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
            ],
        )
        try:
            self.browser = await self.playwright.chromium.launch(
                channel="chrome", **launch_kwargs
            )
        except Exception as exc:
            print(f"[PhantomAPI] ⚠️ Google Chrome not found ({exc}); using bundled Chromium")
            self.browser = await self.playwright.chromium.launch(**launch_kwargs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _acquire_slot(self) -> None:
        """Take a chat slot, or raise ServerBusyError after QUEUE_TIMEOUT."""
        if not self._slots.acquire(timeout=settings.QUEUE_TIMEOUT):
            raise ServerBusyError(
                f"Server busy: all {settings.MAX_CONCURRENT_CHATS} chat slots occupied. "
                "Try again in a few seconds."
            )

    def chat(self, prompt: str, images: list | None = None) -> str:
        """Send a prompt to ChatGPT and return the response text.

        *images* — optional list of local image file paths to upload into the
        composer before sending (vision support).

        This is a blocking call that schedules work on the browser
        thread's event loop and waits for the result.
        """
        if not self.ready.wait(timeout=30) or self.browser is None:
            raise RuntimeError("Browser engine is not ready. Is Chrome installed?")

        self._acquire_slot()
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._interact(prompt, images or []), self.loop
            )
            return future.result(timeout=settings.BROWSER_TIMEOUT // 1000 + 30)
        finally:
            self._slots.release()

    def chat_stream(self, prompt: str, images: list | None = None):
        """Yield text deltas as Luna types its response.

        Sync generator — safe to run in a worker thread. Each yielded string
        is the newly typed slice since the previous yield.
        """
        if not self.ready.wait(timeout=30) or self.browser is None:
            raise RuntimeError("Browser engine is not ready. Is Chrome installed?")

        snapshots: "queue.Queue" = queue.Queue()
        _DONE = object()

        def on_text(full_text: str) -> None:
            snapshots.put(full_text)

        def run() -> None:
            try:
                self._acquire_slot()
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self._interact(prompt, images or [], on_text=on_text), self.loop
                    )
                    future.result(timeout=settings.BROWSER_TIMEOUT // 1000 + 30)
                finally:
                    self._slots.release()
            except BaseException as exc:  # noqa: BLE001 — forwarded to the consumer
                snapshots.put(exc)
            finally:
                snapshots.put(_DONE)

        threading.Thread(target=run, daemon=True).start()

        last = ""
        while True:
            item = snapshots.get()
            if item is _DONE:
                return
            if isinstance(item, BaseException):
                raise item
            if item != last:
                if item.startswith(last):
                    delta = item[len(last):]
                else:
                    delta = item  # text was rewritten; emit as-is
                last = item
                if delta:
                    yield delta

    # ------------------------------------------------------------------
    # Private — browser interaction
    # ------------------------------------------------------------------

    async def _interact(self, prompt: str, images: list, on_text=None) -> str:
        """Open a new ChatGPT session, attach images, send the prompt, scrape the reply.

        *on_text* — optional callback receiving the full current response text
        each time it changes (used for streaming).
        """
        context = await self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )

        # Hide the webdriver flag so ChatGPT thinks we're a real user
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await context.new_page()

        try:
            page.set_default_timeout(settings.BROWSER_TIMEOUT)

            # Navigate to ChatGPT
            await page.goto("https://chatgpt.com/", wait_until="domcontentloaded")

            # Attach images first (vision) — best effort, never fatal
            if images:
                await self._attach_images(page, images)

            # Find the composer (ChatGPT's DOM changes over time; try known selectors)
            composer = await self._find_composer(page)

            # Type the prompt and send it
            await composer.fill(prompt)
            await asyncio.sleep(0.5)
            await self._send_prompt(page, composer)

            # Wait for the assistant to start responding
            await page.wait_for_selector(
                '[data-message-author-role="assistant"]',
                timeout=settings.BROWSER_TIMEOUT,
            )

            # Poll until the response stabilises (no new text for ~2 seconds)
            last_text = ""
            unchanged_count = 0
            while unchanged_count < 4:
                elements = await page.query_selector_all(
                    '[data-message-author-role="assistant"]'
                )
                if elements:
                    current_text = await elements[-1].inner_text()
                    if current_text == last_text and current_text.strip():
                        unchanged_count += 1
                    else:
                        last_text = current_text
                        unchanged_count = 0
                        if on_text is not None:
                            on_text(current_text)
                await asyncio.sleep(0.5)

            return last_text.strip()

        except Exception as exc:
            print(f"[PhantomAPI] ❌ Browser error: {exc}")
            raise
        finally:
            await page.close()
            await context.close()

    async def _find_composer(self, page):
        """Locate the ChatGPT composer, trying known selectors in order.

        ChatGPT's DOM changes over time (#prompt-textarea is gone as of
        2026-10; the mobile textarea #mobile-composer-prompt is current).
        Returns the first visible match or raises after all fail.
        """
        selectors = [
            "#prompt-textarea",
            "#mobile-composer-prompt",
            'div[role="textbox"]',
            '[contenteditable="true"]',
            "[contenteditable]",
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel)
                await loc.first.wait_for(state="visible", timeout=10000)
                print(f"[PhantomAPI] 📝 Composer found: {sel}")
                return loc.first
            except Exception:
                continue
        raise RuntimeError("Could not find the ChatGPT composer (tried: %s)" % ", ".join(selectors))

    async def _send_prompt(self, page, composer) -> None:
        """Submit the typed prompt via send button, falling back to Enter."""
        for sel in ['button[data-testid="send-button"]', 'button[aria-label*="Send"]']:
            try:
                btn = page.locator(sel).first
                await btn.wait_for(state="visible", timeout=5000)
                await btn.click()
                print(f"[PhantomAPI] 📤 Sent via button ({sel})")
                return
            except Exception:
                continue
        await composer.press("Enter")
        print("[PhantomAPI] 📤 Sent via Enter")

    async def _attach_images(self, page, images: list) -> None:
        """Upload image files into the ChatGPT composer (vision support).

        Best effort: if the file input can't be found (UI changed), log and
        continue text-only rather than failing the request.
        """
        try:
            file_input = page.locator('input[type="file"]')
            await file_input.first.wait_for(timeout=15000)
            await file_input.first.set_input_files([str(p) for p in images])
            # Give the composer a moment to register the attachments
            await page.wait_for_timeout(2500)
            print(f"[PhantomAPI] 🖼️ Attached {len(images)} image(s) to composer")
        except Exception as exc:
            print(f"[PhantomAPI] ⚠️ Image attach failed, continuing text-only: {exc}")


# ---------------------------------------------------------------------------
# Singleton — created once at import time, started in app lifespan
# ---------------------------------------------------------------------------
engine = BrowserEngine()
