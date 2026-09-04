from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    url_for,
)

from app.controllers.common import (
    renderizar_contrato,
)
from app.controllers.contexts import (
    contexto_companeros,
    contexto_top_companeros,
)
from app.controllers.presenters import (
    conexion_contexto,
    match_contexto,
    usuario_contexto,
)
from app.core.auth import (
    login_required,
)
from app.models.entities import (
    Curso,
    Usuario,
    db,
)
from app.models.queries import (
    conexion_entre,
    hay_bloqueo_entre,
)
from app.services.matching import (
    calcular_afinidad,
)

bp = Blueprint("companions", __name__)


@bp.route("/companeros")
@login_required
def companeros():
    contexto = contexto_companeros()
    return render_template(
        "companeros.html",
        sugerencias=contexto["sugerencias"],
        conexiones=contexto["conexiones"],
        paginacion=contexto["paginacion"],
        filtros=contexto["filtros"],
        cursos=Curso.query.order_by(Curso.codigo).all(),
        contrato=contexto["contrato"],
    )


@bp.get("/api/v1/companeros")
@login_required
def api_companeros():
    return jsonify(contexto_companeros()["contrato"])


@bp.get("/api/v1/companeros/top")
@login_required
def api_top_companeros():
    return jsonify(contexto_top_companeros())


@bp.route("/personas/<int:usuario_id>")
@login_required
def persona(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    if usuario.id == g.usuario.id:
        return redirect(url_for("profile.perfil"))
    if hay_bloqueo_entre(g.usuario.id, usuario.id):
        abort(404)
    conexion = conexion_entre(g.usuario.id, usuario.id)
    incluir_email = bool(conexion and conexion.estado == "aceptada")
    contrato = {
        "persona": usuario_contexto(usuario, incluir_email),
        "afinidad": match_contexto({"usuario": usuario, **calcular_afinidad(g.usuario, usuario)}),
        "conexion": conexion_contexto(conexion, g.usuario) if conexion else None,
    }
    return renderizar_contrato(
        "persona.html",
        contrato,
        persona=contrato["persona"],
        afinidad=contrato["afinidad"],
        conexion=contrato["conexion"],
    )
