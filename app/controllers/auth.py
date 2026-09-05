from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.controllers.common import (
    _delete_image_safely,
    _destino_seguro,
    _password_valida,
    _resolver_carrera_upc,
)
from app.models.privacy import Consentimiento
from app.controllers.contexts import (
    contexto_catalogo_upc,
)
from app.core.auth import (
    consultar_login,
    es_correo_institucional,
    limpiar_fallos_login,
    registrar_login_fallido,
)
from app.core.verification import (
    MAX_INTENTOS,
    ResultadoVerificacion,
    completar_verificacion,
    limitar_reenvio,
    preparar_reto,
    segundos_para_reenviar,
    validar_codigo,
)
from app.models.entities import (
    Usuario,
    ciclos_para_carrera,
    db,
    normalizar_intereses_upc,
)
from app.services.mailer import enviar_codigo_verificacion
from app.services.media import MediaStorageError, upload_image

bp = Blueprint("auth", __name__)


def emitir_codigo_verificacion(usuario, respetar_espera=True):
    espera = segundos_para_reenviar(usuario)
    if respetar_espera and espera:
        return (False, espera)
    codigo = preparar_reto(usuario, current_app.config["SECRET_KEY"])
    try:
        enviar_codigo_verificacion(
            current_app, usuario.correo_institucional, usuario.nombre, codigo
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "No se pudo enviar la verificación a %s", usuario.correo_institucional
        )
        return (False, 0)
    return (True, 0)


@bp.route("/registro", methods=["GET", "POST"])
def registro():
    if g.usuario:
        return redirect(url_for("profile.perfil"))
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")
        biografia = request.form.get("biografia", "").strip()
        foto = request.files.get("foto")
        carrera_texto = request.form.get("carrera", "").strip()
        error_carrera = None
        try:
            carrera_upc = _resolver_carrera_upc(request.form.get("carrera_upc_id"), carrera_texto)
        except ValueError as error:
            carrera_upc = None
            error_carrera = str(error)
        try:
            intereses = normalizar_intereses_upc(request.form.getlist("intereses"))
            error_intereses = None
        except ValueError as error:
            intereses = []
            error_intereses = str(error)
        carrera = carrera_upc.nombre if carrera_upc else carrera_texto
        ciclo = request.form.get("ciclo", "").strip()
        if not nombre or not correo or (not password):
            flash("Completa nombre, correo y contrasena.", "error")
        elif foto is None or not foto.filename:
            flash("Selecciona una foto de perfil.", "error")
        elif len(biografia) > 220:
            flash("Tu presentación puede tener hasta 220 caracteres.", "error")
        elif len(nombre) > 80 or len(carrera) > 80:
            flash("Revisa la longitud de los datos ingresados.", "error")
        elif error_carrera:
            flash(error_carrera, "error")
        elif error_intereses:
            flash(error_intereses, "error")
        elif ciclo and carrera_upc is None:
            flash("Selecciona una carrera antes de indicar el ciclo.", "error")
        elif not es_correo_institucional(correo):
            flash("Usa tu correo institucional (@upc.edu.pe).", "error")
        elif not _password_valida(password):
            flash("Usa al menos 10 caracteres, con letras y numeros.", "error")
        elif ciclo and (
            not ciclo.isdigit()
            or int(ciclo) not in ciclos_para_carrera(carrera_upc.clave if carrera_upc else None)
        ):
            limite = len(ciclos_para_carrera(carrera_upc.clave if carrera_upc else None))
            flash(f"El ciclo debe estar entre 1 y {limite}.", "error")
        elif Usuario.query.filter_by(correo_institucional=correo).first():
            flash("Ese correo ya esta registrado.", "error")
        else:
            foto_archivo: str | None = None
            try:
                foto_archivo = upload_image(foto)
                usuario = Usuario(
                    nombre=nombre,
                    correo_institucional=correo,
                    foto_archivo=foto_archivo,
                    biografia=biografia or None,
                    carrera=carrera or None,
                    ciclo=int(ciclo) if ciclo else None,
                    intereses=", ".join(intereses) or None,
                )
                usuario.set_password(password)
                if not current_app.config["EMAIL_VERIFICATION_REQUIRED"]:
                    completar_verificacion(usuario)
                db.session.add(usuario)
                db.session.flush()
                Consentimiento.registrar(usuario.id)
                db.session.commit()
            except ValueError as error:
                db.session.rollback()
                _delete_image_safely(foto_archivo)
                flash(str(error), "error")
            except MediaStorageError as error:
                db.session.rollback()
                flash(str(error), "error")
            except IntegrityError:
                db.session.rollback()
                _delete_image_safely(foto_archivo)
                flash("Ese correo ya está registrado.", "error")
            except SQLAlchemyError:
                db.session.rollback()
                _delete_image_safely(foto_archivo)
                current_app.logger.exception("Fallo al confirmar el registro")
                flash("No pudimos crear tu cuenta. Intenta nuevamente.", "error")
            else:
                session.clear()
                session.permanent = True
                if current_app.config["EMAIL_VERIFICATION_REQUIRED"]:
                    session["verificacion_usuario_id"] = usuario.id
                    enviado, _espera = emitir_codigo_verificacion(usuario, respetar_espera=False)
                    if enviado:
                        flash("Te enviamos un código de 6 dígitos a tu correo UPC.", "success")
                    else:
                        flash(
                            "Tu cuenta fue creada, pero el correo no pudo enviarse. Intenta reenviarlo.",
                            "error",
                        )
                    return redirect(url_for("auth.verificar_correo"))
                session["usuario_id"] = usuario.id
                flash("Tu cuenta esta lista. Completa tus cursos y horarios.", "success")
                return redirect(url_for("profile.perfil"))
    return render_template("registro.html", catalogo_upc=contexto_catalogo_upc())


@bp.route("/ingresar", methods=["GET", "POST"])
def ingresar():
    if g.usuario:
        return redirect(url_for("pages.index"))
    if request.method == "POST":
        decision = consultar_login(
            current_app.extensions["login_rate_limiter"], request.remote_addr
        )
        if not decision.permitido:
            flash(
                f"Demasiados intentos fallidos desde esta red. Intenta nuevamente en {decision.reintentar_en} segundos.",
                "error",
            )
            return (
                render_template("ingresar.html"),
                429,
                {"Retry-After": str(decision.reintentar_en)},
            )
        correo = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")
        usuario = Usuario.query.filter_by(correo_institucional=correo).first()
        if usuario is None or not usuario.check_password(password):
            resultado_limite = registrar_login_fallido(
                current_app.extensions["login_rate_limiter"], request.remote_addr
            )
            flash("Correo o contrasena incorrectos.", "error")
            if resultado_limite.restantes == 0:
                flash(
                    f"Alcanzaste el máximo de {current_app.config['LOGIN_MAX_FALLOS']} intentos. La IP quedó limitada por {current_app.config['LOGIN_VENTANA_SEGUNDOS']} segundos.",
                    "error",
                )
        elif current_app.config["EMAIL_VERIFICATION_REQUIRED"] and (not usuario.correo_verificado):
            limpiar_fallos_login(current_app.extensions["login_rate_limiter"], request.remote_addr)
            session.clear()
            session.permanent = True
            session["verificacion_usuario_id"] = usuario.id
            flash("Confirma tu correo UPC antes de ingresar.", "info")
            return redirect(url_for("auth.verificar_correo"))
        else:
            limpiar_fallos_login(current_app.extensions["login_rate_limiter"], request.remote_addr)
            session.clear()
            session.permanent = True
            session["usuario_id"] = usuario.id
            flash(f"Bienvenido de nuevo, {usuario.nombre}.", "success")
            return redirect(_destino_seguro(request.args.get("siguiente"), url_for("pages.index")))
    return render_template("ingresar.html")


@bp.route("/verificar-correo", methods=["GET", "POST"])
def verificar_correo():
    if g.usuario:
        return redirect(url_for("pages.index"))
    usuario_id = session.get("verificacion_usuario_id")
    usuario = db.session.get(Usuario, usuario_id) if usuario_id else None
    if usuario is None:
        flash("Ingresa con tu cuenta para continuar la verificación.", "info")
        return redirect(url_for("auth.ingresar"))
    if usuario.correo_verificado:
        session.clear()
        session.permanent = True
        session["usuario_id"] = usuario.id
        return redirect(url_for("profile.perfil"))
    if request.method == "POST":
        resultado = validar_codigo(
            usuario, current_app.config["SECRET_KEY"], request.form.get("codigo", "")
        )
        if resultado == ResultadoVerificacion.VALIDO:
            completar_verificacion(usuario)
            db.session.commit()
            session.clear()
            session.permanent = True
            session["usuario_id"] = usuario.id
            flash("Correo UPC verificado. Tu cuenta ya está activa.", "success")
            return redirect(url_for("profile.perfil"))
        db.session.commit()
        if resultado == ResultadoVerificacion.INVALIDO:
            restantes = max(MAX_INTENTOS - usuario.verificacion_intentos, 0)
            flash(f"El código no coincide. Te quedan {restantes} intento(s).", "error")
        elif resultado == ResultadoVerificacion.AGOTADO:
            flash("Agotaste los intentos. Solicita un código nuevo para continuar.", "error")
        else:
            flash("El código venció. Solicita uno nuevo.", "error")
    return render_template(
        "verificar_correo.html",
        correo=usuario.correo_institucional,
        segundos_reenvio=segundos_para_reenviar(usuario),
        intentos_restantes=max(MAX_INTENTOS - usuario.verificacion_intentos, 0),
        correo_en_consola=str(current_app.config["MAIL_BACKEND"]).lower() == "console",
    )


@bp.post("/verificar-correo/reenviar")
def reenviar_codigo():
    usuario_id = session.get("verificacion_usuario_id")
    usuario = db.session.get(Usuario, usuario_id) if usuario_id else None
    if usuario is None or usuario.correo_verificado:
        return redirect(url_for("auth.ingresar"))
    espera_persistente = segundos_para_reenviar(usuario)
    if espera_persistente:
        flash(f"Espera {espera_persistente} segundos antes de pedir otro código.", "info")
        return redirect(url_for("auth.verificar_correo"))
    decision = limitar_reenvio(
        current_app.extensions["verification_resend_rate_limiter"], usuario.id, request.remote_addr
    )
    if not decision.permitido:
        flash(f"Demasiadas solicitudes. Reintenta en {decision.reintentar_en} segundos.", "error")
        return (
            render_template(
                "verificar_correo.html",
                correo=usuario.correo_institucional,
                segundos_reenvio=decision.reintentar_en,
                intentos_restantes=max(MAX_INTENTOS - usuario.verificacion_intentos, 0),
                correo_en_consola=str(current_app.config["MAIL_BACKEND"]).lower() == "console",
            ),
            429,
            {"Retry-After": str(decision.reintentar_en)},
        )
    enviado, espera = emitir_codigo_verificacion(usuario)
    if enviado:
        flash("Enviamos un código nuevo. El anterior dejó de funcionar.", "success")
    elif espera:
        flash(f"Espera {espera} segundos antes de pedir otro código.", "info")
    else:
        flash("No pudimos enviar el código. Intenta nuevamente en un momento.", "error")
    return redirect(url_for("auth.verificar_correo"))


@bp.post("/salir")
def salir():
    session.clear()
    flash("Sesion cerrada.", "info")
    return redirect(url_for("pages.index"))
