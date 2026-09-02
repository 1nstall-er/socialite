import os
import secrets
from hmac import compare_digest
from functools import wraps

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for

from auth import es_correo_institucional
from matching import ordenar_candidatos, score
from models import Curso, Grupo, Horario, Usuario, db


TIPOS_GRUPO = ("estudio", "social")
DIAS = ("Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado")


def _minutos(hora):
    partes = hora.split(":")
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


def _horas_compartidas(usuario, otro):
    minutos = 0
    for propio in usuario.horarios:
        for ajeno in otro.horarios:
            if propio.dia != ajeno.dia:
                continue
            inicio = max(_minutos(propio.hora_inicio), _minutos(ajeno.hora_inicio))
            fin = min(_minutos(propio.hora_fin), _minutos(ajeno.hora_fin))
            minutos += max(0, fin - inicio)
    return round(minutos / 60, 1)


def _intereses(texto):
    return {
        item.strip().lower()
        for item in (texto or "").split(",")
        if item.strip()
    }


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
    )
    if test_config:
        app.config.update(test_config)

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
            elif not es_correo_institucional(correo):
                flash("Usa tu correo institucional (@upc.edu.pe).", "error")
            elif len(password) < 8:
                flash("La contrasena debe tener al menos 8 caracteres.", "error")
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
                session["usuario_id"] = usuario.id
                flash("Tu cuenta esta lista. Completa tus cursos y horarios.", "success")
                return redirect(url_for("perfil"))

        return render_template("registro.html")

    @app.route("/ingresar", methods=["GET", "POST"])
    def ingresar():
        if g.usuario:
            return redirect(url_for("index"))

        if request.method == "POST":
            correo = request.form.get("correo", "").strip().lower()
            password = request.form.get("password", "")
            usuario = Usuario.query.filter_by(correo_institucional=correo).first()
            if usuario is None or not usuario.check_password(password):
                flash("Correo o contrasena incorrectos.", "error")
            else:
                session.clear()
                session["usuario_id"] = usuario.id
                flash(f"Bienvenido de nuevo, {usuario.nombre}.", "success")
                siguiente = request.args.get("siguiente", "")
                if siguiente.startswith("/") and not siguiente.startswith("//"):
                    return redirect(siguiente)
                return redirect(url_for("index"))

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
            ciclo = request.form.get("ciclo", "").strip()
            if not nombre:
                flash("Tu nombre no puede quedar vacio.", "error")
            elif ciclo and (not ciclo.isdigit() or not 1 <= int(ciclo) <= 12):
                flash("El ciclo debe estar entre 1 y 12.", "error")
            else:
                g.usuario.nombre = nombre
                g.usuario.carrera = request.form.get("carrera", "").strip() or None
                g.usuario.ciclo = int(ciclo) if ciclo else None
                intereses = request.form.get("intereses", "")
                g.usuario.intereses = ", ".join(sorted(_intereses(intereses))) or None
                db.session.commit()
                flash("Perfil actualizado.", "success")
                return redirect(url_for("perfil"))
        return render_template("perfil.html", dias=DIAS)

    @app.post("/perfil/cursos")
    @login_required
    def agregar_curso():
        codigo = request.form.get("codigo", "").strip().upper()
        nombre = request.form.get("nombre_curso", "").strip()
        if not codigo or not nombre:
            flash("Completa el codigo y el nombre del curso.", "error")
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
        if not _horario_valido(dia, inicio, fin):
            flash("Revisa el dia y el rango de horas.", "error")
        else:
            g.usuario.horarios.append(Horario(dia=dia, hora_inicio=inicio, hora_fin=fin))
            db.session.commit()
            flash("Horario disponible agregado.", "success")
        return redirect(url_for("perfil"))

    @app.post("/perfil/horarios/<int:horario_id>/eliminar")
    @login_required
    def eliminar_horario(horario_id):
        horario = db.get_or_404(Horario, horario_id)
        if horario.usuario_id != g.usuario.id:
            flash("No puedes modificar ese horario.", "error")
        else:
            db.session.delete(horario)
            db.session.commit()
            flash("Horario eliminado.", "info")
        return redirect(url_for("perfil"))

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
            elif not lugar:
                flash("Indica un lugar dentro del campus.", "error")
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

        lista = Grupo.query.order_by(Grupo.creado_en.desc()).all()
        return render_template(
            "grupos.html", grupos=lista, tipos=TIPOS_GRUPO, dias=DIAS
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
        return redirect(url_for("grupos"))

    @app.post("/grupos/<int:grupo_id>/salir")
    @login_required
    def salir_grupo(grupo_id):
        grupo = db.get_or_404(Grupo, grupo_id)
        if grupo.creador_id == g.usuario.id:
            flash("El creador no puede abandonar su grupo por ahora.", "error")
        elif g.usuario in grupo.miembros:
            grupo.miembros.remove(g.usuario)
            db.session.commit()
            flash("Saliste del grupo.", "info")
        return redirect(url_for("grupos"))

    @app.route("/companeros")
    @login_required
    def companeros():
        usuarios = Usuario.query.filter(Usuario.id != g.usuario.id).all()
        mis_cursos = {curso.id: curso for curso in g.usuario.cursos}
        mis_intereses = _intereses(g.usuario.intereses)
        sugerencias = []

        for otro in usuarios:
            cursos_comunes = [curso for curso in otro.cursos if curso.id in mis_cursos]
            intereses_comunes = sorted(mis_intereses & _intereses(otro.intereses))
            horas = _horas_compartidas(g.usuario, otro)
            puntaje = score(bool(cursos_comunes), horas, len(intereses_comunes))
            sugerencias.append(
                {
                    "usuario": otro,
                    "score": puntaje,
                    "porcentaje": round(puntaje * 100),
                    "cursos": cursos_comunes,
                    "horas": horas,
                    "intereses": intereses_comunes,
                }
            )

        return render_template(
            "companeros.html", sugerencias=ordenar_candidatos(sugerencias)
        )

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
