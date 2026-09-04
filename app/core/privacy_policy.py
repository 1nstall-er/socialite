"""Cumplimiento de datos personales para Socialite (Ley N. 29733, Peru).

Este modulo concentra las tres obligaciones que la ley exige y que el
producto debe poder demostrar ante el area legal de la UPC:

1. Consentimiento versionado: se registra que politica acepto cada
   usuario y cuando, para poder probarlo despues.
2. Derechos ARCO: exportacion completa de los datos del titular y
   eliminacion real de la cuenta (no un simple "desactivado").
3. Retencion: reglas explicitas de cuanto tiempo se guarda cada cosa.

No define modelos aqui para no competir con models.py; recibe las
entidades por parametro. Asi el modulo es testeable sin base de datos
y no obliga a una migracion para poder revisarlo.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

# Version vigente de la politica de privacidad. Al cambiar el texto de la
# politica se sube esta version: los usuarios con una version anterior
# deben volver a aceptar.
VERSION_POLITICA_ACTUAL = "2026-09-01"

# Dias que se conservan los datos de una cuenta tras el egreso o la baja.
# 30 dias da margen para revertir una eliminacion accidental sin volver
# la retencion indefinida.
DIAS_GRACIA_ELIMINACION = 30

# Los reportes de convivencia se conservan mas tiempo porque sustentan
# decisiones de moderacion que pueden ser auditadas.
DIAS_RETENCION_REPORTES = 365


class ConsentimientoPendiente(Exception):
    """El usuario no ha aceptado la version vigente de la politica."""


class EliminacionYaSolicitada(Exception):
    """Ya existe una solicitud de eliminacion activa para el usuario."""


def ahora() -> datetime:
    """Instante actual en UTC, consistente con el resto del dominio."""
    return datetime.now(UTC)


def requiere_consentimiento(version_aceptada: str | None) -> bool:
    """Indica si el usuario debe aceptar la politica vigente.

    Args:
        version_aceptada: version que el usuario acepto, o None si nunca
            acepto ninguna.

    Returns:
        True cuando falta aceptar la version vigente.
    """
    return version_aceptada != VERSION_POLITICA_ACTUAL


def fecha_purga(solicitado_en: datetime, dias_gracia: int = DIAS_GRACIA_ELIMINACION) -> datetime:
    """Fecha en la que una cuenta eliminada se purga de forma definitiva."""
    return solicitado_en + timedelta(days=dias_gracia)


def purga_vencida(solicitado_en: datetime, referencia: datetime | None = None) -> bool:
    """True si ya paso el periodo de gracia y corresponde purgar."""
    momento = referencia or ahora()
    return momento >= fecha_purga(solicitado_en)


def reporte_expirado(creado_en: datetime, referencia: datetime | None = None) -> bool:
    """True si un reporte supero su plazo de retencion."""
    momento = referencia or ahora()
    return momento >= creado_en + timedelta(days=DIAS_RETENCION_REPORTES)


@dataclass(frozen=True)
class RegistroAcceso:
    """Entrada del audit log de accesos a datos personales.

    Se registra quien miro el perfil de quien, para poder responder la
    pregunta que toda universidad hace: como saben que nadie consulta
    datos de estudiantes sin motivo.
    """

    actor_id: int
    titular_id: int
    recurso: str
    momento: datetime = field(default_factory=ahora)

    def como_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "titular_id": self.titular_id,
            "recurso": self.recurso,
            "momento": self.momento.isoformat(),
        }


def _iso(valor: Any) -> Any:
    """Serializa fechas a ISO 8601 y deja el resto intacto."""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return valor


def exportar_datos_usuario(
    usuario: Any,
    mensajes: Iterable[Any] = (),
    conexiones: Iterable[Any] = (),
    grupos: Iterable[Any] = (),
) -> dict[str, Any]:
    """Arma el paquete de datos del titular para el derecho de acceso.

    Incluye lo que el usuario aporto y lo que el sistema derivo de el.
    No incluye datos de terceros: de los mensajes solo se exporta el
    contenido propio, porque el mensaje del otro es dato de ese otro.

    Args:
        usuario: entidad Usuario del titular.
        mensajes: mensajes enviados por el titular.
        conexiones: conexiones aceptadas del titular.
        grupos: grupos a los que pertenece.

    Returns:
        Diccionario serializable a JSON, listo para descargar.
    """
    perfil = {
        "nombre": getattr(usuario, "nombre", None),
        "correo_institucional": getattr(usuario, "correo_institucional", None),
        "biografia": getattr(usuario, "biografia", None),
        "carrera": getattr(usuario, "carrera", None),
        "ciclo": getattr(usuario, "ciclo", None),
        "creado_en": _iso(getattr(usuario, "creado_en", None)),
    }

    return {
        "formato": "socialite-export-v1",
        "generado_en": ahora().isoformat(),
        "titular_id": getattr(usuario, "id", None),
        "perfil": {clave: valor for clave, valor in perfil.items() if valor is not None},
        "cursos": [getattr(c, "codigo", None) for c in getattr(usuario, "cursos", [])],
        "horarios": [
            {
                "dia": getattr(h, "dia", None),
                "hora_inicio": getattr(h, "hora_inicio", None),
                "hora_fin": getattr(h, "hora_fin", None),
            }
            for h in getattr(usuario, "horarios", [])
        ],
        "intereses": list(getattr(usuario, "lista_intereses", []) or []),
        "grupos": [getattr(g, "id", None) for g in grupos],
        "conexiones": [getattr(c, "id", None) for c in conexiones],
        "mensajes_enviados": [
            {"momento": _iso(getattr(m, "creado_en", None)), "contenido": getattr(m, "contenido", None)}
            for m in mensajes
        ],
    }


def anonimizar_usuario(usuario: Any, sufijo: str) -> None:
    """Borra la PII del usuario conservando la integridad referencial.

    Se usa cuando el titular pide eliminacion pero existen registros que
    deben sobrevivir (por ejemplo un reporte de convivencia en revision).
    El resultado no permite reidentificar a la persona.

    Args:
        usuario: entidad Usuario a anonimizar.
        sufijo: valor unico y estable para el correo tecnico resultante.
    """
    usuario.nombre = "Cuenta eliminada"
    usuario.correo_institucional = f"eliminado+{sufijo}@invalido.local"
    usuario.biografia = None
    usuario.foto_archivo = None
    usuario.password_hash = ""
    if hasattr(usuario, "lista_intereses"):
        usuario.lista_intereses = []
    if hasattr(usuario, "activo"):
        usuario.activo = False


def plan_eliminacion(
    usuario: Any,
    borrar: Callable[[Any], None],
    dependencias: dict[str, Iterable[Any]] | None = None,
) -> list[str]:
    """Ejecuta el borrado en cascada de los datos del titular.

    Devuelve la bitacora de lo eliminado para poder demostrar que la
    solicitud se atendio por completo.

    Args:
        usuario: titular que solicito la eliminacion.
        borrar: funcion que elimina una entidad (normalmente
            db.session.delete).
        dependencias: colecciones por nombre a eliminar antes de
            anonimizar al usuario.

    Returns:
        Lista de lineas describiendo que se elimino.
    """
    bitacora: list[str] = []
    for nombre, coleccion in (dependencias or {}).items():
        total = 0
        for entidad in list(coleccion):
            borrar(entidad)
            total += 1
        bitacora.append(f"{nombre}: {total} registros eliminados")

    anonimizar_usuario(usuario, sufijo=str(getattr(usuario, "id", "0")))
    bitacora.append("perfil: PII anonimizada")
    return bitacora
