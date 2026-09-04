from __future__ import annotations

from flask import (
    current_app,
    jsonify,
    render_template,
)
from jinja2 import TemplateNotFound

from app.models.entities import (
    CarreraUPC,
    db,
    slugificar,
)
from app.services.media import MediaStorageError, delete_image

TIPOS_GRUPO = ("estudio", "social")
DIAS = ("Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado")
PASSWORD_MINIMO = 10
MAXIMO_POR_PAGINA = 48


def _delete_image_safely(public_url: str | None) -> None:
    """Compensa cargas remotas sin ocultar el resultado de la transacción SQL."""
    if not public_url:
        return
    try:
        delete_image(public_url)
    except MediaStorageError:
        current_app.logger.exception("No se pudo eliminar un avatar remoto")


def _minutos(hora):
    partes = (hora or "").split(":")
    if len(partes) != 2:
        raise ValueError("Hora invalida")
    horas, minutos = map(int, partes)
    if not 0 <= horas <= 23 or not 0 <= minutos <= 59:
        raise ValueError("Hora invalida")
    return horas * 60 + minutos


def _horario_valido(dia, inicio, fin):
    if dia not in DIAS:
        return False
    try:
        return _minutos(inicio) < _minutos(fin)
    except (TypeError, ValueError):
        return False


def _password_valida(password):
    return (
        len(password) >= PASSWORD_MINIMO
        and any(caracter.isalpha() for caracter in password)
        and any(caracter.isdigit() for caracter in password)
    )


def _entero_acotado(valor, predeterminado, minimo, maximo):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return predeterminado
    return min(max(numero, minimo), maximo)


def _booleano(valor, predeterminado=False):
    if valor is None:
        return predeterminado
    return str(valor).strip().lower() in {"1", "true", "si", "on"}


def _booleano_opcional(valor):
    if valor is None or str(valor).strip() == "":
        return None
    normalizado = str(valor).strip().lower()
    if normalizado in {"1", "true", "si", "on"}:
        return True
    if normalizado in {"0", "false", "no", "off"}:
        return False
    raise ValueError("El valor booleano debe ser si o no")


def _resolver_carrera_upc(carrera_id_texto, nombre):
    """Resuelve ID o nombre legado contra el catálogo activo."""
    carrera_id_texto = str(carrera_id_texto or "").strip()
    nombre = str(nombre or "").strip()
    if carrera_id_texto:
        if not carrera_id_texto.isdigit():
            raise ValueError("La carrera UPC seleccionada no es válida.")
        carrera = db.session.get(CarreraUPC, int(carrera_id_texto))
    elif nombre:
        carrera = CarreraUPC.query.filter_by(clave=slugificar(nombre), activa=True).one_or_none()
    else:
        return None
    if carrera is None or not carrera.activa:
        raise ValueError("Selecciona una carrera disponible del catálogo UPC.")
    return carrera


def _destino_seguro(valor, predeterminado):
    if valor and valor.startswith("/") and (not valor.startswith("//")):
        return valor
    return predeterminado


def renderizar_contrato(template, contrato, **contexto_jinja):
    """Renderiza Jinja si existe; durante la fusion expone el contrato JSON."""
    try:
        return render_template(template, **contexto_jinja, contrato=contrato)
    except TemplateNotFound as error:
        if error.name != template:
            raise
        return jsonify({"template_pendiente": template, **contrato})
