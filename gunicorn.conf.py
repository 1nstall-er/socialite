"""Configuración de un worker WebSocket por contenedor."""

import os


def _positive_int(name: str, default: int, *, maximum: int | None = None) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} debe ser un número entero") from error
    if value <= 0 or (maximum is not None and value > maximum):
        raise RuntimeError(f"{name} está fuera del rango permitido")
    return value


bind = f"0.0.0.0:{_positive_int('PORT', 8000, maximum=65_535)}"
workers = 1
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
timeout = _positive_int("GUNICORN_TIMEOUT", 60)
graceful_timeout = min(timeout, 30)
keepalive = 5
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
accesslog = "-"
errorlog = "-"
capture_output = True
