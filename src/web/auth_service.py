from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.web.sqlite_store import connect_web_sqlite, ensure_web_sqlite_schema
from src.web.user_store import (
    create_user,
    get_user_by_username,
    update_user_password,
    verify_password,
)


AUTH_COOKIE_NAME = "vuescan_session"
AUTH_SESSION_DAYS = 30


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_text() -> str:
    return _utc_now().isoformat(timespec="seconds")


def _expiry_text(days: int = AUTH_SESSION_DAYS) -> str:
    return (_utc_now() + timedelta(days=days)).isoformat(timespec="seconds")


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def count_users(*, database_file: Path) -> int:
    ensure_web_sqlite_schema(database_file)
    with connect_web_sqlite(database_file) as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    return int(row["total"]) if row else 0


def _public_user_row(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "username": str(row["username"]),
        "disabled": bool(int(row["disabled"])),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def create_auth_session(*, database_file: Path, user_id: int) -> str:
    ensure_web_sqlite_schema(database_file)
    token = secrets.token_urlsafe(32)
    with connect_web_sqlite(database_file) as connection:
        connection.execute(
            """
            INSERT INTO auth_sessions(token_hash, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (_token_hash(token), int(user_id), _utc_now_text(), _expiry_text()),
        )
        connection.commit()
    return token


def delete_auth_session(*, database_file: Path, token: str) -> None:
    if not str(token or "").strip():
        return
    ensure_web_sqlite_schema(database_file)
    with connect_web_sqlite(database_file) as connection:
        connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(token),))
        connection.commit()


def delete_user_sessions(*, database_file: Path, user_id: int) -> None:
    ensure_web_sqlite_schema(database_file)
    with connect_web_sqlite(database_file) as connection:
        connection.execute("DELETE FROM auth_sessions WHERE user_id = ?", (int(user_id),))
        connection.commit()


def get_session_user(*, database_file: Path, token: str) -> dict[str, Any] | None:
    raw_token = str(token or "").strip()
    if not raw_token:
        return None
    ensure_web_sqlite_schema(database_file)
    now_text = _utc_now_text()
    with connect_web_sqlite(database_file) as connection:
        connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now_text,))
        row = connection.execute(
            """
            SELECT users.id, users.username, users.disabled, users.created_at, users.updated_at
            FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ?
            """,
            (_token_hash(raw_token), now_text),
        ).fetchone()
        if row is not None:
            connection.execute(
                """
                UPDATE auth_sessions
                SET expires_at = ?
                WHERE token_hash = ?
                """,
                (_expiry_text(), _token_hash(raw_token)),
            )
        connection.commit()
    if not row:
        return None
    return _public_user_row(row)


def authenticate_user(*, database_file: Path, username: str, password: str) -> dict[str, Any] | None:
    row = get_user_by_username(database_file=database_file, username=username)
    if not row or bool(row.get("disabled")):
        return None
    if not verify_password(password, str(row.get("password_hash") or "")):
        return None
    return {
        "id": int(row["id"]),
        "username": str(row["username"]),
        "disabled": bool(row["disabled"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def bootstrap_admin_user(*, database_file: Path, username: str, password: str) -> dict[str, Any]:
    if count_users(database_file=database_file) > 0:
        raise ValueError("bootstrap is not allowed")
    return create_user(database_file=database_file, username=username, password=password, disabled=False)


def change_user_password(
    *,
    database_file: Path,
    username: str,
    current_password: str,
    new_password: str,
) -> dict[str, Any]:
    user = authenticate_user(database_file=database_file, username=username, password=current_password)
    if not user:
        raise ValueError("current password is invalid")
    updated = update_user_password(database_file=database_file, username=username, password=new_password)
    if not updated:
        raise ValueError("user not found")
    return {
        "id": int(updated["id"]),
        "username": str(updated["username"]),
        "disabled": bool(updated["disabled"]),
        "created_at": str(updated["created_at"]),
        "updated_at": str(updated["updated_at"]),
    }


__all__ = [
    "AUTH_COOKIE_NAME",
    "AUTH_SESSION_DAYS",
    "authenticate_user",
    "bootstrap_admin_user",
    "change_user_password",
    "count_users",
    "create_auth_session",
    "delete_auth_session",
    "delete_user_sessions",
    "get_session_user",
]
