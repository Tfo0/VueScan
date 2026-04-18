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
