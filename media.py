"""Validación de avatares y almacenamiento privado en AWS S3."""

from __future__ import annotations

import re
import secrets
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Final
from urllib.parse import quote, unquote, urlsplit

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

MAX_FOTO_BYTES: Final[int] = 5 * 1024 * 1024
MIN_LADO_FOTO: Final[int] = 200
TAMANO_AVATAR: Final[tuple[int, int]] = (640, 640)
FORMATOS_FOTO: Final[frozenset[str]] = frozenset({"JPEG", "PNG", "WEBP"})
AVATAR_TOKEN_PATTERN: Final[str] = r"[A-Za-z0-9_-]{24,80}\.jpg"
S3_CACHE_CONTROL: Final[str] = "public, max-age=31536000, immutable"


class MediaStorageError(RuntimeError):
    """Fallo remoto seguro para presentar sin filtrar datos del proveedor."""


@dataclass(frozen=True, slots=True)
class S3Settings:
    access_key_id: str
    secret_access_key: str
    session_token: str | None
    region: str
    bucket: str
    public_base_url: str
    avatar_prefix: str

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> S3Settings:
        names = (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION",
            "AWS_S3_BUCKET",
            "S3_PUBLIC_BASE_URL",
            "S3_AVATAR_PREFIX",
        )
        values = {name: str(config.get(name) or "").strip() for name in names}
        if not all(values.values()):
            raise MediaStorageError(
                "El almacenamiento de imágenes no está configurado."
            )

        try:
            public = urlsplit(values["S3_PUBLIC_BASE_URL"])
        except ValueError as error:
            raise MediaStorageError(
                "La configuración pública de imágenes no es válida."
            ) from error
        prefix = values["S3_AVATAR_PREFIX"].strip("/")
        prefix_is_valid = len(prefix) <= 128 and re.fullmatch(
            r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", prefix
        )
        if (
            public.scheme != "https"
            or not public.netloc
            or public.username is not None
            or public.password is not None
            or bool(public.query)
            or bool(public.fragment)
            or unquote(public.path) != public.path
            or not prefix_is_valid
        ):
            raise MediaStorageError(
                "La configuración pública de imágenes no es válida."
            )

        return cls(
            access_key_id=values["AWS_ACCESS_KEY_ID"],
            secret_access_key=values["AWS_SECRET_ACCESS_KEY"],
            session_token=str(config.get("AWS_SESSION_TOKEN") or "").strip() or None,
            region=values["AWS_REGION"],
            bucket=values["AWS_S3_BUCKET"],
            public_base_url=values["S3_PUBLIC_BASE_URL"].rstrip("/"),
            avatar_prefix=prefix,
        )


def _normalize_avatar(archivo: FileStorage | None) -> BytesIO:
    if archivo is None or not archivo.filename:
        raise ValueError("Selecciona una foto de perfil.")

    contenido = archivo.stream.read(MAX_FOTO_BYTES + 1)
    if not contenido:
        raise ValueError("La foto seleccionada está vacía.")
    if len(contenido) > MAX_FOTO_BYTES:
        raise ValueError("La foto debe pesar como máximo 5 MB.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contenido)) as imagen_verificada:
                formato = imagen_verificada.format
                imagen_verificada.verify()
            if formato not in FORMATOS_FOTO:
                raise ValueError("Usa una foto JPG, PNG o WebP.")

            with Image.open(BytesIO(contenido)) as original:
                orientada = ImageOps.exif_transpose(original)
                if min(orientada.size) < MIN_LADO_FOTO:
                    raise ValueError(
                        f"La foto debe medir al menos {MIN_LADO_FOTO} × "
                        f"{MIN_LADO_FOTO} píxeles."
                    )
                if "A" in orientada.getbands():
                    rgba = orientada.convert("RGBA")
                    normalizada = Image.new("RGB", rgba.size, (247, 246, 240))
                    normalizada.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    normalizada = orientada.convert("RGB")
                avatar = ImageOps.fit(
                    normalizada,
                    TAMANO_AVATAR,
                    method=Image.Resampling.LANCZOS,
                )
    except ValueError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("La resolución de la foto es demasiado grande.") from None
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError("El archivo no contiene una imagen válida.") from None

    buffer = BytesIO()
    avatar.save(
        buffer,
        format="JPEG",
        quality=88,
        optimize=True,
        progressive=True,
    )
    buffer.seek(0)
    return buffer


def _s3_client(settings: S3Settings) -> Any:
    credentials = {
        "region_name": settings.region,
        "aws_access_key_id": settings.access_key_id,
        "aws_secret_access_key": settings.secret_access_key,
    }
    if settings.session_token:
        credentials["aws_session_token"] = settings.session_token
    return boto3.client("s3", **credentials)


def _owned_avatar_key(public_url: str, settings: S3Settings) -> str | None:
    base = urlsplit(settings.public_base_url)
    try:
        candidate = urlsplit(public_url)
    except ValueError:
        return None
    if (
        candidate.scheme != base.scheme
        or candidate.netloc != base.netloc
        or candidate.username is not None
        or candidate.password is not None
        or bool(candidate.query)
        or bool(candidate.fragment)
        or unquote(candidate.path) != candidate.path
    ):
        return None

    base_path = base.path.rstrip("/")
    relative_prefix = f"{base_path}/" if base_path else "/"
    if not candidate.path.startswith(relative_prefix):
        return None
    key = candidate.path.removeprefix(relative_prefix)
    owned_pattern = rf"{re.escape(settings.avatar_prefix)}/{AVATAR_TOKEN_PATTERN}"
    return key if re.fullmatch(owned_pattern, key) else None


def upload_image(archivo: FileStorage | None) -> str:
    """Normaliza una imagen, la sube a S3 y devuelve su URL pública HTTPS."""
    settings = S3Settings.from_config(current_app.config)
    stream = _normalize_avatar(archivo)
    key = f"{settings.avatar_prefix}/{secrets.token_urlsafe(24)}.jpg"
    try:
        _s3_client(settings).upload_fileobj(
            stream,
            settings.bucket,
            key,
            ExtraArgs={
                "ContentType": "image/jpeg",
                "CacheControl": S3_CACHE_CONTROL,
                "ServerSideEncryption": "AES256",
            },
        )
    except (BotoCoreError, ClientError, S3UploadFailedError) as error:
        raise MediaStorageError(
            "No pudimos almacenar la foto. Intenta nuevamente."
        ) from error
    return f"{settings.public_base_url}/{quote(key, safe='/')}"


def delete_image(public_url: str | None) -> None:
    """Borra solo URLs propias que pertenecen al prefijo aislado de avatares."""
    if not public_url:
        return
    settings = S3Settings.from_config(current_app.config)
    key = _owned_avatar_key(public_url, settings)
    if key is None:
        return
    try:
        _s3_client(settings).delete_object(Bucket=settings.bucket, Key=key)
    except (BotoCoreError, ClientError) as error:
        raise MediaStorageError("No pudimos eliminar la foto remota.") from error
