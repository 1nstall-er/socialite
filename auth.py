"""Validación institucional y defensa del inicio de sesión."""

from __future__ import annotations

from typing import Final

from rate_limit import DecisionLimite, LimitadorVentanaDeslizante

DOMINIOS_PERMITIDOS: Final[tuple[str, ...]] = ("upc.edu.pe",)
MAX_FALLOS_LOGIN: Final[int] = 3
VENTANA_LOGIN_SEGUNDOS: Final[int] = 60


def es_correo_institucional(correo: str | None) -> bool:
    """Devuelve True si el correo pertenece a un dominio universitario permitido.

    Acepta el dominio exacto o un subdominio (por ejemplo alumno.upc.edu.pe).
    """
    if not correo or correo.count("@") != 1 or any(caracter.isspace() for caracter in correo):
        return False
    usuario, dominio = correo.lower().split("@", 1)
    if not usuario or not dominio:
        return False
    return any(
        dominio == permitido or dominio.endswith("." + permitido)
        for permitido in DOMINIOS_PERMITIDOS
    )


def normalizar_clave_ip(direccion_ip: str | None) -> str:
    """Usa exclusivamente la IP resuelta por Flask, no cabeceras falsificables."""
    return (direccion_ip or "desconocido").strip().lower()


def crear_limitador_login(
    max_fallos: int = MAX_FALLOS_LOGIN,
    ventana_segundos: int = VENTANA_LOGIN_SEGUNDOS,
) -> LimitadorVentanaDeslizante:
    return LimitadorVentanaDeslizante(max_fallos, ventana_segundos)


def consultar_login(
    limitador: LimitadorVentanaDeslizante, direccion_ip: str | None
) -> DecisionLimite:
    return limitador.consultar(normalizar_clave_ip(direccion_ip))


def registrar_login_fallido(
    limitador: LimitadorVentanaDeslizante, direccion_ip: str | None
) -> DecisionLimite:
    return limitador.consultar(normalizar_clave_ip(direccion_ip), consumir=True)


def limpiar_fallos_login(
    limitador: LimitadorVentanaDeslizante, direccion_ip: str | None
) -> None:
    limitador.limpiar(normalizar_clave_ip(direccion_ip))
