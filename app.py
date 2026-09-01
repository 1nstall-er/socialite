from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, Grupo, Usuario
from auth import es_correo_institucional
from matching import score, ordenar_candidatos

TIPOS_GRUPO = ("estudio", "social")


def bloques_horario(usuario):
    """Conjunto de bloques (dia, inicio, fin) del horario de un usuario."""
    return {(h.dia, h.hora_inicio, h.hora_fin) for h in usuario.horarios}


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "cambiar-esta-clave-en-produccion"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///socialite.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/grupos", methods=["GET", "POST"])
    def grupos():
        if request.method == "POST":
            tipo = request.form.get("tipo", "").strip()
            lugar = request.form.get("lugar", "").strip()

            if tipo not in TIPOS_GRUPO:
                flash("Elige un tipo de grupo valido.")
                return redirect(url_for("grupos"))

            grupo = Grupo(tipo=tipo, lugar=lugar or None)
            db.session.add(grupo)
            db.session.commit()
            flash("Grupo creado.")
            return redirect(url_for("grupos"))

        lista = Grupo.query.all()
        return render_template("grupos.html", grupos=lista, tipos=TIPOS_GRUPO)

    @app.route("/companeros")
    def companeros():
        usuarios = Usuario.query.all()
        usuario_id = request.args.get("usuario", type=int)

        if not usuario_id:
            return render_template(
                "companeros.html", usuarios=usuarios, seleccionado=None, sugerencias=None
            )

        usuario = Usuario.query.get_or_404(usuario_id)
        mis_cursos = {c.id for c in usuario.cursos}
        mis_bloques = bloques_horario(usuario)

        sugerencias = []
        for otro in usuarios:
            if otro.id == usuario.id:
                continue
            sus_cursos = {c.id for c in otro.cursos}
            mismo_curso = len(mis_cursos & sus_cursos) > 0
            horas = len(mis_bloques & bloques_horario(otro))
            puntaje = score(mismo_curso, horas, 0)
            sugerencias.append({"usuario": otro, "score": puntaje})

        sugerencias = ordenar_candidatos(sugerencias)
        return render_template(
            "companeros.html", usuarios=usuarios, seleccionado=usuario, sugerencias=sugerencias
        )

    @app.route("/registro", methods=["GET", "POST"])
    def registro():
        if request.method == "POST":
            nombre = request.form.get("nombre", "").strip()
            correo = request.form.get("correo", "").strip()
            carrera = request.form.get("carrera", "").strip()
            ciclo = request.form.get("ciclo", "").strip()

            if not nombre or not correo:
                flash("Completa tu nombre y tu correo.")
                return render_template("registro.html")

            if not es_correo_institucional(correo):
                flash("Usa tu correo institucional (@upc.edu.pe).")
                return render_template("registro.html")

            if Usuario.query.filter_by(correo_institucional=correo).first():
                flash("Ese correo ya esta registrado.")
                return render_template("registro.html")

            usuario = Usuario(
                nombre=nombre,
                correo_institucional=correo,
                carrera=carrera or None,
                ciclo=int(ciclo) if ciclo.isdigit() else None,
            )
            db.session.add(usuario)
            db.session.commit()
            flash("Registro exitoso. Bienvenido a Socialite.")
            return redirect(url_for("index"))

        return render_template("registro.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
