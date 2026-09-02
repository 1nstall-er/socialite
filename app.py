import logging
import os
import secrets
import time
from datetime import timedelta
from functools import wraps
from hmac import compare_digest

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from jinja2 import TemplateNotFound

from auth import es_correo_institucional
from matching import (
    calcular_afinidad,
    calcular_afinidad_grupo,
    preparar_perfil,
    rankear_candidatos,
)
from models import Conexion, Curso, Grupo, Horario, Usuario, db
from presenters import (
    conexion_contexto,
    curso_contexto,
    grupo_contexto,
    match_contexto,
    paginacion_contexto,
    usuario_contexto,
)
from queries import (
    candidatos_para,
    conexion_entre,
    conexiones_con_candidatos,
    conexiones_de,
    grupos_de_usuario,
    grupos_filtrados,
    obtener_grupo,
)


TIPOS_GRUPO = ("estudio", "social")
DIAS = ("Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado")
PASSWORD_MINIMO = 10
MAXIMO_POR_PAGINA = 48


def _minutos(hora):
    partes = (hora or "").split(":")
    if len(partes) != 2:
        raise ValueError("Hora invalida")
    horas, minutos = map(int, partes)
    if not 0 <= horas <= 23 or not 0 <= minutos <= 59:
        raise ValueError("Hora invalida")
    return horas * 60 + minutos


def _horario_valido(dia, inicio, fin):
    if dia not in DIAS:
        return False
    try:
        return _minutos(inicio) < _minutos(fin)
    except (TypeError, ValueError):
        return False


def _intereses(texto):
    return {
        item.strip().lower()
        for item in (texto or "").split(",")
        if item.strip()
    }


def _password_valida(password):
    return (
        len(password) >= PASSWORD_MINIMO
        and any(caracter.isalpha() for caracter in password)
        and any(caracter.isdigit() for caracter in password)
    )


def _entero_acotado(valor, predeterminado, minimo, maximo):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return predeterminado
    return min(max(numero, minimo), maximo)


def _destino_seguro(valor, predeterminado):
    if valor and valor.startswith("/") and not valor.startswith("//"):
        return valor
    return predeterminado


def login_required(vista):
    @wraps(vista)
    def protegida(*args, **kwargs):
        if g.usuario is None:
            flash("Inicia sesion para continuar.", "info")
            return redirect(url_for("ingresar", siguiente=request.path))
        return vista(*args, **kwargs)

    return protegida


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "clave-local-socialite"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///socialite.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        CSRF_ENABLED=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if (
        os.getenv("APP_ENV") == "production"
        and app.config["SECRET_KEY"] == "clave-local-socialite"
    ):
        raise RuntimeError("SECRET_KEY es obligatoria en produccion")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()

    @app.before_request
    def cargar_usuario():
        usuario_id = session.get("usuario_id")
        g.usuario = db.session.get(Usuario, usuario_id) if usuario_id else None

    def csrf_token():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_urlsafe(32)
        return session["_csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def proteger_formularios():
        if request.method == "POST" and app.config["CSRF_ENABLED"]:
            esperado = csrf_token()
            recibido = request.form.get("csrf_token", "")
            if not recibido or not compare_digest(esperado, recibido):
                abort(400, description="El formulario expiro. Recarga la pagina e intenta otra vez.")

    @app.after_request
    def cabeceras_seguras(respuesta):
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        respuesta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        respuesta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        respuesta.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        if g.get("usuario"):
            respuesta.headers["Cache-Control"] = "private, no-store"
        return respuesta

    def renderizar_contrato(template, contrato, **contexto_jinja):
        """Renderiza Jinja si existe; durante la fusion expone el contrato JSON."""
        try:
            return render_template(template, **contexto_jinja, contrato=contrato)
        except TemplateNotFound as error:
            if error.name != template:
                raise
            return jsonify({"template_pendiente": template, **contrato})

    def contexto_companeros():
        busqueda = request.args.get("q", "").strip()
        curso_id = request.args.get("curso", type=int)
        afinidad = _entero_acotado(request.args.get("afinidad"), 0, 0, 100)
        pagina = _entero_acotado(request.args.get("pagina"), 1, 1, 100000)
        por_pagina = _entero_acotado(
            request.args.get("por_pagina"), 18, 1, MAXIMO_POR_PAGINA
        )
        candidatos = candidatos_para(g.usuario.id, busqueda, curso_id)
        resultados = rankear_candidatos(g.usuario, candidatos, afinidad)
        paginacion = paginacion_contexto(resultados, pagina, por_pagina)
        conexiones = conexiones_con_candidatos(
            g.usuario.id,
            [resultado["usuario"].id for resultado in paginacion["items"]],
        )
        contrato = {
            "resultados": [match_contexto(item) for item in paginacion["items"]],
            "paginacion": {
                clave: valor
                for clave, valor in paginacion.items()
                if clave != "items"
            },
            "filtros": {
                "q": busqueda,
                "curso": curso_id,
                "afinidad": afinidad,
            },
        }
        return {
            "contrato": contrato,
            "sugerencias": paginacion["items"],
            "conexiones": conexiones,
            "paginacion": contrato["paginacion"],
            "filtros": contrato["filtros"],
        }

    def contexto_grupos():
        tipo = request.args.get("tipo", "").strip()
        curso_id = request.args.get("curso", type=int)
        dia = request.args.get("dia", "").strip()
        busqueda = request.args.get("q", "").strip()
        solo_disponibles = request.args.get("disponibles") == "1"
        pagina = _entero_acotado(request.args.get("pagina"), 1, 1, 100000)
        por_pagina = _entero_acotado(
            request.args.get("por_pagina"), 18, 1, MAXIMO_POR_PAGINA
        )
        tipo_consulta = tipo if tipo in TIPOS_GRUPO else ""
        dia_consulta = dia if dia in DIAS else ""
        grupos = grupos_filtrados(tipo_consulta, curso_id, dia_consulta, busqueda)
        if solo_disponibles:
            grupos = [grupo for grupo in grupos if not grupo.esta_lleno]
        paginacion = paginacion_contexto(grupos, pagina, por_pagina)
        perfil_preparado = preparar_perfil(g.usuario) if g.usuario else None
        afinidades = {
            grupo.id: calcular_afinidad_grupo(
                g.usuario, grupo, perfil_usuario=perfil_preparado
            )
            for grupo in paginacion["items"]
            if g.usuario
        }
        contrato = {
            "resultados": [
                grupo_contexto(grupo, afinidades.get(grupo.id))
                for grupo in paginacion["items"]
            ],
            "paginacion": {
                clave: valor
                for clave, valor in paginacion.items()
                if clave != "items"
            },
            "filtros": {
                "q": busqueda,
                "tipo": tipo_consulta,
                "curso": curso_id,
                "dia": dia_consulta,
                "disponibles": solo_disponibles,
            },
        }
        return {
            "contrato": contrato,
            "grupos": paginacion["items"],
            "afinidades": afinidades,
            "paginacion": contrato["paginacion"],
            "filtros": contrato["filtros"],
        }

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            total_usuarios=Usuario.query.count(),
            total_grupos=Grupo.query.count(),
        )

    @app.route("/registro", methods=["GET", "POST"])
    def registro():
        if g.usuario:
            return redirect(url_for("perfil"))
        if request.method == "POST":
            nombre = request.form.get("nombre", "").strip()
            correo = request.form.get("correo", "").strip().lower()
            password = request.form.get("password", "")
            carrera = request.form.get("carrera", "").strip()
            ciclo = request.form.get("ciclo", "").strip()
            if not nombre or not correo or not password:
                flash("Completa nombre, correo y contrasena.", "error")
            elif len(nombre) > 80 or len(carrera) > 80:
                flash("Revisa la longitud de los datos ingresados.", "error")
            elif not es_correo_institucional(correo):
                flash("Usa tu correo institucional (@upc.edu.pe).", "error")
            elif not _password_valida(password):
                flash("Usa al menos 10 caracteres, con letras y numeros.", "error")
            elif ciclo and (not ciclo.isdigit() or not 1 <= int(ciclo) <= 12):
                flash("El ciclo debe estar entre 1 y 12.", "error")
            elif Usuario.query.filter_by(correo_institucional=correo).first():
                flash("Ese correo ya esta registrado.", "error")
            else:
                usuario = Usuario(
                    nombre=nombre,
                    correo_institucional=correo,
                    carrera=carrera or None,
                    ciclo=int(ciclo) if ciclo else None,
                )
                usuario.set_password(password)
                db.session.add(usuario)
                db.session.commit()
                session.clear()
                session.permanent = True
                session["usuario_id"] = usuario.id
                flash("Tu cuenta esta lista. Completa tus cursos y horarios.", "success")
                return redirect(url_for("perfil"))
        return render_template("registro.html")

    @app.route("/ingresar", methods=["GET", "POST"])
    def ingresar():
        if g.usuario:
            return redirect(url_for("index"))
        bloqueo_hasta = session.get("bloqueo_login_hasta", 0)
        if bloqueo_hasta > time.time():
            flash("Demasiados intentos. Espera un minuto.", "error")
            return render_template("ingresar.html"), 429
        if request.method == "POST":
            correo = request.form.get("correo", "").strip().lower()
            password = request.form.get("password", "")
            usuario = Usuario.query.filter_by(correo_institucional=correo).first()
            if usuario is None or not usuario.check_password(password):
                intentos = session.get("intentos_login", 0) + 1
                session["intentos_login"] = intentos
                if intentos >= 5:
                    session["intentos_login"] = 0
                    session["bloqueo_login_hasta"] = time.time() + 60
                flash("Correo o contrasena incorrectos.", "error")
            else:
                session.clear()
                session.permanent = True
                session["usuario_id"] = usuario.id
                flash(f"Bienvenido de nuevo, {usuario.nombre}.", "success")
                return redirect(
                    _destino_seguro(request.args.get("siguiente"), url_for("index"))
                )
        return render_template("ingresar.html")

    @app.post("/salir")
    def salir():
        session.clear()
        flash("Sesion cerrada.", "info")
        return redirect(url_for("index"))

    @app.route("/perfil", methods=["GET", "POST"])
    @login_required
    def perfil():
        if request.method == "POST":
            nombre = request.form.get("nombre", "").strip()
            carrera = request.form.get("carrera", "").strip()
            ciclo = request.form.get("ciclo", "").strip()
            intereses = request.form.get("intereses", "")
            if not nombre:
                flash("Tu nombre no puede quedar vacio.", "error")
            elif len(nombre) > 80 or len(carrera) > 80 or len(intereses) > 300:
                flash("Uno de los campos supera la longitud permitida.", "error")
            elif ciclo and (not ciclo.isdigit() or not 1 <= int(ciclo) <= 12):
                flash("El ciclo debe estar entre 1 y 12.", "error")
            else:
                g.usuario.nombre = nombre
                g.usuario.carrera = carrera or None
                g.usuario.ciclo = int(ciclo) if ciclo else None
                g.usuario.intereses = ", ".join(sorted(_intereses(intereses))) or None
                db.session.commit()
                flash("Perfil actualizado.", "success")
                return redirect(url_for("perfil"))
        return render_template(
            "perfil.html",
            dias=DIAS,
            perfil=usuario_contexto(g.usuario, incluir_email=True),
        )

    @app.post("/perfil/cursos")
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
        return redirect(url_for("perfil"))

    @app.post("/perfil/cursos/<int:curso_id>/eliminar")
    @login_required
    def eliminar_curso(curso_id):
        curso = db.get_or_404(Curso, curso_id)
        if curso in g.usuario.cursos:
            g.usuario.cursos.remove(curso)
            db.session.commit()
            flash("Curso retirado de tu perfil.", "info")
        return redirect(url_for("perfil"))

    @app.post("/perfil/horarios")
    @login_required
    def agregar_horario():
        dia = request.form.get("dia", "")
        inicio = request.form.get("hora_inicio", "")
        fin = request.form.get("hora_fin", "")
        repetido = Horario.query.filter_by(
            usuario_id=g.usuario.id,
            dia=dia,
            hora_inicio=inicio,
            hora_fin=fin,
        ).first()
        if not _horario_valido(dia, inicio, fin):
            flash("Revisa el dia y el rango de horas.", "error")
        elif repetido:
            flash("Ese bloque ya esta registrado.", "info")
        else:
            g.usuario.horarios.append(
                Horario(dia=dia, hora_inicio=inicio, hora_fin=fin)
            )
            db.session.commit()
            flash("Horario disponible agregado.", "success")
        return redirect(url_for("perfil"))

    @app.post("/perfil/horarios/<int:horario_id>/eliminar")
    @login_required
    def eliminar_horario(horario_id):
        horario = db.get_or_404(Horario, horario_id)
        if horario.usuario_id != g.usuario.id:
            abort(403)
        db.session.delete(horario)
        db.session.commit()
        flash("Horario eliminado.", "info")
        return redirect(url_for("perfil"))

    @app.route("/companeros")
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

    @app.get("/api/v1/companeros")
    @login_required
    def api_companeros():
        return jsonify(contexto_companeros()["contrato"])

    @app.route("/personas/<int:usuario_id>")
    @login_required
    def persona(usuario_id):
        usuario = db.get_or_404(Usuario, usuario_id)
        if usuario.id == g.usuario.id:
            return redirect(url_for("perfil"))
        conexion = conexion_entre(g.usuario.id, usuario.id)
        incluir_email = bool(conexion and conexion.estado == "aceptada")
        contrato = {
            "persona": usuario_contexto(usuario, incluir_email),
            "afinidad": match_contexto(
                {"usuario": usuario, **calcular_afinidad(g.usuario, usuario)}
            ),
            "conexion": conexion_contexto(conexion, g.usuario) if conexion else None,
        }
        return renderizar_contrato(
            "persona.html",
            contrato,
            persona=contrato["persona"],
            afinidad=contrato["afinidad"],
            conexion=contrato["conexion"],
        )

    @app.route("/grupos", methods=["GET", "POST"])
    def grupos():
        if request.method == "POST":
            if g.usuario is None:
                flash("Inicia sesion para crear un grupo.", "info")
                return redirect(url_for("ingresar", siguiente=url_for("grupos")))
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
                return redirect(url_for("grupos"))
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

    @app.get("/api/v1/grupos")
    def api_grupos():
        return jsonify(contexto_grupos()["contrato"])

    @app.get("/grupos/nuevo")
    @login_required
    def nuevo_grupo():
        contrato = {
            "tipos": list(TIPOS_GRUPO),
            "dias": list(DIAS),
            "cursos": [curso_contexto(curso) for curso in g.usuario.cursos],
            "limites": {"min_miembros": 2, "max_miembros": 12},
        }
        return renderizar_contrato("grupo_nuevo.html", contrato, **contrato)

    @app.get("/grupos/<int:grupo_id>")
    def grupo_detalle(grupo_id):
        grupo = obtener_grupo(grupo_id)
        if grupo is None:
            abort(404)
        afinidad = calcular_afinidad_grupo(g.usuario, grupo) if g.usuario else None
        contrato = grupo_contexto(grupo, afinidad)
        contrato["usuario_es_miembro"] = bool(g.usuario and g.usuario in grupo.miembros)
        contrato["usuario_es_creador"] = bool(
            g.usuario and grupo.creador_id == g.usuario.id
        )
        return renderizar_contrato(
            "grupo_detalle.html", contrato, grupo=contrato, afinidad=afinidad
        )

    @app.post("/grupos/<int:grupo_id>/unirse")
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
        return redirect(
            _destino_seguro(request.form.get("siguiente"), url_for("grupos"))
        )

    @app.post("/grupos/<int:grupo_id>/salir")
    @login_required
    def salir_grupo(grupo_id):
        grupo = db.get_or_404(Grupo, grupo_id)
        if grupo.creador_id == g.usuario.id:
            flash("El creador debe cancelar el grupo si ya no continuara.", "error")
        elif g.usuario in grupo.miembros:
            grupo.miembros.remove(g.usuario)
            db.session.commit()
            flash("Saliste del grupo.", "info")
        return redirect(url_for("grupos"))

    @app.post("/grupos/<int:grupo_id>/eliminar")
    @login_required
    def eliminar_grupo(grupo_id):
        grupo = db.get_or_404(Grupo, grupo_id)
        if grupo.creador_id != g.usuario.id:
            abort(403)
        db.session.delete(grupo)
        db.session.commit()
        flash("Grupo cancelado.", "info")
        return redirect(url_for("grupos"))

    @app.route("/panel")
    @login_required
    def panel():
        matches = contexto_companeros()["contrato"]["resultados"][:3]
        grupos_usuario = grupos_de_usuario(g.usuario.id)
        grupos_recomendados = [
            grupo
            for grupo in grupos_filtrados()
            if g.usuario not in grupo.miembros and not grupo.esta_lleno
        ]
        perfil_preparado = preparar_perfil(g.usuario)
        afinidades_grupo = {
            grupo.id: calcular_afinidad_grupo(
                g.usuario, grupo, perfil_usuario=perfil_preparado
            )
            for grupo in grupos_recomendados
        }
        grupos_recomendados.sort(
            key=lambda grupo: afinidades_grupo[grupo.id]["score"], reverse=True
        )
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
                grupo_contexto(grupo, afinidades_grupo[grupo.id])
                for grupo in grupos_recomendados[:3]
            ],
            "solicitudes": [
                conexion_contexto(conexion, g.usuario) for conexion in pendientes[:3]
            ],
        }
        return renderizar_contrato("panel.html", contrato, **contrato)

    @app.route("/conexiones")
    @login_required
    def conexiones():
        todas = conexiones_de(g.usuario.id)
        contrato = {
            "recibidas": [
                conexion_contexto(item, g.usuario)
                for item in todas
                if item.estado == "pendiente"
                and item.destinatario_id == g.usuario.id
            ],
            "enviadas": [
                conexion_contexto(item, g.usuario)
                for item in todas
                if item.estado == "pendiente" and item.remitente_id == g.usuario.id
            ],
            "aceptadas": [
                conexion_contexto(item, g.usuario)
                for item in todas
                if item.estado == "aceptada"
            ],
        }
        return renderizar_contrato("conexiones.html", contrato, **contrato)

    @app.post("/companeros/<int:usuario_id>/conectar")
    @login_required
    def solicitar_conexion(usuario_id):
        usuario = db.get_or_404(Usuario, usuario_id)
        if usuario.id == g.usuario.id:
            abort(400, description="No puedes conectarte contigo mismo.")
        conexion = conexion_entre(g.usuario.id, usuario.id)
        if conexion is None:
            conexion = Conexion(
                remitente=g.usuario, destinatario=usuario, estado="pendiente"
            )
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
            _destino_seguro(request.form.get("siguiente"), url_for("companeros"))
        )

    @app.post("/conexiones/<int:conexion_id>/aceptar")
    @login_required
    def aceptar_conexion(conexion_id):
        conexion = db.get_or_404(Conexion, conexion_id)
        if conexion.destinatario_id != g.usuario.id or conexion.estado != "pendiente":
            abort(403)
        conexion.estado = "aceptada"
        db.session.commit()
        flash("Conexion aceptada.", "success")
        return redirect(url_for("conexiones"))

    @app.post("/conexiones/<int:conexion_id>/rechazar")
    @login_required
    def rechazar_conexion(conexion_id):
        conexion = db.get_or_404(Conexion, conexion_id)
        if conexion.destinatario_id != g.usuario.id or conexion.estado != "pendiente":
            abort(403)
        conexion.estado = "rechazada"
        db.session.commit()
        flash("Solicitud descartada.", "info")
        return redirect(url_for("conexiones"))

    @app.post("/conexiones/<int:conexion_id>/cancelar")
    @login_required
    def cancelar_conexion(conexion_id):
        conexion = db.get_or_404(Conexion, conexion_id)
        if conexion.remitente_id != g.usuario.id or conexion.estado != "pendiente":
            abort(403)
        db.session.delete(conexion)
        db.session.commit()
        flash("Solicitud cancelada.", "info")
        return redirect(url_for("conexiones"))

    return app


if __name__ == "__main__":
    create_app().run(debug=os.getenv("FLASK_DEBUG", "0") == "1")
