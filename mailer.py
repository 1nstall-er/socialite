"""Entrega de correos transaccionales con backends SMTP, consola y memoria."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from html import escape
from typing import Any

from flask import Flask


def _mensaje_verificacion(
    remitente: str, destinatario: str, nombre: str, codigo: str
) -> EmailMessage:
    nombre_html = escape(nombre)
    mensaje = EmailMessage()
    mensaje["Subject"] = f"{codigo} es tu código de Socialite"
    mensaje["From"] = remitente
    mensaje["To"] = destinatario
    mensaje.set_content(
        f"Hola, {nombre}.\n\n"
        f"Tu código para verificar tu correo UPC es: {codigo}\n\n"
        "El código vence en 15 minutos. Si no creaste esta cuenta, ignora este mensaje.\n"
    )
    mensaje.add_alternative(
        f"""<!doctype html><html lang="es"><body style="font-family:Arial,sans-serif;"
        ><h1>Confirma tu correo UPC</h1><p>Hola, {nombre_html}.</p>
        <p>Usa este código para entrar a Socialite:</p>
        <p style="font-size:30px;font-weight:bold;letter-spacing:8px;">{codigo}</p>
        <p>Vence en 15 minutos. Si no creaste esta cuenta, ignora este mensaje.</p>
        </body></html>""",
        subtype="html",
    )
    return mensaje


def enviar_codigo_verificacion(
    app: Flask, destinatario: str, nombre: str, codigo: str
) -> None:
    """Entrega el código según la configuración, sin persistirlo en la base."""
    backend = str(app.config["MAIL_BACKEND"]).lower()
    if backend == "memory":
        outbox: list[dict[str, str]] = app.extensions.setdefault("mail_outbox", [])
        outbox.append(
            {"destinatario": destinatario, "nombre": nombre, "codigo": codigo}
        )
        return
    if backend == "console":
        app.logger.warning(
            "Correo de desarrollo para %s: código Socialite %s",
            destinatario,
            codigo,
        )
        return
    if backend != "smtp":
        raise RuntimeError(f"MAIL_BACKEND no soportado: {backend}")

    remitente = str(app.config["MAIL_DEFAULT_SENDER"])
    mensaje = _mensaje_verificacion(remitente, destinatario, nombre, codigo)
    servidor = str(app.config["MAIL_SERVER"])
    puerto = int(app.config["MAIL_PORT"])
    timeout = int(app.config["MAIL_TIMEOUT"])
    usar_ssl = bool(app.config["MAIL_USE_SSL"])
    usar_tls = bool(app.config["MAIL_USE_TLS"])
    usuario = app.config.get("MAIL_USERNAME")
    password = app.config.get("MAIL_PASSWORD")
    cliente_tipo: Any = smtplib.SMTP_SSL if usar_ssl else smtplib.SMTP

    with cliente_tipo(servidor, puerto, timeout=timeout) as cliente:
        if usar_tls and not usar_ssl:
            cliente.starttls(context=ssl.create_default_context())
        if usuario:
            cliente.login(str(usuario), str(password or ""))
        cliente.send_message(mensaje)
