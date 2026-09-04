"""Entrada del servidor: Python en desarrollo, Gunicorn en producción."""

from __future__ import annotations

import os

if os.getenv("SOCKETIO_ASYNC_MODE", "threading") == "gevent":
    from gevent import monkey

    monkey.patch_all()

from app import create_app  # noqa: E402
from app.extensions import socketio  # noqa: E402

app = create_app()

if __name__ == "__main__":
    if app.config["APP_ENV"] == "production":
        raise SystemExit("En producción utiliza Gunicorn con run:app.")
    socketio.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        allow_unsafe_werkzeug=True,
    )
