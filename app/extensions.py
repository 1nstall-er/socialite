"""Instancias compartidas, sin vincularlas a una aplicación al importar."""

from flask_cors import CORS
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate(compare_type=True, render_as_batch=True)
socketio = SocketIO()
cors = CORS()
