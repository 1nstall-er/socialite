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
from sqlalchemy.exc import IntegrityError

from app.controllers.common import (
    renderizar_contrato,
)
from app.controllers.presenters import (
    usuario_contexto,
)
from app.core.auth import (
    login_required,
)
from app.models.entities import (
    Bloqueo,
    Conexion,
    EstadoReporte,
    MotivoReporte,
    Reporte,
    Usuario,
    convertir_enum,
    db,
)
from app.models.queries import (
    bloqueos_emitidos_de,
)

bp = Blueprint("safety", __name__)


@bp.get("/seguridad")
@login_required
def seguridad():
    bloqueos = bloqueos_emitidos_de(g.usuario.id)
    contrato = {
        "bloqueados": [
            {
                "id": bloqueo.id,
                "creado_en": bloqueo.creado_en.isoformat(),
                "persona": usuario_contexto(bloqueo.bloqueado),
            }
            for bloqueo in bloqueos
        ]
    }
    return renderizar_contrato("seguridad.html", contrato, bloqueos=bloqueos)


@bp.get("/personas/<int:usuario_id>/seguridad")
@login_required
def seguridad_persona(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    if usuario.id == g.usuario.id:
        abort(400, description="No puedes reportarte o bloquearte.")
    bloqueo = Bloqueo.query.filter_by(
        bloqueador_id=g.usuario.id, bloqueado_id=usuario.id
    ).one_or_none()
    contrato = {
        "persona": usuario_contexto(usuario),
        "bloqueado": bloqueo is not None,
        "motivos": [
            {"valor": motivo.value, "etiqueta": motivo.etiqueta} for motivo in MotivoReporte
        ],
    }
    return renderizar_contrato(
        "seguridad_persona.html",
        contrato,
        persona=contrato["persona"],
        bloqueo=bloqueo,
        motivos=contrato["motivos"],
    )


@bp.post("/personas/<int:usuario_id>/bloquear")
@login_required
def bloquear_persona(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    if usuario.id == g.usuario.id:
        abort(400, description="No puedes bloquearte.")
    existente = Bloqueo.query.filter_by(
        bloqueador_id=g.usuario.id, bloqueado_id=usuario.id
    ).one_or_none()
    if existente is None:
        try:
            db.session.add(Bloqueo(bloqueador=g.usuario, bloqueado=usuario))
            conexiones_existentes = Conexion.query.filter(
                (Conexion.remitente_id == g.usuario.id) & (Conexion.destinatario_id == usuario.id)
                | (Conexion.remitente_id == usuario.id) & (Conexion.destinatario_id == g.usuario.id)
            ).all()
            for conexion in conexiones_existentes:
                db.session.delete(conexion)
            db.session.commit()
            flash(
                f"Bloqueaste a {usuario.nombre}. Ya no podrán conectar ni aparecerse en el matching.",
                "success",
            )
        except IntegrityError:
            db.session.rollback()
            flash("Esta persona ya está bloqueada.", "info")
    else:
        flash("Esta persona ya está bloqueada.", "info")
    return redirect(url_for("safety.seguridad"))


@bp.post("/bloqueos/<int:bloqueo_id>/eliminar")
@login_required
def desbloquear_persona(bloqueo_id):
    bloqueo = db.get_or_404(Bloqueo, bloqueo_id)
    if bloqueo.bloqueador_id != g.usuario.id:
        abort(403)
    nombre = bloqueo.bloqueado.nombre
    db.session.delete(bloqueo)
    db.session.commit()
    flash(f"Desbloqueaste a {nombre}.", "info")
    return redirect(url_for("safety.seguridad"))


@bp.post("/personas/<int:usuario_id>/reportar")
@login_required
def reportar_persona(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    if usuario.id == g.usuario.id:
        abort(400, description="No puedes reportarte.")
    try:
        motivo = convertir_enum(MotivoReporte, request.form.get("motivo"))
        if motivo is None:
            raise ValueError("Selecciona un motivo para el reporte.")
        detalle = request.form.get("detalle", "").strip()
        abierto = Reporte.query.filter(
            Reporte.denunciante_id == g.usuario.id,
            Reporte.reportado_id == usuario.id,
            Reporte.estado.in_([EstadoReporte.PENDIENTE, EstadoReporte.EN_REVISION]),
        ).first()
        if abierto:
            flash("Ya tienes un reporte de esta persona en revisión.", "info")
        else:
            db.session.add(
                Reporte(
                    denunciante=g.usuario, reportado=usuario, motivo=motivo, detalle=detalle or None
                )
            )
            db.session.commit()
            flash(
                "Recibimos tu reporte de forma privada. Gracias por cuidar la comunidad.", "success"
            )
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
    return redirect(url_for("safety.seguridad_persona", usuario_id=usuario.id))
