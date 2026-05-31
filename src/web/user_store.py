from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.web.sqlite_store import connect_web_sqlite, ensure_web_sqlite_schema


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"pbkdf2_sha256${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, password_hash: str) -> bool:
    token = str(password_hash or "")
    if not token.startswith("pbkdf2_sha256$"):
        return False
    try:
        _, salt_token, digest_token = token.split("$", 2)
        salt = base64.b64decode(salt_token.encode())
        expected = base64.b64decode(digest_token.encode())
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return hmac.compare_digest(actual, expected)


def list_users(*, database_file: Path) -> list[dict[str, Any]]:
    ensure_web_sqlite_schema(database_file)
    with connect_web_sqlite(database_file) as connection:
        rows = connection.execute(
            """
            SELECT id, username, disabled, created_at, updated_at
            FROM users
            ORDER BY id ASC
            """
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "username": str(row["username"]),
            "disabled": bool(int(row["disabled"])),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    ]


def get_user_by_username(*, database_file: Path, username: str) -> dict[str, Any] | None:
    token = str(username or "").strip()
    if not token:
        return None
    ensure_web_sqlite_schema(database_file)
    with connect_web_sqlite(database_file) as connection:
        row = connection.execute(
            """
            SELECT id, username, password_hash, disabled, created_at, updated_at
            FROM users
            WHERE username = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "username": str(row["username"]),
        "password_hash": str(row["password_hash"]),
        "disabled": bool(int(row["disabled"])),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def create_user(*, database_file: Path, username: str, password: str, disabled: bool = False) -> dict[str, Any]:
    token = str(username or "").strip()
    if not token:
        raise ValueError("username is required")
    if not password:
        raise ValueError("password is required")
    ensure_web_sqlite_schema(database_file)
    now = _utc_now()
    with connect_web_sqlite(database_file) as connection:
        connection.execute(
            """
            INSERT INTO users(username, password_hash, disabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token, hash_password(password), 1 if disabled else 0, now, now),
        )
        connection.commit()
    return get_user_by_username(database_file=database_file, username=token) or {}


def update_user_password(*, database_file: Path, username: str, password: str) -> dict[str, Any] | None:
    token = str(username or "").strip()
    if not token:
        raise ValueError("username is required")
    if not password:
        raise ValueError("password is required")
    ensure_web_sqlite_schema(database_file)
    with connect_web_sqlite(database_file) as connection:
        connection.execute(
            """
            UPDATE users
            SET password_hash = ?, updated_at = ?
            WHERE username = ?
            """,
            (hash_password(password), _utc_now(), token),
        )
        connection.commit()
    return get_user_by_username(database_file=database_file, username=token)


__all__ = [
    "create_user",
    "get_user_by_username",
    "hash_password",
    "list_users",
    "update_user_password",
    "verify_password",
]
