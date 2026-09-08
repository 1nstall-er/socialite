"""Connection transitions with server-derived plan context and atomic alerts."""

from __future__ import annotations

from dataclasses import dataclass

from app.extensions import db
from app.models.entities import Conexion, Notificacion, TipoNotificacion, Usuario
from app.models.queries import conexion_entre, hay_bloqueo_entre
from app.services.discovery import construir_propuesta
from app.services.matching import calcular_afinidad


class ErrorConexion(ValueError):
    def __init__(self, mensaje: str, estado: int, propuesta: dict[str, str] | None = None):
        super().__init__(mensaje)
        self.estado = estado
        self.propuesta = propuesta


@dataclass(frozen=True)
class ResultadoConexion:
    conexion: Conexion
    cambio: bool
    notificacion: Notificacion | None = None


def _permitir(actor_id: int, otro_id: int) -> None:
    if actor_id == otro_id:
        raise ErrorConexion("No puedes conectarte contigo mismo.", 400)
    if hay_bloqueo_entre(actor_id, otro_id):
        raise ErrorConexion("No es posible conectar con esta persona.", 403)


def _guardar() -> None:
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def proponer_conexion(
    actor: Usuario, destinatario: Usuario, plan: str | None, vista_previa: str | None,
) -> ResultadoConexion:
    _permitir(actor.id, destinatario.id)
    if plan is not None and plan not in {"estudio", "proyecto", "social"}:
        raise ErrorConexion("Selecciona un plan válido.", 400)
    if plan is None and vista_previa is not None:
        raise ErrorConexion("El tema necesita un plan.", 400)
    conexion = conexion_entre(actor.id, destinatario.id)
    if conexion is not None and conexion.estado in {"pendiente", "aceptada"}:
        return ResultadoConexion(conexion, False)
    tema = None
    if plan is not None:
        propuesta = construir_propuesta(plan, calcular_afinidad(actor, destinatario))
        tema = propuesta["titulo"]
        if vista_previa is not None and vista_previa != tema:
            raise ErrorConexion("La propuesta cambió. Revísala antes de enviarla.", 409, propuesta)
    if conexion is None:
        conexion = Conexion()
        db.session.add(conexion)
    conexion.remitente = actor
    conexion.destinatario = destinatario
    conexion.estado = "pendiente"
    conexion.plan_tipo = plan
    conexion.plan_tema = tema
    notificacion = None
    if plan is not None:
        notificacion = Notificacion(
            usuario_id=destinatario.id, actor_id=actor.id, tipo=TipoNotificacion.INVITACION,
            titulo=f"{actor.nombre} te propone un plan"[:120],
            contenido=tema, destino_url="/conexiones",
        )
        db.session.add(notificacion)
    _guardar()
    return ResultadoConexion(conexion, True, notificacion)


def responder_conexion(actor: Usuario, conexion: Conexion, accion: str) -> ResultadoConexion:
    esperado = conexion.remitente_id if accion == "cancelar" else conexion.destinatario_id
    if actor.id != esperado:
        raise ErrorConexion("No puedes modificar esta invitación.", 403)
    _permitir(conexion.remitente_id, conexion.destinatario_id)
    if accion == "aceptar" and conexion.estado == "aceptada":
        return ResultadoConexion(conexion, False)
    if conexion.estado != "pendiente" or accion not in {"aceptar", "rechazar", "cancelar"}:
        raise ErrorConexion("La invitación ya no está pendiente.", 403)
    notificacion = None
    if accion == "cancelar":
        db.session.delete(conexion)
    else:
        conexion.estado = "aceptada" if accion == "aceptar" else "rechazada"
        if accion == "aceptar" and conexion.plan_tipo:
            notificacion = Notificacion(
                usuario_id=conexion.remitente_id, actor_id=actor.id,
                tipo=TipoNotificacion.CONEXION,
                titulo=f"{actor.nombre} aceptó tu plan"[:120],
                contenido=conexion.plan_tema, destino_url="/conexiones",
            )
            db.session.add(notificacion)
    _guardar()
    return ResultadoConexion(conexion, True, notificacion)
