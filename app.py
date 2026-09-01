from flask import Flask, jsonify
from models import db


def create_app():
  app = Flask(__name__)
  app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///socialite.db"
  app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
  db.init_app(app)

    with app.app_context():
      db.create_all()

    @app.route("/")
    def index():
      return jsonify({"status": "ok", "app": "Socialite"})

return app


if __name__ == "__main__":
  app = create_app()
  app.run(debug=True)
  
