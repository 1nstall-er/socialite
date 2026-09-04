from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from app.controllers.common import (
    DIAS,
    TIPOS_GRUPO,
    _destino_seguro,
    _horario_valido,
    renderizar_contrato,
)
from app.controllers.contexts import (
    contexto_grupos,
)
from app.controllers.presenters import (
    curso_contexto,
    grupo_contexto,
)
from app.core.auth import (
    login_required,
)
from app.models.entities import (
    Curso,
    Grupo,
    db,
)
from app.models.queries import (
    obtener_grupo,
)
from app.services.matching import (
    calcular_afinidad_grupo,
)

bp = Blueprint("groups", __name__)


@bp.route("/grupos", methods=["GET", "POST"])
def grupos():
    if request.method == "POST":
        if g.usuario is None:
            flash("Inicia sesion para crear un grupo.", "info")
            return redirect(url_for("auth.ingresar", siguiente=url_for("groups.grupos")))
        tipo = request.form.get("tipo", "").strip()
        lugar = request.form.get("lugar", "").strip()
        dia = request.form.get("dia", "")
        inicio = request.form.get("hora_inicio", "")
        fin = request.form.get("hora_fin", "")
        curso_id = request.form.get("curso_id", type=int)
        max_miembros = request.form.get("max_miembros", type=int)
        curso = db.session.get(Curso, curso_id) if curso_id else None
        if tipo not in TIPOS_GRUPO:
            flash("Elige un tipo de grupo valido.", "error")
        elif tipo == "estudio" and (curso is None or curso not in g.usuario.cursos):
            flash("Elige uno de tus cursos para el grupo de estudio.", "error")
        elif not lugar or len(lugar) > 120:
            flash("Indica un lugar valido dentro del campus.", "error")
        elif not _horario_valido(dia, inicio, fin):
            flash("Revisa el dia y el rango de horas.", "error")
        elif max_miembros is None or not 2 <= max_miembros <= 12:
            flash("El grupo debe admitir entre 2 y 12 personas.", "error")
        else:
            grupo = Grupo(
                tipo=tipo,
                curso=curso if tipo == "estudio" else None,
                creador=g.usuario,
                lugar=lugar,
                dia=dia,
                hora_inicio=inicio,
                hora_fin=fin,
                max_miembros=max_miembros,
            )
            grupo.miembros.append(g.usuario)
            db.session.add(grupo)
            db.session.commit()
            flash("Grupo creado. Ya formas parte de el.", "success")
            return redirect(url_for("groups.grupos"))
    contexto = contexto_grupos()
    return render_template(
        "grupos.html",
        grupos=contexto["grupos"],
        afinidades=contexto["afinidades"],
        paginacion=contexto["paginacion"],
        filtros=contexto["filtros"],
        tipos=TIPOS_GRUPO,
        dias=DIAS,
        cursos=Curso.query.order_by(Curso.codigo).all(),
        contrato=contexto["contrato"],
    )


@bp.get("/api/v1/grupos")
def api_grupos():
    return jsonify(contexto_grupos()["contrato"])


@bp.get("/grupos/nuevo")
@login_required
def nuevo_grupo():
    contrato = {
        "tipos": list(TIPOS_GRUPO),
        "dias": list(DIAS),
        "cursos": [curso_contexto(curso) for curso in g.usuario.cursos],
        "limites": {"min_miembros": 2, "max_miembros": 12},
    }
    return renderizar_contrato("grupo_nuevo.html", contrato, **contrato)


@bp.get("/grupos/<int:grupo_id>")
def grupo_detalle(grupo_id):
    grupo = obtener_grupo(grupo_id)
    if grupo is None:
        abort(404)
    afinidad = calcular_afinidad_grupo(g.usuario, grupo) if g.usuario else None
    contrato = grupo_contexto(grupo, afinidad)
    contrato["usuario_es_miembro"] = bool(g.usuario and g.usuario in grupo.miembros)
    contrato["usuario_es_creador"] = bool(g.usuario and grupo.creador_id == g.usuario.id)
    return renderizar_contrato("grupo_detalle.html", contrato, grupo=contrato, afinidad=afinidad)


@bp.post("/grupos/<int:grupo_id>/unirse")
@login_required
def unirse_grupo(grupo_id):
    grupo = db.get_or_404(Grupo, grupo_id)
    if g.usuario in grupo.miembros:
        flash("Ya formas parte de este grupo.", "info")
    elif grupo.esta_lleno:
        flash("El grupo ya alcanzo su capacidad maxima.", "error")
    else:
        grupo.miembros.append(g.usuario)
        db.session.commit()
        flash("Te uniste al grupo.", "success")
    return redirect(_destino_seguro(request.form.get("siguiente"), url_for("groups.grupos")))


@bp.post("/grupos/<int:grupo_id>/salir")
@login_required
def salir_grupo(grupo_id):
    grupo = db.get_or_404(Grupo, grupo_id)
    if grupo.creador_id == g.usuario.id:
        flash("El creador debe cancelar el grupo si ya no continuara.", "error")
    elif g.usuario in grupo.miembros:
        grupo.miembros.remove(g.usuario)
        db.session.commit()
        flash("Saliste del grupo.", "info")
    return redirect(url_for("groups.grupos"))


@bp.post("/grupos/<int:grupo_id>/eliminar")
@login_required
def eliminar_grupo(grupo_id):
    grupo = db.get_or_404(Grupo, grupo_id)
    if grupo.creador_id != g.usuario.id:
        abort(403)
    db.session.delete(grupo)
    db.session.commit()
    flash("Grupo cancelado.", "info")
    return redirect(url_for("groups.grupos"))
