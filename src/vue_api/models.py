from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ApiEndpoint:
    id: int
    method: str
    path: str
    url: str
    source_file: str
    source_line: int
    match_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApiEndpoint":
        return cls(
            id=int(data["id"]),
            method=str(data.get("method", "GET")).upper(),
            path=str(data.get("path", "")),
            url=str(data.get("url", "")),
            source_file=str(data.get("source_file", "")),
            source_line=int(data.get("source_line", 0)),
            match_text=str(data.get("match_text", "")),
        )


def serialize_api_endpoint(endpoint: Any) -> dict[str, Any]:
    # Web 层和 VueApi 业务层都需要稳定的 endpoint 字典结构，统一收口到这里。
    if hasattr(endpoint, "to_dict") and callable(getattr(endpoint, "to_dict")):
        try:
            payload = endpoint.to_dict()
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    return {
        "id": int(getattr(endpoint, "id", 0) or 0),
        "method": str(getattr(endpoint, "method", "GET") or "GET").upper(),
        "path": str(getattr(endpoint, "path", "") or ""),
        "url": str(getattr(endpoint, "url", "") or ""),
        "source_file": str(getattr(endpoint, "source_file", "") or ""),
        "source_line": int(getattr(endpoint, "source_line", 0) or 0),
        "match_text": str(getattr(endpoint, "match_text", "") or ""),
    }


@dataclass(slots=True)
class ApiProfile:
    name: str
    baseurl: str
    baseapi: str
    pattern: str
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApiProfile":
        created_at = str(data.get("created_at") or utc_now_iso())
        updated_at = str(data.get("updated_at") or created_at)
        return cls(
            name=str(data["name"]),
            baseurl=str(data.get("baseurl", "")),
            baseapi=str(data.get("baseapi", "")),
            pattern=str(data.get("pattern", "")),
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass(slots=True)
class ApiCallResult:
    endpoint_id: int
    method: str
    url: str
    status_code: int
    ok: bool
    elapsed_ms: int
    response_headers: dict[str, str]
    response_text: str
    error: str
    request_body: Any
    requested_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApiCallResult":
        return cls(
            endpoint_id=int(data.get("endpoint_id", 0)),
            method=str(data.get("method", "GET")).upper(),
            url=str(data.get("url", "")),
            status_code=int(data.get("status_code", 0)),
            ok=bool(data.get("ok", False)),
            elapsed_ms=int(data.get("elapsed_ms", 0)),
            response_headers=dict(data.get("response_headers") or {}),
            response_text=str(data.get("response_text", "")),
            error=str(data.get("error", "")),
            request_body=data.get("request_body"),
            requested_at=str(data.get("requested_at") or utc_now_iso()),
        )
