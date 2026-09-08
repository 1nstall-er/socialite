from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    request,
    url_for,
)

from app.controllers.common import (
    _destino_seguro,
    renderizar_contrato,
)
from app.controllers.presenters import (
    conexion_contexto,
    notificacion_contexto,
)
from app.core.auth import (
    login_required,
)
from app.extensions import socketio
from app.models.entities import (
    Conexion,
    Usuario,
    db,
)
from app.models.queries import (
    conexiones_de,
    notificaciones_no_leidas_total,
)
from app.services.connections import (
    ErrorConexion,
    ResultadoConexion,
    proponer_conexion,
    responder_conexion,
)

bp = Blueprint("connections", __name__)


def _json_solicitado():
    return request.accept_mimetypes.best_match(["text/html", "application/json"]) == "application/json"


def _error(error):
    if _json_solicitado():
        return jsonify(ok=False, error=str(error), propuesta=error.propuesta), error.estado
    abort(error.estado, description=str(error))


def _respuesta(resultado: ResultadoConexion, siguiente: str, *, aceptar: bool = False):
    if resultado.notificacion is not None:
        notification = resultado.notificacion
        try:
            payload = notificacion_contexto(notification)
            payload['total_no_leidas'] = notificaciones_no_leidas_total(notification.usuario_id)
            socketio.emit('notification_received', payload, to=f'usuario:{notification.usuario_id}')
        except Exception:
            current_app.logger.exception('No se pudo emitir la alerta; permanece guardada')
    if _json_solicitado():
        return jsonify(
            ok=True, conexion=conexion_contexto(resultado.conexion, g.usuario),
            match=aceptar and resultado.cambio, siguiente=siguiente,
        )
    return redirect(siguiente)


@bp.route("/conexiones")
@login_required
def conexiones():
    todas = conexiones_de(g.usuario.id)
    contrato = {
        "recibidas": [
            conexion_contexto(item, g.usuario)
            for item in todas
            if item.estado == "pendiente" and item.destinatario_id == g.usuario.id
        ],
        "enviadas": [
            conexion_contexto(item, g.usuario)
            for item in todas
            if item.estado == "pendiente" and item.remitente_id == g.usuario.id
        ],
        "aceptadas": [
            conexion_contexto(item, g.usuario) for item in todas if item.estado == "aceptada"
        ],
    }
    return renderizar_contrato("conexiones.html", contrato, **contrato)


@bp.post("/companeros/<int:usuario_id>/conectar")
@login_required
def solicitar_conexion(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    try:
        resultado = proponer_conexion(
            g.usuario, usuario, request.form.get("plan"), request.form.get("plan_tema"),
        )
    except ErrorConexion as error:
        return _error(error)
    if resultado.cambio:
        flash(f"Solicitud enviada a {usuario.nombre}.", "success")
    elif resultado.conexion.estado == "aceptada":
        flash("Ya estan conectados.", "info")
    else:
        flash("Ya existe una solicitud pendiente.", "info")
    return _respuesta(resultado,
        _destino_seguro(request.form.get("siguiente"), url_for("companions.companeros"))
    )


@bp.post("/conexiones/<int:conexion_id>/aceptar")
@login_required
def aceptar_conexion(conexion_id):
    conexion = db.get_or_404(Conexion, conexion_id)
    try:
        resultado = responder_conexion(g.usuario, conexion, "aceptar")
    except ErrorConexion as error:
        return _error(error)
    flash("Conexion aceptada.", "success")
    return _respuesta(resultado, url_for("connections.conexiones"), aceptar=True)


@bp.post("/conexiones/<int:conexion_id>/rechazar")
@login_required
def rechazar_conexion(conexion_id):
    conexion = db.get_or_404(Conexion, conexion_id)
    try:
        resultado = responder_conexion(g.usuario, conexion, "rechazar")
    except ErrorConexion as error:
        return _error(error)
    flash("Solicitud descartada.", "info")
    return _respuesta(resultado, url_for("connections.conexiones"))


@bp.post("/conexiones/<int:conexion_id>/cancelar")
@login_required
def cancelar_conexion(conexion_id):
    conexion = db.get_or_404(Conexion, conexion_id)
    try:
        resultado = responder_conexion(g.usuario, conexion, "cancelar")
    except ErrorConexion as error:
        return _error(error)
    flash("Solicitud cancelada.", "info")
    return _respuesta(resultado, url_for("connections.conexiones"))
