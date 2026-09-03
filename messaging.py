"""Casos de uso transaccionales para mensajería privada."""

from __future__ import annotations

from dataclasses import dataclass

from models import Mensaje, Notificacion, TipoNotificacion, Usuario, db
from queries import contacto_aceptado, hay_bloqueo_entre


@dataclass(frozen=True, slots=True)
class ErrorMensajeria(Exception):
    mensaje: str
    codigo: str
    estado_http: int = 400

    def __str__(self) -> str:
        return self.mensaje


def crear_mensaje(
    emisor: Usuario, receptor_id: int, texto: str | None
) -> tuple[Mensaje, Notificacion]:
    """Persiste mensaje y alerta en una única transacción.

    La autorización vive aquí para que HTTP y Socket.IO no puedan divergir.
    """
    if receptor_id == emisor.id:
        raise ErrorMensajeria("No puedes enviarte mensajes.", "destinatario_invalido", 400)
    if hay_bloqueo_entre(emisor.id, receptor_id):
        raise ErrorMensajeria(
            "No puedes enviar mensajes a esta persona.", "interaccion_bloqueada", 403
        )

    conexion = contacto_aceptado(emisor.id, receptor_id)
    if conexion is None:
        raise ErrorMensajeria("El chat requiere una conexión aceptada.", "conexion_requerida", 403)

    receptor = conexion.otra_persona(emisor)
    try:
        mensaje = Mensaje(emisor=emisor, receptor=receptor, texto=texto or "")
    except ValueError as error:
        raise ErrorMensajeria(str(error), "mensaje_invalido", 400) from error

    db.session.add(mensaje)
    try:
        db.session.flush()
        vista_previa = mensaje.texto
        if len(vista_previa) > 197:
            vista_previa = f"{vista_previa[:197]}…"
        notificacion = Notificacion(
            usuario=receptor,
            actor=emisor,
            mensaje=mensaje,
            tipo=TipoNotificacion.MENSAJE,
            titulo=f"Nuevo mensaje de {emisor.nombre}",
            contenido=vista_previa,
            destino_url=f"/mensajes/{emisor.id}",
        )
        db.session.add(notificacion)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return mensaje, notificacion
