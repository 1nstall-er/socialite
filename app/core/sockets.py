"""Gateway Socket.IO autenticado para chat y notificaciones en tiempo real."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, Concatenate, ParamSpec, TypeVar

from flask import Flask, current_app, session
from flask_socketio import disconnect, emit, join_room, leave_room

from app.controllers.presenters import mensaje_contexto, notificacion_contexto
from app.core.auth import resolver_identidad_socket
from app.core.rate_limit import LimitadorVentanaDeslizante
from app.extensions import socketio
from app.models.entities import Usuario, db
from app.models.queries import (
    contacto_aceptado,
    marcar_conversacion_leida,
    notificaciones_no_leidas_total,
)
from app.services.messaging import ErrorMensajeria, crear_mensaje

P = ParamSpec("P")
R = TypeVar("R")


def _sala_usuario(usuario_id: int) -> str:
    return f"usuario:{usuario_id}"


def _sala_chat(usuario_a_id: int, usuario_b_id: int) -> str:
    primero, segundo = sorted((usuario_a_id, usuario_b_id))
    return f"chat:{primero}:{segundo}"


def _contacto_id(datos: Any) -> int | None:
    if not isinstance(datos, dict):
        return None
    valor = datos.get("contacto_id")
    if isinstance(valor, bool) or not isinstance(valor, (int, str)):
        return None
    try:
        identificador = int(valor)
    except (TypeError, ValueError):
        return None
    return identificador if identificador > 0 else None


def _error(codigo: str, mensaje: str, *, reintentar_en: int | None = None) -> dict[str, Any]:
    respuesta: dict[str, Any] = {
        "ok": False,
        "error": {"codigo": codigo, "mensaje": mensaje},
    }
    if reintentar_en is not None:
        respuesta["error"]["reintentar_en"] = reintentar_en
    emit("socket_error", respuesta["error"])
    return respuesta


def _autorizar_contacto(usuario: Usuario, contacto_id: int) -> bool:
    return contacto_id != usuario.id and contacto_aceptado(usuario.id, contacto_id) is not None


def _sesion_invalida() -> dict[str, Any]:
    respuesta = _error("no_autenticado", "Tu sesión ya no es válida.")
    disconnect()
    return respuesta


def socket_authenticated(
    handler: Callable[Concatenate[Usuario, P], R],
) -> Callable[P, R | dict[str, Any]]:
    """Revalida la sesión antes de cada operación sensible del socket."""

    @wraps(handler)
    def protected(*args: P.args, **kwargs: P.kwargs) -> R | dict[str, Any]:
        usuario = resolver_identidad_socket()
        if usuario is None:
            return _sesion_invalida()
        return handler(usuario, *args, **kwargs)

    return protected


@socketio.on("connect")  # type: ignore[untyped-decorator]
def conectar(auth: Any = None) -> bool | None:
    usuario = resolver_identidad_socket(auth, exigir_csrf=True)
    if usuario is None:
        return False
    join_room(_sala_usuario(usuario.id))
    current_app.logger.debug("Socket conectado para usuario_id=%s", usuario.id)
    emit(
        "socket_ready",
        {
            "usuario_id": usuario.id,
            "notificaciones_no_leidas": notificaciones_no_leidas_total(usuario.id),
        },
    )
    return None


@socketio.on("disconnect")  # type: ignore[untyped-decorator]
def desconectar(_razon: str | None = None) -> None:
    """Registra el cierre; Flask-SocketIO elimina las salas automáticamente."""
    current_app.logger.debug(
        "Socket desconectado para usuario_id=%s; razon=%s",
        session.get("usuario_id"),
        _razon,
    )


@socketio.on("join_room")  # type: ignore[untyped-decorator]
@socket_authenticated
def entrar_sala(usuario: Usuario, datos: Any) -> dict[str, Any]:
    contacto_id = _contacto_id(datos)
    if contacto_id is None or not _autorizar_contacto(usuario, contacto_id):
        return _error("chat_no_autorizado", "No tienes acceso a esta conversación.")
    join_room(_sala_chat(usuario.id, contacto_id))
    return {"ok": True, "contacto_id": contacto_id}


@socketio.on("leave_room")  # type: ignore[untyped-decorator]
@socket_authenticated
def salir_sala(usuario: Usuario, datos: Any) -> dict[str, Any]:
    contacto_id = _contacto_id(datos)
    if contacto_id is None:
        return _error("destinatario_invalido", "La conversación no es válida.")
    leave_room(_sala_chat(usuario.id, contacto_id))
    return {"ok": True, "contacto_id": contacto_id}


@socketio.on("send_message")  # type: ignore[untyped-decorator]
@socket_authenticated
def enviar_mensaje(usuario: Usuario, datos: Any) -> dict[str, Any]:
    contacto_id = _contacto_id(datos)
    if contacto_id is None or not isinstance(datos, dict):
        return _error("destinatario_invalido", "La conversación no es válida.")

    limitador: LimitadorVentanaDeslizante = current_app.extensions["socket_message_rate_limiter"]
    decision = limitador.consultar(str(usuario.id), consumir=True)
    if not decision.permitido:
        return _error(
            "limite_mensajes",
            "Estás enviando mensajes demasiado rápido.",
            reintentar_en=decision.reintentar_en,
        )

    try:
        mensaje, notificacion = crear_mensaje(usuario, contacto_id, datos.get("texto"))
    except ErrorMensajeria as error:
        return _error(error.codigo, error.mensaje)
    except Exception:
        current_app.logger.exception("Fallo al persistir un mensaje Socket.IO")
        return _error(
            "error_interno", "No pudimos enviar el mensaje. Intenta nuevamente."
        )

    sala_chat = _sala_chat(usuario.id, contacto_id)
    join_room(sala_chat)
    mensaje_datos = mensaje_contexto(mensaje, usuario.id)
    mensaje_evento = {
        clave: valor for clave, valor in mensaje_datos.items() if clave != "propio"
    }
    socketio.emit("message_received", mensaje_evento, to=sala_chat)

    notificacion_datos = notificacion_contexto(notificacion)
    notificacion_datos["total_no_leidas"] = notificaciones_no_leidas_total(contacto_id)
    socketio.emit(
        "notification_received",
        notificacion_datos,
        to=_sala_usuario(contacto_id),
    )
    return {"ok": True, "mensaje": mensaje_datos}


@socketio.on("mark_read")  # type: ignore[untyped-decorator]
@socket_authenticated
def marcar_leidos(usuario: Usuario, datos: Any) -> dict[str, Any]:
    contacto_id = _contacto_id(datos)
    if contacto_id is None or not _autorizar_contacto(usuario, contacto_id):
        return _error("chat_no_autorizado", "No tienes acceso a esta conversación.")

    try:
        mensajes_marcados, notificaciones_marcadas = marcar_conversacion_leida(
            usuario.id, contacto_id
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Fallo al marcar una conversación como leída")
        return _error(
            "error_interno", "No pudimos actualizar la conversación. Intenta nuevamente."
        )
    if mensajes_marcados:
        socketio.emit(
            "messages_read",
            {"lector_id": usuario.id, "contacto_id": contacto_id},
            to=_sala_chat(usuario.id, contacto_id),
        )
    total = notificaciones_no_leidas_total(usuario.id)
    emit("notifications_synced", {"total_no_leidas": total})
    return {
        "ok": True,
        "mensajes_marcados": mensajes_marcados,
        "notificaciones_marcadas": notificaciones_marcadas,
        "total_no_leidas": total,
    }


def inicializar_socketio(app: Flask) -> None:
    """Vincula el gateway al factory sin ampliar CORS a otros orígenes."""
    socketio.init_app(
        app,
        async_mode=app.config["SOCKETIO_ASYNC_MODE"],
        manage_session=True,
        cors_allowed_origins=None,
        max_http_buffer_size=16_384,
        message_queue=app.config.get("REDIS_URL") or None,
        channel=app.config["SOCKETIO_CHANNEL"],
    )
    app.extensions["socket_message_rate_limiter"] = LimitadorVentanaDeslizante(
        app.config["SOCKET_MESSAGE_MAX"],
        app.config["SOCKET_MESSAGE_WINDOW_SECONDS"],
    )
