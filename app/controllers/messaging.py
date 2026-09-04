from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    request,
    url_for,
)

from app.controllers.common import (
    renderizar_contrato,
)
from app.controllers.contexts import (
    contexto_bandeja_mensajes,
)
from app.controllers.presenters import (
    mensaje_contexto,
)
from app.core.auth import (
    login_required,
)
from app.models.entities import (
    db,
)
from app.models.queries import (
    contacto_aceptado,
    hay_bloqueo_entre,
    marcar_conversacion_leida,
    mensajes_entre,
)
from app.services.messaging import ErrorMensajeria, crear_mensaje

bp = Blueprint("messaging", __name__)


@bp.get("/mensajes")
@login_required
def mensajes():
    contrato = contexto_bandeja_mensajes()
    return renderizar_contrato("mensajes.html", contrato, **contrato)


@bp.get("/api/v1/mensajes")
@login_required
def api_mensajes():
    return jsonify(contexto_bandeja_mensajes())


@bp.route("/mensajes/<int:usuario_id>", methods=["GET", "POST"])
@login_required
def conversacion(usuario_id):
    if usuario_id == g.usuario.id:
        abort(400, description="No puedes enviarte mensajes.")
    if hay_bloqueo_entre(g.usuario.id, usuario_id):
        abort(404)
    conexion = contacto_aceptado(g.usuario.id, usuario_id)
    if conexion is None:
        abort(403, description="El chat requiere una conexión aceptada.")
    contacto = conexion.otra_persona(g.usuario)
    if request.method == "POST":
        try:
            crear_mensaje(g.usuario, contacto.id, request.form.get("texto"))
        except ErrorMensajeria as error:
            flash(str(error), "error")
        else:
            flash("Mensaje enviado.", "success")
        return (redirect(url_for("messaging.conversacion", usuario_id=contacto.id)), 303)
    antes_de_id = request.args.get("antes_de", type=int)
    historial = mensajes_entre(g.usuario.id, contacto.id, limite=51, antes_de_id=antes_de_id)
    hay_anteriores = len(historial) > 50
    if hay_anteriores:
        historial = historial[-50:]
    mensajes_marcados, notificaciones_marcadas = marcar_conversacion_leida(
        g.usuario.id, contacto.id
    )
    mensajes_serializados = [mensaje_contexto(mensaje, g.usuario.id) for mensaje in historial]
    if mensajes_marcados or notificaciones_marcadas:
        db.session.commit()
    contrato = {
        "contacto": {
            "id": contacto.id,
            "nombre": contacto.nombre,
            "iniciales": contacto.iniciales,
            "foto_url": contacto.foto_url,
            "carrera": contacto.carrera,
            "ciclo": contacto.ciclo,
        },
        "mensajes": mensajes_serializados,
        "paginacion": {
            "hay_anteriores": hay_anteriores,
            "antes_de": historial[0].id if historial and hay_anteriores else None,
            "limite": 50,
        },
    }
    return renderizar_contrato(
        "conversacion.html",
        contrato,
        contacto=contrato["contacto"],
        mensajes=contrato["mensajes"],
        paginacion=contrato["paginacion"],
    )


@bp.get("/api/v1/mensajes/<int:usuario_id>")
@login_required
def api_conversacion(usuario_id):
    if usuario_id == g.usuario.id or hay_bloqueo_entre(g.usuario.id, usuario_id):
        abort(404)
    conexion = contacto_aceptado(g.usuario.id, usuario_id)
    if conexion is None:
        abort(403)
    historial = mensajes_entre(
        g.usuario.id,
        usuario_id,
        limite=request.args.get("limite", default=50, type=int),
        antes_de_id=request.args.get("antes_de", type=int),
    )
    marcar_conversacion_leida(g.usuario.id, usuario_id)
    mensajes_serializados = [mensaje_contexto(mensaje, g.usuario.id) for mensaje in historial]
    db.session.commit()
    return jsonify({"contacto_id": usuario_id, "mensajes": mensajes_serializados})
