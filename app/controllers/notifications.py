from __future__ import annotations

from flask import (
    Blueprint,
    abort,
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
    notificacion_contexto,
)
from app.core.auth import (
    login_required,
)
from app.models.entities import (
    Notificacion,
    db,
)
from app.models.queries import (
    marcar_notificaciones_leidas,
    notificaciones_de,
    notificaciones_no_leidas_total,
)

bp = Blueprint("notifications", __name__)


@bp.get("/notificaciones")
@login_required
def notificaciones():
    alertas = notificaciones_de(g.usuario.id, limite=50)
    contrato = {
        "notificaciones": [notificacion_contexto(item) for item in alertas],
        "total_no_leidas": notificaciones_no_leidas_total(g.usuario.id),
    }
    return renderizar_contrato("notificaciones.html", contrato, **contrato)


@bp.get("/api/v1/notificaciones")
@login_required
def api_notificaciones():
    alertas = notificaciones_de(
        g.usuario.id,
        limite=request.args.get("limite", default=30, type=int),
        solo_no_leidas=request.args.get("solo_no_leidas") == "1",
    )
    return jsonify(
        {
            "notificaciones": [notificacion_contexto(item) for item in alertas],
            "total_no_leidas": notificaciones_no_leidas_total(g.usuario.id),
        }
    )


@bp.post("/notificaciones/<int:notificacion_id>/leer")
@login_required
def leer_notificacion(notificacion_id):
    notificacion = db.get_or_404(Notificacion, notificacion_id)
    if notificacion.usuario_id != g.usuario.id:
        abort(404)
    if notificacion.marcar_leida():
        db.session.commit()
    return (
        redirect(
            _destino_seguro(notificacion.destino_url, url_for("notifications.notificaciones"))
        ),
        303,
    )


@bp.post("/notificaciones/leer-todas")
@login_required
def leer_todas_notificaciones():
    if marcar_notificaciones_leidas(g.usuario.id):
        db.session.commit()
    return (redirect(url_for("notifications.notificaciones")), 303)
