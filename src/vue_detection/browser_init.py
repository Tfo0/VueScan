from playwright.async_api import async_playwright

from config import PLAYWRIGHT_BROWSER_CHANNEL


async def initialize_vd_browser(headless: bool = True):
    playwright = await async_playwright().start()
    launch_kwargs: dict[str, object] = {"headless": headless}
    if PLAYWRIGHT_BROWSER_CHANNEL:
        launch_kwargs["channel"] = PLAYWRIGHT_BROWSER_CHANNEL
    browser = await playwright.chromium.launch(**launch_kwargs)
    context = await browser.new_context(
        ignore_https_errors=True,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    return playwright, browser, context
