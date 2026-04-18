from __future__ import annotations

from pathlib import Path
from typing import Any


def merge_project_domains(
    project_records: list[dict[str, Any]],
    *,
    projects_dir: Path,
    safe_str,
) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()

    for item in project_records:
        domain = safe_str(item.get("domain"))
        if not domain or domain in seen:
            continue
        seen.add(domain)
        domains.append(domain)

    if projects_dir.is_dir():
        for path in sorted(projects_dir.iterdir(), key=lambda p: p.name.lower()):
            if not path.is_dir():
                continue
            domain = path.name
            if domain in seen:
                continue
            seen.add(domain)
            domains.append(domain)

    return domains


def serialize_project(item: dict[str, Any], *, safe_str) -> dict[str, Any]:
    # 这里统一做 Web 层项目行序列化，避免多个路由重复拼装同一份结构。
    return {
        "domain": safe_str(item.get("domain")),
        "title": safe_str(item.get("title")),
        "source": safe_str(item.get("source")),
        "seed_urls": [str(url).strip() for url in item.get("seed_urls", []) if str(url).strip()],
        "task_ids": [str(task_id).strip() for task_id in item.get("task_ids", []) if str(task_id).strip()],
        "created_at": safe_str(item.get("created_at")),
        "updated_at": safe_str(item.get("updated_at")),
    }
