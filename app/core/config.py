"""Configuración centralizada y validación de dependencias de producción."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_SECRET_KEY = "clave-local-socialite"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value == "1"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return default if raw is None else int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} debe ser un número entero") from error


def build_config(instance_path: str | Path) -> dict[str, object]:
    """Construye la configuración sin contactar servicios externos."""
    instance = Path(instance_path)
    local_database = (instance / "socialite.db").resolve().as_posix()
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    return {
        "APP_ENV": app_env,
        "SECRET_KEY": os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY),
        "SQLALCHEMY_DATABASE_URI": os.getenv(
            "DATABASE_URL", f"sqlite:///{local_database}"
        ),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "CSRF_ENABLED": True,
        "CORS_ALLOWED_ORIGINS": [
            origin.strip()
            for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        ],
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": _env_bool(
            "COOKIE_SECURE", app_env == "production"
        ),
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=12),
        "MAX_CONTENT_LENGTH": 6 * 1024 * 1024,
        "AVATAR_UPLOAD_FOLDER": os.getenv(
            "AVATAR_UPLOAD_FOLDER", str(instance / "avatares")
        ),
        "AUTO_CREATE_SCHEMA": _env_bool("AUTO_CREATE_SCHEMA", False),
        "SYNC_UPC_CATALOG": _env_bool("SYNC_UPC_CATALOG", True),
        "EMAIL_VERIFICATION_REQUIRED": _env_bool(
            "EMAIL_VERIFICATION_REQUIRED", True
        ),
        "MAIL_BACKEND": os.getenv("MAIL_BACKEND", "console"),
        "MAIL_SERVER": os.getenv("MAIL_SERVER", "localhost"),
        "MAIL_PORT": _env_int("MAIL_PORT", 587),
        "MAIL_USE_TLS": _env_bool("MAIL_USE_TLS", True),
        "MAIL_USE_SSL": _env_bool("MAIL_USE_SSL", False),
        "MAIL_USERNAME": os.getenv("MAIL_USERNAME"),
        "MAIL_PASSWORD": os.getenv("MAIL_PASSWORD"),
        "MAIL_DEFAULT_SENDER": os.getenv(
            "MAIL_DEFAULT_SENDER", "Socialite <no-reply@socialite.local>"
        ),
        "MAIL_TIMEOUT": _env_int("MAIL_TIMEOUT", 10),
        "LOGIN_MAX_FALLOS": _env_int("LOGIN_MAX_FALLOS", 3),
        "LOGIN_VENTANA_SEGUNDOS": _env_int("LOGIN_VENTANA_SEGUNDOS", 60),
        "REENVIO_VENTANA_SEGUNDOS": _env_int(
            "REENVIO_VENTANA_SEGUNDOS", 60
        ),
        "SOCKETIO_ASYNC_MODE": os.getenv("SOCKETIO_ASYNC_MODE", "threading"),
        "SOCKET_MESSAGE_MAX": _env_int("SOCKET_MESSAGE_MAX", 20),
        "SOCKET_MESSAGE_WINDOW_SECONDS": _env_int(
            "SOCKET_MESSAGE_WINDOW_SECONDS", 60
        ),
        "REDIS_URL": os.getenv("REDIS_URL"),
        "SOCKETIO_CHANNEL": os.getenv("SOCKETIO_CHANNEL", "socialite"),
        "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "AWS_SESSION_TOKEN": os.getenv("AWS_SESSION_TOKEN"),
        "AWS_REGION": os.getenv("AWS_REGION"),
        "AWS_S3_BUCKET": os.getenv("AWS_S3_BUCKET"),
        "S3_PUBLIC_BASE_URL": os.getenv("S3_PUBLIC_BASE_URL"),
        "S3_AVATAR_PREFIX": os.getenv("S3_AVATAR_PREFIX", "avatars"),
    }


def _configured(config: Mapping[str, object], name: str) -> bool:
    value = config.get(name)
    return isinstance(value, str) and bool(value.strip())


def validate_production_config(config: Mapping[str, object]) -> None:
    """Falla antes de servir tráfico si producción carece de dependencias."""
    if str(config.get("APP_ENV") or "").lower() != "production":
        return

    errors: list[str] = []
    secret = str(config.get("SECRET_KEY") or "")
    database = str(config.get("SQLALCHEMY_DATABASE_URI") or "")
    redis_url = str(config.get("REDIS_URL") or "")
    public_url = str(config.get("S3_PUBLIC_BASE_URL") or "")

    if not secret or secret == DEFAULT_SECRET_KEY:
        errors.append("secret")
    if not database or database.lower().startswith("sqlite:"):
        errors.append("database")

    mail_fields = (
        "MAIL_SERVER",
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "MAIL_DEFAULT_SENDER",
    )
    if str(config.get("MAIL_BACKEND") or "").lower() != "smtp" or not all(
        _configured(config, field) for field in mail_fields
    ):
        errors.append("smtp")

    try:
        parsed_redis = urlsplit(redis_url)
    except ValueError:
        parsed_redis = None
    if (
        parsed_redis is None
        or parsed_redis.scheme not in {"redis", "rediss"}
        or not parsed_redis.netloc
    ):
        errors.append("redis")
    if not _configured(config, "SOCKETIO_CHANNEL"):
        errors.append("socket_channel")

    s3_fields = (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION",
        "AWS_S3_BUCKET",
    )
    if not all(_configured(config, field) for field in s3_fields):
        errors.append("s3")

    try:
        parsed_public = urlsplit(public_url)
    except ValueError:
        parsed_public = None
    if (
        parsed_public is None
        or parsed_public.scheme != "https"
        or not parsed_public.netloc
        or parsed_public.username is not None
        or parsed_public.password is not None
        or bool(parsed_public.query)
        or bool(parsed_public.fragment)
    ):
        errors.append("public_url")

    prefix = str(config.get("S3_AVATAR_PREFIX") or "")
    if len(prefix) > 128 or not re.fullmatch(
        r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", prefix
    ):
        errors.append("avatar_prefix")

    if errors:
        raise RuntimeError(
            "Configuración de producción inválida: " + ", ".join(errors)
        )
