from __future__ import annotations

import secrets
from hmac import compare_digest
from urllib.parse import urlsplit

from flask import (
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    request,
    session,
)

from app.models.entities import (
    Usuario,
    db,
)
from app.models.queries import (
    notificaciones_no_leidas_total,
)


def cargar_usuario():
    usuario_id = session.get("usuario_id")
    g.usuario = db.session.get(Usuario, usuario_id) if usuario_id else None
    if (
        g.usuario is not None
        and current_app.config["EMAIL_VERIFICATION_REQUIRED"]
        and (not g.usuario.correo_verificado)
    ):
        session.pop("usuario_id", None)
        session["verificacion_usuario_id"] = g.usuario.id
        g.usuario = None


def csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


def contexto_notificaciones_global():
    total = notificaciones_no_leidas_total(g.usuario.id) if g.get("usuario") else 0
    return {"notificaciones_no_leidas": total}


def proteger_formularios():
    if request.method == "POST" and current_app.config["CSRF_ENABLED"]:
        esperado = csrf_token()
        recibido = request.form.get("csrf_token", "")
        if not recibido or not compare_digest(esperado, recibido):
            abort(400, description="El formulario expiro. Recarga la pagina e intenta otra vez.")


def cabeceras_seguras(respuesta):
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    respuesta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    media_source = ""
    public_base_url = str(current_app.config.get("S3_PUBLIC_BASE_URL") or "")
    parsed_media = urlsplit(public_base_url)
    if parsed_media.scheme == "https" and parsed_media.netloc:
        media_source = f" {parsed_media.scheme}://{parsed_media.netloc}"
    respuesta.headers["Content-Security-Policy"] = (
        f"default-src 'self'; img-src 'self' data:{media_source}; style-src 'self'; script-src 'self' https://cdn.socket.io; connect-src 'self' ws: wss:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    if g.get("usuario") and request.endpoint != "profile.avatar":
        respuesta.headers["Cache-Control"] = "private, no-store"
    return respuesta


def archivo_demasiado_grande(_error):
    flash("La foto supera el límite permitido de 5 MB.", "error")
    destino = request.path if request.path in {"/registro", "/perfil"} else "/registro"
    return (redirect(destino), 303)


def register_hooks(app: Flask) -> None:
    app.before_request(cargar_usuario)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.context_processor(contexto_notificaciones_global)
    app.before_request(proteger_formularios)
    app.after_request(cabeceras_seguras)
    app.register_error_handler(413, archivo_demasiado_grande)
