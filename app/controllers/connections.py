from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    g,
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
)
from app.core.auth import (
    login_required,
)
from app.models.entities import (
    Conexion,
    Usuario,
    db,
)
from app.models.queries import (
    conexion_entre,
    conexiones_de,
    hay_bloqueo_entre,
)

bp = Blueprint("connections", __name__)


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
    if usuario.id == g.usuario.id:
        abort(400, description="No puedes conectarte contigo mismo.")
    if hay_bloqueo_entre(g.usuario.id, usuario.id):
        abort(403, description="No es posible conectar con esta persona.")
    conexion = conexion_entre(g.usuario.id, usuario.id)
    if conexion is None:
        conexion = Conexion(remitente=g.usuario, destinatario=usuario, estado="pendiente")
        db.session.add(conexion)
        db.session.commit()
        flash(f"Solicitud enviada a {usuario.nombre}.", "success")
    elif conexion.estado == "rechazada":
        conexion.remitente = g.usuario
        conexion.destinatario = usuario
        conexion.estado = "pendiente"
        db.session.commit()
        flash(f"Nueva solicitud enviada a {usuario.nombre}.", "success")
    elif conexion.estado == "aceptada":
        flash("Ya estan conectados.", "info")
    else:
        flash("Ya existe una solicitud pendiente.", "info")
    return redirect(
        _destino_seguro(request.form.get("siguiente"), url_for("companions.companeros"))
    )


@bp.post("/conexiones/<int:conexion_id>/aceptar")
@login_required
def aceptar_conexion(conexion_id):
    conexion = db.get_or_404(Conexion, conexion_id)
    if conexion.destinatario_id != g.usuario.id or conexion.estado != "pendiente":
        abort(403)
    conexion.estado = "aceptada"
    db.session.commit()
    flash("Conexion aceptada.", "success")
    return redirect(url_for("connections.conexiones"))


@bp.post("/conexiones/<int:conexion_id>/rechazar")
@login_required
def rechazar_conexion(conexion_id):
    conexion = db.get_or_404(Conexion, conexion_id)
    if conexion.destinatario_id != g.usuario.id or conexion.estado != "pendiente":
        abort(403)
    conexion.estado = "rechazada"
    db.session.commit()
    flash("Solicitud descartada.", "info")
    return redirect(url_for("connections.conexiones"))


@bp.post("/conexiones/<int:conexion_id>/cancelar")
@login_required
def cancelar_conexion(conexion_id):
    conexion = db.get_or_404(Conexion, conexion_id)
    if conexion.remitente_id != g.usuario.id or conexion.estado != "pendiente":
        abort(403)
    db.session.delete(conexion)
    db.session.commit()
    flash("Solicitud cancelada.", "info")
    return redirect(url_for("connections.conexiones"))
