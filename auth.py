"""Verificacion de correo institucional para el registro.

Por ahora la verificacion es solo por dominio: se acepta el registro
si el correo pertenece a una universidad de la lista. Mas adelante se
puede reforzar con un correo de confirmacion (link o codigo).
"""

DOMINIOS_PERMITIDOS = ("upc.edu.pe",)


def es_correo_institucional(correo):
    """Devuelve True si el correo pertenece a un dominio universitario permitido.

    Acepta el dominio exacto o un subdominio (por ejemplo alumno.upc.edu.pe).
    """
    if not correo or correo.count("@") != 1 or any(caracter.isspace() for caracter in correo):
        return False
    usuario, dominio = correo.lower().split("@", 1)
    if not usuario or not dominio:
        return False
    return any(
        dominio == permitido or dominio.endswith("." + permitido)
        for permitido in DOMINIOS_PERMITIDOS
    )
