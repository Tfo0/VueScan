from __future__ import annotations

import json
import re
from pathlib import Path

from config import OUTPUTS_DIR
from src.vue_api.models import ApiProfile, utc_now_iso


PROFILE_DIR = OUTPUTS_DIR / "va" / "profiles"


def _normalize_profile_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        raise ValueError("profile name cannot be empty")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    if not safe:
        raise ValueError("profile name is invalid")
    return safe


def _profile_path(name: str) -> Path:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _normalize_profile_name(name)
    return PROFILE_DIR / f"{safe_name}.json"


def save_profile(profile: ApiProfile) -> Path:
    path = _profile_path(profile.name)
    now = utc_now_iso()

    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        created_at = str(current.get("created_at") or profile.created_at)
    else:
        created_at = profile.created_at or now

    payload = {
        "name": _normalize_profile_name(profile.name),
        "baseurl": str(profile.baseurl).strip(),
        "baseapi": str(profile.baseapi).strip(),
        "pattern": str(profile.pattern),
        "created_at": created_at,
        "updated_at": now,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_profile(name: str) -> ApiProfile:
    path = _profile_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"profile not found: {name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ApiProfile.from_dict(payload)


def list_profiles() -> list[str]:
    if not PROFILE_DIR.is_dir():
        return []
    return sorted(path.stem for path in PROFILE_DIR.glob("*.json"))
