from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.controllers.common import (
    DIAS,
    _booleano,
    _booleano_opcional,
    _delete_image_safely,
    _horario_valido,
    _resolver_carrera_upc,
)
from app.controllers.contexts import (
    contexto_catalogo_upc,
)
from app.controllers.presenters import (
    usuario_contexto,
)
from app.core.auth import (
    login_required,
)
from app.models.entities import (
    CampusUPC,
    CarreraUPC,
    Curso,
    EspacioUPC,
    EstiloEstudio,
    FacultadUPC,
    Horario,
    MetaCursoUPC,
    ModalidadUPC,
    ObjetivoSocialite,
    ParticipacionUPC,
    PerfilUPC,
    RolActividadUPC,
    RolCursoUPC,
    TipoActividadUPC,
    ciclos_para_carrera,
    convertir_enum,
    db,
    normalizar_intereses_upc,
)
from app.services.media import MediaStorageError, upload_image

bp = Blueprint("profile", __name__)


@bp.get("/media/avatares/<path:nombre_archivo>")
@login_required
def avatar(nombre_archivo):
    respuesta = send_from_directory(
        current_app.config["AVATAR_UPLOAD_FOLDER"],
        nombre_archivo,
        conditional=True,
        max_age=60 * 60 * 24 * 30,
    )
    respuesta.headers["Cache-Control"] = "private, max-age=2592000, immutable"
    return respuesta


@bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        biografia = request.form.get("biografia", "").strip()
        foto = request.files.get("foto")
        foto_anterior = g.usuario.foto_archivo
        foto_nueva = None
        carrera_texto = request.form.get("carrera", "").strip()
        ciclo = request.form.get("ciclo", "").strip()
        try:
            carrera_upc = _resolver_carrera_upc(request.form.get("carrera_upc_id"), carrera_texto)
            carrera = carrera_upc.nombre if carrera_upc else carrera_texto
            intereses = normalizar_intereses_upc(request.form.getlist("intereses"))
            if not nombre:
                raise ValueError("Tu nombre no puede quedar vacío.")
            if len(nombre) > 80 or len(carrera) > 80:
                raise ValueError("Uno de los campos supera la longitud permitida.")
            if len(biografia) > 220:
                raise ValueError("Tu presentación puede tener hasta 220 caracteres.")
            if ciclo and carrera_upc is None:
                raise ValueError("Selecciona una carrera antes de indicar el ciclo.")
            ciclos_validos = ciclos_para_carrera(carrera_upc.clave if carrera_upc else None)
            if ciclo and (not ciclo.isdigit() or int(ciclo) not in ciclos_validos):
                raise ValueError(f"El ciclo debe estar entre 1 y {len(ciclos_validos)}.")
            g.usuario.nombre = nombre
            g.usuario.biografia = biografia or None
            if foto is not None and foto.filename:
                foto_nueva = upload_image(foto)
                g.usuario.foto_archivo = foto_nueva
            g.usuario.carrera = carrera or None
            g.usuario.ciclo = int(ciclo) if ciclo else None
            g.usuario.intereses = ", ".join(intereses) or None
            if g.usuario.perfil_upc is not None:
                g.usuario.perfil_upc.carrera_upc = carrera_upc
                g.usuario.perfil_upc.facultad = carrera_upc.facultad if carrera_upc else None
            db.session.commit()
            if foto_nueva:
                _delete_image_safely(foto_anterior)
            flash("Perfil actualizado.", "success")
            return redirect(url_for("profile.perfil"))
        except ValueError as error:
            db.session.rollback()
            _delete_image_safely(foto_nueva)
            flash(str(error), "error")
        except MediaStorageError as error:
            db.session.rollback()
            flash(str(error), "error")
        except SQLAlchemyError:
            db.session.rollback()
            _delete_image_safely(foto_nueva)
            current_app.logger.exception("Fallo al confirmar la actualización del perfil")
            flash("No pudimos guardar los cambios. Intenta nuevamente.", "error")
    return render_template(
        "perfil.html",
        dias=DIAS,
        perfil=usuario_contexto(g.usuario, incluir_email=True, incluir_privado=True),
        catalogo_upc=contexto_catalogo_upc(),
    )


@bp.get("/api/v1/catalogo-upc")
def api_catalogo_upc():
    return jsonify(contexto_catalogo_upc())


@bp.get("/api/v1/perfil")
@login_required
def api_perfil():
    return jsonify(
        {
            "perfil": usuario_contexto(g.usuario, incluir_email=True, incluir_privado=True),
            "catalogo_upc": contexto_catalogo_upc(),
        }
    )


@bp.post("/perfil/upc")
@login_required
def actualizar_perfil_upc():
    try:
        campus = convertir_enum(CampusUPC, request.form.get("campus"))
        if campus is None:
            raise ValueError("Selecciona un campus UPC")
        facultad = convertir_enum(FacultadUPC, request.form.get("facultad"))
        carrera_valor = request.form.get("carrera_upc_id", "").strip()
        carrera_id = int(carrera_valor) if carrera_valor else None
        carrera_upc = db.session.get(CarreraUPC, carrera_id) if carrera_id else None
        if carrera_id and (carrera_upc is None or not carrera_upc.activa):
            raise ValueError("La carrera UPC seleccionada no esta disponible")
        if carrera_upc and facultad is None:
            facultad = carrera_upc.facultad
        ciclo_valor = request.form.get("ciclo", "").strip()
        if ciclo_valor:
            if carrera_upc is None:
                raise ValueError("Selecciona una carrera antes de indicar el ciclo")
            ciclos_validos = ciclos_para_carrera(carrera_upc.clave)
            if not ciclo_valor.isdigit() or int(ciclo_valor) not in ciclos_validos:
                raise ValueError(f"El ciclo debe estar entre 1 y {len(ciclos_validos)}")
        intereses = (
            normalizar_intereses_upc(request.form.getlist("intereses"))
            if "intereses" in request.form
            else None
        )
        modalidad = convertir_enum(ModalidadUPC, request.form.get("modalidad"))
        objetivo = convertir_enum(ObjetivoSocialite, request.form.get("objetivo"))
        estilo = convertir_enum(EstiloEstudio, request.form.get("estilo_estudio"))
        espacio_valor = request.form.get("espacio_preferido_id", "").strip()
        espacio_id = int(espacio_valor) if espacio_valor else None
        espacio = db.session.get(EspacioUPC, espacio_id) if espacio_id else None
        if espacio_id and (espacio is None or not espacio.activo):
            raise ValueError("El espacio UPC seleccionado no esta disponible")
        perfil_upc = g.usuario.perfil_upc or PerfilUPC(usuario=g.usuario, campus=campus)
        perfil_upc.campus = campus
        perfil_upc.facultad = facultad
        perfil_upc.carrera_upc = carrera_upc
        perfil_upc.modalidad = modalidad
        perfil_upc.objetivo = objetivo
        perfil_upc.estilo_estudio = estilo
        perfil_upc.viernes_cultural_disponible = _booleano_opcional(
            request.form.get("viernes_cultural_disponible")
        )
        perfil_upc.acepta_intercampus = _booleano(request.form.get("acepta_intercampus"))
        perfil_upc.espacio_preferido = espacio
        perfil_upc.validar_coherencia()
        db.session.add(perfil_upc)
        if carrera_upc is not None:
            g.usuario.carrera = carrera_upc.nombre
        if ciclo_valor:
            g.usuario.ciclo = int(ciclo_valor)
        if intereses is not None:
            g.usuario.intereses = ", ".join(intereses) or None
        db.session.commit()
        flash("Contexto UPC actualizado.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
    return redirect(url_for("profile.perfil"))


@bp.post("/perfil/participaciones")
@login_required
def agregar_participacion_upc():
    try:
        tipo = convertir_enum(TipoActividadUPC, request.form.get("tipo"))
        rol = convertir_enum(RolActividadUPC, request.form.get("rol"))
        campus = convertir_enum(CampusUPC, request.form.get("campus"))
        if tipo is None:
            raise ValueError("Selecciona el tipo de actividad UPC")
        participacion = ParticipacionUPC(
            usuario=g.usuario,
            tipo=tipo,
            nombre=request.form.get("nombre", ""),
            rol=rol or RolActividadUPC.PARTICIPANTE,
            campus=campus,
            periodo=request.form.get("periodo", ""),
            creditos_confirmados=int(request.form.get("creditos_confirmados", 0)),
            activa=_booleano(request.form.get("activa"), True),
        )
        db.session.add(participacion)
        db.session.commit()
        flash("Actividad UPC agregada.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
    except IntegrityError:
        db.session.rollback()
        flash("Esa actividad ya esta registrada para el periodo.", "info")
    return redirect(url_for("profile.perfil"))


@bp.post("/perfil/participaciones/<int:participacion_id>/eliminar")
@login_required
def eliminar_participacion_upc(participacion_id):
    participacion = db.session.get(ParticipacionUPC, participacion_id)
    if participacion is None:
        abort(404)
    if participacion.usuario_id != g.usuario.id:
        abort(403)
    db.session.delete(participacion)
    db.session.commit()
    flash("Actividad UPC eliminada.", "info")
    return redirect(url_for("profile.perfil"))


@bp.post("/perfil/cursos/<int:curso_id>/meta")
@login_required
def actualizar_meta_curso_upc(curso_id):
    curso = db.session.get(Curso, curso_id)
    if curso is None:
        abort(404)
    if curso not in g.usuario.cursos:
        abort(403)
    try:
        rol = convertir_enum(RolCursoUPC, request.form.get("rol"))
        if rol is None:
            raise ValueError("Selecciona una meta para el curso")
        meta = MetaCursoUPC.query.filter_by(
            usuario_id=g.usuario.id, curso_id=curso.id
        ).one_or_none()
        if meta is None:
            meta = MetaCursoUPC(usuario=g.usuario, curso=curso, rol=rol)
        meta.rol = rol
        meta.prioridad = int(request.form.get("prioridad", 3))
        meta.intento = int(request.form.get("intento", 1))
        meta.busca_equipo = _booleano(request.form.get("busca_equipo"), True)
        db.session.add(meta)
        db.session.commit()
        flash("Meta del curso actualizada.", "success")
    except (TypeError, ValueError) as error:
        db.session.rollback()
        flash(str(error), "error")
    return redirect(url_for("profile.perfil"))


@bp.post("/perfil/cursos")
@login_required
def agregar_curso():
    codigo = request.form.get("codigo", "").strip().upper()
    nombre = request.form.get("nombre_curso", "").strip()
    if not codigo or not nombre:
        flash("Completa el codigo y el nombre del curso.", "error")
    elif len(codigo) > 20 or len(nombre) > 120:
        flash("El codigo o el nombre del curso es demasiado largo.", "error")
    else:
        curso = Curso.query.filter_by(codigo=codigo).first()
        if curso is None:
            curso = Curso(codigo=codigo, nombre=nombre)
            db.session.add(curso)
        if curso in g.usuario.cursos:
            flash("Ese curso ya esta en tu perfil.", "info")
        else:
            g.usuario.cursos.append(curso)
            db.session.commit()
            flash("Curso agregado.", "success")
    return redirect(url_for("profile.perfil"))


@bp.post("/perfil/cursos/<int:curso_id>/eliminar")
@login_required
def eliminar_curso(curso_id):
    curso = db.get_or_404(Curso, curso_id)
    if curso in g.usuario.cursos:
        g.usuario.cursos.remove(curso)
        db.session.commit()
        flash("Curso retirado de tu perfil.", "info")
    return redirect(url_for("profile.perfil"))


@bp.post("/perfil/horarios")
@login_required
def agregar_horario():
    dia = request.form.get("dia", "")
    inicio = request.form.get("hora_inicio", "")
    fin = request.form.get("hora_fin", "")
    repetido = Horario.query.filter_by(
        usuario_id=g.usuario.id, dia=dia, hora_inicio=inicio, hora_fin=fin
    ).first()
    if not _horario_valido(dia, inicio, fin):
        flash("Revisa el dia y el rango de horas.", "error")
    elif repetido:
        flash("Ese bloque ya esta registrado.", "info")
    else:
        g.usuario.horarios.append(Horario(dia=dia, hora_inicio=inicio, hora_fin=fin))
        db.session.commit()
        flash("Horario disponible agregado.", "success")
    return redirect(url_for("profile.perfil"))


@bp.post("/perfil/horarios/<int:horario_id>/eliminar")
@login_required
def eliminar_horario(horario_id):
    horario = db.get_or_404(Horario, horario_id)
    if horario.usuario_id != g.usuario.id:
        abort(403)
    db.session.delete(horario)
    db.session.commit()
    flash("Horario eliminado.", "info")
    return redirect(url_for("profile.perfil"))
