from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from .request_snapshot_store import REQUEST_DB_FILE, connect_request_store, ensure_request_snapshot_schema
from .request_snapshots import load_request_run_snapshots
from .requester import load_saved_response_detail


SAMPLED_ROWS_PER_SNAPSHOT = 20
LONG_RESPONSE_LENGTH = 800
LONG_PACKET_LENGTH = 1200
AUTH_ONLY_STATUS_CODES = {401, 403}
HIGH_VALUE_RESPONSE_PATTERNS = (
    re.compile(r"\bmissing\b", re.IGNORECASE),
    re.compile(r"\brequired\b", re.IGNORECASE),
    re.compile(r"\bparam(?:eter)?s?\b", re.IGNORECASE),
    re.compile(r"accountname", re.IGNORECASE),
    re.compile(r"orderid", re.IGNORECASE),
    re.compile(r"缺少"),
    re.compile(r"参数"),
    re.compile(r"必填"),
    re.compile(r"不能为空"),
)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_int(raw: Any, default: int = 0, minimum: int = 0) -> int:
    text = _safe_text(raw)
    if not text:
        return max(default, minimum)
    try:
        value = int(text)
    except Exception:
        return max(default, minimum)
    return max(value, minimum)


def _blank_summary() -> dict[str, object]:
    return {
        "request_value_level": "",
        "request_value_label": "",
        "request_value_reason": "",
        "request_value_score": 0,
        "request_value_snapshot_count": 0,
        "request_value_sample_count": 0,
    }


def _matched_keyword_labels(response_path: str, cache: dict[str, list[str]]) -> list[str]:
    path = _safe_text(response_path)
    if not path:
        return []
    cached = cache.get(path)
    if cached is not None:
        return cached

    detail = load_saved_response_detail(path)
    body_text = _safe_text(detail.get("response_text"))
    if not body_text:
        cache[path] = []
        return []

    matched: list[str] = []
    for pattern in HIGH_VALUE_RESPONSE_PATTERNS:
        if pattern.search(body_text):
            matched.append(pattern.pattern)
    cache[path] = matched
    return matched


def _sort_default_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    ordered = [item for item in rows if isinstance(item, dict)]
    ordered.sort(
        key=lambda row: (
            _coerce_int(row.get("status_code"), default=0, minimum=0) != 200,
            -_coerce_int(row.get("packet_length"), default=0, minimum=0),
            -_coerce_int(row.get("status_code"), default=0, minimum=0),
            _safe_text(row.get("path")),
        )
    )
    return ordered


def _analyze_snapshot_rows(
    rows: list[dict[str, object]],
    *,
    keyword_cache: dict[str, list[str]],
) -> dict[str, object]:
    sampled_rows = _sort_default_rows(rows)[: max(1, SAMPLED_ROWS_PER_SNAPSHOT)]
    if not sampled_rows:
        return {
            "level": "",
            "score": 0,
            "reason": "",
            "sample_count": 0,
            "long_200_count": 0,
            "keyword_hit_count": 0,
            "auth_only": False,
        }

    long_200_count = 0
    keyword_hit_count = 0
    auth_only_count = 0

    for row in sampled_rows:
        status_code = _coerce_int(row.get("status_code"), default=0, minimum=0)
        response_length = _coerce_int(row.get("response_length"), default=0, minimum=0)
        packet_length = _coerce_int(row.get("packet_length"), default=0, minimum=0)

        if status_code in AUTH_ONLY_STATUS_CODES:
            auth_only_count += 1

        if status_code == 200 and (
            response_length >= LONG_RESPONSE_LENGTH or packet_length >= LONG_PACKET_LENGTH
        ):
            long_200_count += 1

        matched_keywords = _matched_keyword_labels(_safe_text(row.get("response_path")), keyword_cache)
        if matched_keywords:
            keyword_hit_count += 1

    auth_only = auth_only_count == len(sampled_rows)
    score = long_200_count * 12 + keyword_hit_count * 18
    if auth_only:
        score = max(score - 20, 0)

    if keyword_hit_count > 0:
        return {
            "level": "high",
            "score": max(score, 70),
            "reason": f"命中缺参或参数提示 {keyword_hit_count} 条",
            "sample_count": len(sampled_rows),
            "long_200_count": long_200_count,
            "keyword_hit_count": keyword_hit_count,
            "auth_only": auth_only,
        }

    if long_200_count > 0:
        return {
            "level": "high",
            "score": max(score, 65),
            "reason": f"命中长响应 200 数据包 {long_200_count} 条",
            "sample_count": len(sampled_rows),
            "long_200_count": long_200_count,
            "keyword_hit_count": keyword_hit_count,
            "auth_only": auth_only,
        }

    if auth_only:
        return {
            "level": "low",
            "score": 10,
            "reason": f"前 {len(sampled_rows)} 条结果均为 401/403",
            "sample_count": len(sampled_rows),
            "long_200_count": 0,
            "keyword_hit_count": 0,
            "auth_only": True,
        }

    return {
        "level": "medium",
        "score": max(score, 40),
        "reason": "存在混合响应，建议人工复核",
        "sample_count": len(sampled_rows),
        "long_200_count": long_200_count,
        "keyword_hit_count": keyword_hit_count,
        "auth_only": False,
    }


def load_request_analysis_summary(domain: str) -> dict[str, object]:
    token = _safe_text(domain)
    if not token:
        return _blank_summary()
    ensure_request_snapshot_schema(REQUEST_DB_FILE)
    with connect_request_store(REQUEST_DB_FILE) as connection:
        row = connection.execute(
            """
            SELECT value_level, value_label, value_reason, value_score, snapshot_count, sample_count, summary_json
            FROM request_analysis_summary
            WHERE domain = ?
            """,
            (token,),
        ).fetchone()
    if row is None:
        return _blank_summary()
    try:
        summary_json = json.loads(str(row["summary_json"] or "{}"))
    except Exception:
        summary_json = {}
    return {
        "request_value_level": _safe_text(row["value_level"]) or _safe_text(summary_json.get("request_value_level")),
        "request_value_label": _safe_text(row["value_label"]) or _safe_text(summary_json.get("request_value_label")),
        "request_value_reason": _safe_text(row["value_reason"]) or _safe_text(summary_json.get("request_value_reason")),
        "request_value_score": _coerce_int(row["value_score"], default=0, minimum=0),
        "request_value_snapshot_count": _coerce_int(row["snapshot_count"], default=0, minimum=0),
        "request_value_sample_count": _coerce_int(row["sample_count"], default=0, minimum=0),
    }


def refresh_request_analysis_summary(domain: str) -> dict[str, object]:
    token = _safe_text(domain)
    if not token:
        return _blank_summary()

    snapshots = load_request_run_snapshots(token)
    if not snapshots:
        summary = _blank_summary()
    else:
        keyword_cache: dict[str, list[str]] = {}
        analyzed_rows = 0
        analyzed_snapshots = 0
        high_results: list[dict[str, object]] = []
        medium_results: list[dict[str, object]] = []
        low_results: list[dict[str, object]] = []

        for snapshot in snapshots:
            rows = snapshot.get("rows") if isinstance(snapshot.get("rows"), list) else []
            normalized_rows = [item for item in rows if isinstance(item, dict)]
            if not normalized_rows:
                continue
            analyzed = _analyze_snapshot_rows(normalized_rows, keyword_cache=keyword_cache)
            if not _safe_text(analyzed.get("level")):
                continue
            analyzed_rows += _coerce_int(analyzed.get("sample_count"), default=0, minimum=0)
            analyzed_snapshots += 1
            level = _safe_text(analyzed.get("level"))
            if level == "high":
                high_results.append(analyzed)
            elif level == "low":
                low_results.append(analyzed)
            else:
                medium_results.append(analyzed)

        if analyzed_snapshots <= 0:
            summary = _blank_summary()
        elif high_results:
            best = max(high_results, key=lambda item: _coerce_int(item.get("score"), default=0, minimum=0))
            summary = {
                "request_value_level": "high",
                "request_value_label": "高",
                "request_value_reason": _safe_text(best.get("reason")),
                "request_value_score": _coerce_int(best.get("score"), default=0, minimum=0),
                "request_value_snapshot_count": analyzed_snapshots,
                "request_value_sample_count": analyzed_rows,
            }
        elif analyzed_snapshots == len(low_results):
            best = low_results[0] if low_results else {}
            summary = {
                "request_value_level": "low",
                "request_value_label": "低",
                "request_value_reason": _safe_text(best.get("reason")),
                "request_value_score": _coerce_int(best.get("score"), default=0, minimum=0),
                "request_value_snapshot_count": analyzed_snapshots,
                "request_value_sample_count": analyzed_rows,
            }
        else:
            best = max(
                medium_results or low_results,
                key=lambda item: _coerce_int(item.get("score"), default=0, minimum=0),
            )
            summary = {
                "request_value_level": "medium",
                "request_value_label": "中",
                "request_value_reason": _safe_text(best.get("reason")) or "存在混合响应，建议人工复核",
                "request_value_score": _coerce_int(best.get("score"), default=0, minimum=0),
                "request_value_snapshot_count": analyzed_snapshots,
                "request_value_sample_count": analyzed_rows,
            }

    ensure_request_snapshot_schema(REQUEST_DB_FILE)
    now = datetime.now(timezone.utc).isoformat()
    with connect_request_store(REQUEST_DB_FILE) as connection:
        connection.execute(
            """
            INSERT INTO request_analysis_summary (
                domain,
                value_level,
                value_label,
                value_reason,
                value_score,
                snapshot_count,
                sample_count,
                updated_at,
                summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                value_level = excluded.value_level,
                value_label = excluded.value_label,
                value_reason = excluded.value_reason,
                value_score = excluded.value_score,
                snapshot_count = excluded.snapshot_count,
                sample_count = excluded.sample_count,
                updated_at = excluded.updated_at,
                summary_json = excluded.summary_json
            """,
            (
                token,
                _safe_text(summary.get("request_value_level")),
                _safe_text(summary.get("request_value_label")),
                _safe_text(summary.get("request_value_reason")),
                _coerce_int(summary.get("request_value_score"), default=0, minimum=0),
                _coerce_int(summary.get("request_value_snapshot_count"), default=0, minimum=0),
                _coerce_int(summary.get("request_value_sample_count"), default=0, minimum=0),
                now,
                json.dumps(summary, ensure_ascii=False),
            ),
        )
        connection.commit()
    return summary


def analyze_request_run_snapshots(domain: str) -> dict[str, object]:
    summary = load_request_analysis_summary(domain)
    if _safe_text(summary.get("request_value_level")):
        return summary
    return refresh_request_analysis_summary(domain)


__all__ = [
    "analyze_request_run_snapshots",
    "load_request_analysis_summary",
    "refresh_request_analysis_summary",
]
