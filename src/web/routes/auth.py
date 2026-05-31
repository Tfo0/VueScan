from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from src.web.auth_service import (
    AUTH_COOKIE_NAME,
    AUTH_SESSION_DAYS,
    authenticate_user,
    bootstrap_admin_user,
    change_user_password,
    count_users,
    create_auth_session,
    delete_auth_session,
    delete_user_sessions,
    get_session_user,
)


@dataclass(frozen=True)
class AuthRouteDeps:
    json_ok: Callable[..., JSONResponse]
    json_error: Callable[..., JSONResponse]
    database_file: Path


async def _read_json_payload(request: Request) -> dict[str, Any]:
    try:
        raw_payload = await request.json()
    except Exception:
        return {}
    return raw_payload if isinstance(raw_payload, dict) else {}


def _bind_route(
    handler: Callable[[Request, AuthRouteDeps], Awaitable[Any]],
    deps: AuthRouteDeps,
) -> Callable[[Request], Awaitable[Any]]:
    async def endpoint(request: Request):
        return await handler(request, deps)

    endpoint.__name__ = handler.__name__.lstrip("_")
    return endpoint


def _is_secure_request(request: Request) -> bool:
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").strip().lower()
    if forwarded_proto:
        return forwarded_proto.split(",", 1)[0].strip() == "https"
    return request.url.scheme.lower() == "https"


def _set_no_store(response: JSONResponse) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _set_auth_cookie(request: Request, response: JSONResponse, token: str) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=AUTH_SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=_is_secure_request(request),
        path="/",
    )
    _set_no_store(response)


def _clear_auth_cookie(response: JSONResponse) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    _set_no_store(response)


def _current_session_user(request: Request, deps: AuthRouteDeps) -> dict[str, Any] | None:
    token = str(request.cookies.get(AUTH_COOKIE_NAME) or "").strip()
    return get_session_user(database_file=deps.database_file, token=token)


async def _api_auth_session(request: Request, deps: AuthRouteDeps):
    user = _current_session_user(request, deps)
    response = deps.json_ok(
        {
            "authenticated": bool(user),
            "bootstrap_required": count_users(database_file=deps.database_file) == 0,
            "user": user or {},
        }
    )
    _set_no_store(response)
    return response


async def _api_auth_bootstrap(request: Request, deps: AuthRouteDeps):
    if count_users(database_file=deps.database_file) > 0:
        return deps.json_error("bootstrap is not allowed", status_code=403)
    payload = await _read_json_payload(request)
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or not password:
        return deps.json_error("username and password are required", status_code=400)
    if len(password) < 6:
        return deps.json_error("password must be at least 6 characters", status_code=400)
    try:
        user = bootstrap_admin_user(database_file=deps.database_file, username=username, password=password)
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    token = create_auth_session(database_file=deps.database_file, user_id=int(user["id"]))
    response = deps.json_ok(
        {
            "authenticated": True,
            "bootstrap_required": False,
            "user": user,
        }
    )
    _set_auth_cookie(request, response, token)
    return response


async def _api_auth_login(request: Request, deps: AuthRouteDeps):
    payload = await _read_json_payload(request)
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or not password:
        return deps.json_error("username and password are required", status_code=400)
    if count_users(database_file=deps.database_file) == 0:
        return deps.json_error("bootstrap required", status_code=403)
    user = authenticate_user(database_file=deps.database_file, username=username, password=password)
    if not user:
        return deps.json_error("username or password is invalid", status_code=401)
    token = create_auth_session(database_file=deps.database_file, user_id=int(user["id"]))
    response = deps.json_ok(
        {
            "authenticated": True,
            "bootstrap_required": False,
            "user": user,
        }
    )
    _set_auth_cookie(request, response, token)
    return response


async def _api_auth_logout(request: Request, deps: AuthRouteDeps):
    token = str(request.cookies.get(AUTH_COOKIE_NAME) or "").strip()
    if token:
        delete_auth_session(database_file=deps.database_file, token=token)
    response = deps.json_ok({"authenticated": False})
    _clear_auth_cookie(response)
    return response


async def _api_auth_change_password(request: Request, deps: AuthRouteDeps):
    auth_user = getattr(request.state, "auth_user", None)
    username = str(auth_user.get("username") if isinstance(auth_user, dict) else "").strip()
    if not username:
        return deps.json_error("unauthorized", status_code=401)
    payload = await _read_json_payload(request)
    current_password = str(payload.get("current_password") or "")
    new_password = str(payload.get("new_password") or "")
    if not current_password or not new_password:
        return deps.json_error("current_password and new_password are required", status_code=400)
    if len(new_password) < 6:
        return deps.json_error("new password must be at least 6 characters", status_code=400)
    try:
        user = change_user_password(
            database_file=deps.database_file,
            username=username,
            current_password=current_password,
            new_password=new_password,
        )
    except ValueError as exc:
        return deps.json_error(str(exc), status_code=400)
    delete_user_sessions(database_file=deps.database_file, user_id=int(user["id"]))
    token = create_auth_session(database_file=deps.database_file, user_id=int(user["id"]))
    response = deps.json_ok({"user": user})
    _set_auth_cookie(request, response, token)
    return response


def build_auth_routes(deps: AuthRouteDeps) -> list[Route]:
    return [
        Route("/api/auth/session", endpoint=_bind_route(_api_auth_session, deps), methods=["GET"]),
        Route("/api/auth/bootstrap", endpoint=_bind_route(_api_auth_bootstrap, deps), methods=["POST"]),
        Route("/api/auth/login", endpoint=_bind_route(_api_auth_login, deps), methods=["POST"]),
        Route("/api/auth/logout", endpoint=_bind_route(_api_auth_logout, deps), methods=["POST"]),
        Route(
            "/api/auth/change-password",
            endpoint=_bind_route(_api_auth_change_password, deps),
            methods=["POST"],
        ),
    ]


__all__ = ["AuthRouteDeps", "build_auth_routes"]
