from playwright.async_api import async_playwright

from config import PLUGIN_DIR


def _normalize_proxy_server(raw_proxy: str | None) -> str:
    value = str(raw_proxy or "").strip()
    if not value:
        return ""
    if "://" not in value:
        return f"http://{value}"
    return value


async def initialize_browser(proxy_server: str = ""):
    playwright = await async_playwright().start()
    launch_kwargs: dict[str, object] = {
        "headless": True,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-features=IsolateOrigins,site-per-process",
            "--ignore-certificate-errors",
        ],
    }
    normalized_proxy = _normalize_proxy_server(proxy_server)
    if normalized_proxy:
        launch_kwargs["proxy"] = {"server": normalized_proxy}
    browser = await playwright.chromium.launch(**launch_kwargs)
    context = await browser.new_context(
        ignore_https_errors=True,
        bypass_csp=True,
        locale="zh-CN",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    await context.add_init_script(
        script="""
Object.defineProperty(navigator, 'webdriver', {
  get: () => undefined
});
"""
    )
    page = await context.new_page()

    print("\033[1m\033[32m======= Browser Started =======\033[0m\n")
    print("\033[1m--- Plugin Loading ---\033[0m")

    for sub_dir in sorted(d for d in PLUGIN_DIR.iterdir() if d.is_dir()):
        js_files = sorted(f for f in sub_dir.iterdir() if f.is_file() and f.suffix == ".js")

        if not js_files:
            print(f"\033[33m[skip] no js file in: {sub_dir.name}\033[0m")
            continue

        for file_path in js_files:
            script_content = file_path.read_text(encoding="utf-8")
            # Inject into browser context so every new page (including
            # concurrent pages created later) receives the same plugins.
            await context.add_init_script(script=script_content)

        print(f"\033[32m[ok] plugin loaded: {sub_dir.name}\033[0m")

    return playwright, browser, context, page
