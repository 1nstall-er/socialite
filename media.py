"""Procesamiento seguro y determinista de las fotos de perfil."""

from __future__ import annotations

import os
import secrets
import warnings
from io import BytesIO
from pathlib import Path
from typing import Final

from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

MAX_FOTO_BYTES: Final[int] = 5 * 1024 * 1024
MIN_LADO_FOTO: Final[int] = 200
TAMANO_AVATAR: Final[tuple[int, int]] = (640, 640)
FORMATOS_FOTO: Final[frozenset[str]] = frozenset({"JPEG", "PNG", "WEBP"})


def guardar_avatar(archivo: FileStorage | None, carpeta: str | Path) -> str:
    """Valida, normaliza y persiste una foto sin conservar metadatos.

    La extensión enviada por el cliente no se considera confiable. Pillow abre el
    contenido real, se aplica la orientación EXIF y el resultado siempre se vuelve
    a codificar como JPEG cuadrado. El reemplazo en disco es atómico.
    """
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

    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    nombre = f"{secrets.token_urlsafe(24)}.jpg"
    ruta_final = destino / nombre
    ruta_temporal = destino / f".{nombre}.tmp"
    try:
        avatar.save(
            ruta_temporal,
            format="JPEG",
            quality=88,
            optimize=True,
            progressive=True,
        )
        os.replace(ruta_temporal, ruta_final)
    finally:
        ruta_temporal.unlink(missing_ok=True)
    return nombre


def eliminar_avatar(nombre: str | None, carpeta: str | Path) -> None:
    """Elimina únicamente nombres generados por :func:`guardar_avatar`."""
    if not nombre or Path(nombre).name != nombre or not nombre.endswith(".jpg"):
        return
    (Path(carpeta) / nombre).unlink(missing_ok=True)
