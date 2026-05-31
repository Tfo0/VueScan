from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet

from starlette.templating import Jinja2Templates

from config import OUTPUTS_DIR, PROJECTS_DIR


@dataclass(frozen=True)
class WebBootstrapConfig:
    # 统一收口 Web 启动阶段会用到的路径和默认配置，避免工厂文件散落硬编码。
    base_dir: Path
    templates: Jinja2Templates
    static_dir: Path
    frontend_dir: Path
    frontend_dist_dir: Path
    web_upload_dir: Path
    jobs_dir: Path
    projects_dir: Path
    sqlite_db_file: Path
    global_settings_file: Path
    upload_extensions: FrozenSet[str]
    detect_default_concurrency: int
    detect_default_timeout: int
    detect_default_wait_ms: int
    js_download_default_concurrency: int
    module3_js_max_display_chars: int
    module1_detect_job_step: str
    module2_sync_job_step: str
    module2_js_download_job_step: str
    module2_request_capture_job_step: str
    vue_request_batch_job_step: str
    module2_request_default_concurrency: int
    module2_route_style_sample_size: int
    module2_auto_scan_pattern: str
    module3_auto_regex_max_scan_files: int


def build_web_bootstrap_config() -> WebBootstrapConfig:
    # 这里保留现有默认值，不改业务流程，只把启动配置集中管理。
    base_dir = Path(__file__).resolve().parent
    frontend_dir = base_dir.parents[1] / "frontend"
    return WebBootstrapConfig(
        base_dir=base_dir,
        templates=Jinja2Templates(directory=str(base_dir / "templates")),
        static_dir=base_dir / "static",
        frontend_dir=frontend_dir,
        frontend_dist_dir=frontend_dir / "dist",
        web_upload_dir=OUTPUTS_DIR / "web_uploads",
        jobs_dir=OUTPUTS_DIR / "jobs",
        projects_dir=PROJECTS_DIR,
        sqlite_db_file=OUTPUTS_DIR / "web" / "app.sqlite3",
        global_settings_file=OUTPUTS_DIR / "web" / "global_settings.json",
        upload_extensions=frozenset({".xlsx", ".xlsm", ".txt", ".html", ".htm"}),
        detect_default_concurrency=5,
        detect_default_timeout=20,
        detect_default_wait_ms=1800,
        js_download_default_concurrency=24,
        module3_js_max_display_chars=260000,
        module1_detect_job_step="web_module1_detect",
        module2_sync_job_step="web_module2_project_sync",
        module2_js_download_job_step="web_module2_js_download",
        module2_request_capture_job_step="web_module2_request_capture",
        vue_request_batch_job_step="web_vue_request_batch",
        module2_request_default_concurrency=8,
        module2_route_style_sample_size=5,
        module2_auto_scan_pattern=r'return\s*Object\(\w\.\w\)\(\{\s*url:"([^"]*)',
        module3_auto_regex_max_scan_files=220,
    )
