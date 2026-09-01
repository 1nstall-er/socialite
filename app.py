from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, Grupo, Usuario
from auth import es_correo_institucional

TIPOS_GRUPO = ("estudio", "social")


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
