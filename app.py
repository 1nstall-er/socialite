from flask import Flask, render_template
from models import db, Grupo


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///socialite.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/grupos")
    def grupos():
        lista = Grupo.query.all()
        return render_template("grupos.html", grupos=lista)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
