from __future__ import annotations

from flask import (
    Blueprint,
    g,
    redirect,
    render_template,
    url_for,
)

from app.controllers.common import (
    renderizar_contrato,
)
from app.controllers.contexts import (
    contexto_top_companeros,
)
from app.controllers.presenters import (
    conexion_contexto,
    grupo_contexto,
    usuario_contexto,
)
from app.core.auth import (
    login_required,
)
from app.models.entities import (
    Grupo,
    Usuario,
)
from app.models.queries import (
    conexiones_de,
    grupos_de_usuario,
    grupos_filtrados,
)
from app.services.matching import (
    calcular_afinidad_grupo,
    preparar_perfil,
)

bp = Blueprint("pages", __name__)


@bp.route("/")
def index():
    if g.usuario:
        return redirect(url_for('pages.panel'))
    return render_template(
        "index.html", total_usuarios=Usuario.query.count(), total_grupos=Grupo.query.count()
    )


@bp.route("/panel")
@login_required
def panel():
    matches = contexto_top_companeros()["resultados"][:3]
    grupos_usuario = grupos_de_usuario(g.usuario.id)
    grupos_recomendados = [
        grupo
        for grupo in grupos_filtrados()
        if g.usuario not in grupo.miembros and (not grupo.esta_lleno)
    ]
    perfil_preparado = preparar_perfil(g.usuario)
    afinidades_grupo = {
        grupo.id: calcular_afinidad_grupo(g.usuario, grupo, perfil_usuario=perfil_preparado)
        for grupo in grupos_recomendados
    }
    grupos_recomendados.sort(key=lambda grupo: afinidades_grupo[grupo.id]["score"], reverse=True)
    pendientes = [
        conexion
        for conexion in conexiones_de(g.usuario.id, "pendiente")
        if conexion.destinatario_id == g.usuario.id
    ]
    contrato = {
        "usuario": usuario_contexto(g.usuario, incluir_email=True),
        "metricas": {
            "perfil_completo": g.usuario.perfil_completo,
            "grupos_activos": len(grupos_usuario),
            "solicitudes_pendientes": len(pendientes),
        },
        "sugerencias": matches,
        "mis_grupos": [grupo_contexto(grupo) for grupo in grupos_usuario[:3]],
        "grupos_recomendados": [
            grupo_contexto(grupo, afinidades_grupo[grupo.id]) for grupo in grupos_recomendados[:3]
        ],
        "solicitudes": [conexion_contexto(conexion, g.usuario) for conexion in pendientes[:3]],
    }
    return renderizar_contrato("panel.html", contrato, **contrato)
