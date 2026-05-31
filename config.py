import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
PLUGIN_DIR = ROOT_DIR / "plugin"

# VueScan VC artifacts: routes/chunks/manifests by domain.
PROJECTS_DIR = ROOT_DIR / "projects"

# VueScan VD and util script outputs.
OUTPUTS_DIR = ROOT_DIR / "outputs"
VD_OUTPUT_DIR = OUTPUTS_DIR / "vd"
UTIL_OUTPUT_DIR = OUTPUTS_DIR / "util"

# Playwright browser channel.
# Leave empty to use Playwright's own bundled Chromium (requires `playwright install chromium`).
# Set to "msedge" (Windows pre-installed) or "chrome" to skip the Chromium download entirely.
# Example: set env PLAYWRIGHT_BROWSER_CHANNEL=msedge in .env or start script.
PLAYWRIGHT_BROWSER_CHANNEL: str = os.environ.get("PLAYWRIGHT_BROWSER_CHANNEL", "").strip()
