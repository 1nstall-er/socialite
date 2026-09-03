"""Gateway Socket.IO autenticado para chat y notificaciones en tiempo real."""

from __future__ import annotations

from hmac import compare_digest
from typing import Any

from flask import Flask, current_app, session
from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room

from messaging import ErrorMensajeria, crear_mensaje
from models import Usuario, db
from presenters import mensaje_contexto, notificacion_contexto
from queries import (
    contacto_aceptado,
    marcar_conversacion_leida,
    notificaciones_no_leidas_total,
)
from rate_limit import LimitadorVentanaDeslizante

socketio = SocketIO()


def _sala_usuario(usuario_id: int) -> str:
    return f"usuario:{usuario_id}"


def _sala_chat(usuario_a_id: int, usuario_b_id: int) -> str:
    primero, segundo = sorted((usuario_a_id, usuario_b_id))
    return f"chat:{primero}:{segundo}"


def _usuario_autenticado() -> Usuario | None:
    usuario_id = session.get("usuario_id")
    if not isinstance(usuario_id, int):
        return None
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        return None
    if current_app.config["EMAIL_VERIFICATION_REQUIRED"] and not usuario.correo_verificado:
        return None
    return usuario


def _csrf_valido(auth: Any) -> bool:
    if not current_app.config["CSRF_ENABLED"]:
        return True
    esperado = session.get("_csrf_token")
    recibido = auth.get("csrf_token") if isinstance(auth, dict) else None
    return (
        isinstance(esperado, str)
        and isinstance(recibido, str)
        and compare_digest(esperado, recibido)
    )


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


@socketio.on("connect")  # type: ignore[untyped-decorator]
def conectar(auth: Any = None) -> bool | None:
    usuario = _usuario_autenticado()
    if usuario is None or not _csrf_valido(auth):
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
def entrar_sala(datos: Any) -> dict[str, Any]:
    usuario = _usuario_autenticado()
    contacto_id = _contacto_id(datos)
    if usuario is None:
        return _sesion_invalida()
    if contacto_id is None or not _autorizar_contacto(usuario, contacto_id):
        return _error("chat_no_autorizado", "No tienes acceso a esta conversación.")
    join_room(_sala_chat(usuario.id, contacto_id))
    return {"ok": True, "contacto_id": contacto_id}


@socketio.on("leave_room")  # type: ignore[untyped-decorator]
def salir_sala(datos: Any) -> dict[str, Any]:
    usuario = _usuario_autenticado()
    contacto_id = _contacto_id(datos)
    if usuario is None:
        return _sesion_invalida()
    if contacto_id is None:
        return _error("destinatario_invalido", "La conversación no es válida.")
    leave_room(_sala_chat(usuario.id, contacto_id))
    return {"ok": True, "contacto_id": contacto_id}


@socketio.on("send_message")  # type: ignore[untyped-decorator]
def enviar_mensaje(datos: Any) -> dict[str, Any]:
    usuario = _usuario_autenticado()
    contacto_id = _contacto_id(datos)
    if usuario is None:
        return _sesion_invalida()
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
def marcar_leidos(datos: Any) -> dict[str, Any]:
    usuario = _usuario_autenticado()
    contacto_id = _contacto_id(datos)
    if usuario is None:
        return _sesion_invalida()
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
    )
    app.extensions["socket_message_rate_limiter"] = LimitadorVentanaDeslizante(
        app.config["SOCKET_MESSAGE_MAX"],
        app.config["SOCKET_MESSAGE_WINDOW_SECONDS"],
    )
