"""Creación y validación de retos de verificación de correo."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final, Protocol

from app.core.rate_limit import DecisionLimite, LimitadorVentanaDeslizante

CODIGO_DIGITOS: Final[int] = 6
VIGENCIA_MINUTOS: Final[int] = 15
REENVIO_SEGUNDOS: Final[int] = 60
MAX_INTENTOS: Final[int] = 5
MAX_REENVIOS_POR_VENTANA: Final[int] = 1


class UsuarioVerificable(Protocol):
    id: int
    correo_institucional: str
    correo_verificado_en: datetime | None
    verificacion_codigo_hash: str | None
    verificacion_expira_en: datetime | None
    verificacion_enviada_en: datetime | None
    verificacion_intentos: int


class ResultadoVerificacion(StrEnum):
    VALIDO = "valido"
    INVALIDO = "invalido"
    EXPIRADO = "expirado"
    AGOTADO = "agotado"


def crear_limitador_reenvio(
    ventana_segundos: int = REENVIO_SEGUNDOS,
) -> LimitadorVentanaDeslizante:
    return LimitadorVentanaDeslizante(MAX_REENVIOS_POR_VENTANA, ventana_segundos)


def limitar_reenvio(
    limitador: LimitadorVentanaDeslizante,
    usuario_id: int,
    direccion_ip: str | None,
) -> DecisionLimite:
    clave = f"{usuario_id}:{(direccion_ip or 'desconocido').strip().lower()}"
    return limitador.consultar(clave, consumir=True)


def ahora_utc() -> datetime:
    """UTC sin zona para mantener comparaciones consistentes también en SQLite."""
    return datetime.now(UTC).replace(tzinfo=None)


def _resumen_codigo(
    secreto: str, usuario_id: int, correo: str, codigo: str
) -> str:
    mensaje = f"{usuario_id}:{correo.lower()}:{codigo}".encode()
    return hmac.new(secreto.encode(), mensaje, hashlib.sha256).hexdigest()


def preparar_reto(
    usuario: UsuarioVerificable,
    secreto: str,
    instante: datetime | None = None,
) -> str:
    instante = instante or ahora_utc()
    codigo = f"{secrets.randbelow(10**CODIGO_DIGITOS):0{CODIGO_DIGITOS}d}"
    usuario.verificacion_codigo_hash = _resumen_codigo(
        secreto, usuario.id, usuario.correo_institucional, codigo
    )
    usuario.verificacion_expira_en = instante + timedelta(minutes=VIGENCIA_MINUTOS)
    usuario.verificacion_enviada_en = instante
    usuario.verificacion_intentos = 0
    return codigo


def segundos_para_reenviar(
    usuario: UsuarioVerificable, instante: datetime | None = None
) -> int:
    if usuario.verificacion_enviada_en is None:
        return 0
    instante = instante or ahora_utc()
    restante = REENVIO_SEGUNDOS - int(
        (instante - usuario.verificacion_enviada_en).total_seconds()
    )
    return max(restante, 0)


def validar_codigo(
    usuario: UsuarioVerificable,
    secreto: str,
    codigo: str,
    instante: datetime | None = None,
) -> ResultadoVerificacion:
    instante = instante or ahora_utc()
    if (
        usuario.verificacion_codigo_hash is None
        or usuario.verificacion_expira_en is None
        or instante >= usuario.verificacion_expira_en
    ):
        return ResultadoVerificacion.EXPIRADO
    if usuario.verificacion_intentos >= MAX_INTENTOS:
        return ResultadoVerificacion.AGOTADO

    limpio = codigo.strip()
    esperado = _resumen_codigo(
        secreto, usuario.id, usuario.correo_institucional, limpio
    )
    if (
        len(limpio) != CODIGO_DIGITOS
        or not limpio.isdigit()
        or not hmac.compare_digest(usuario.verificacion_codigo_hash, esperado)
    ):
        usuario.verificacion_intentos += 1
        return (
            ResultadoVerificacion.AGOTADO
            if usuario.verificacion_intentos >= MAX_INTENTOS
            else ResultadoVerificacion.INVALIDO
        )
    return ResultadoVerificacion.VALIDO


def completar_verificacion(
    usuario: UsuarioVerificable, instante: datetime | None = None
) -> None:
    usuario.correo_verificado_en = instante or ahora_utc()
    usuario.verificacion_codigo_hash = None
    usuario.verificacion_expira_en = None
    usuario.verificacion_enviada_en = None
    usuario.verificacion_intentos = 0
