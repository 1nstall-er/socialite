"""Contratos estables y serializables para Jinja2 y JSON."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from models import (
    CAMPUS_UPC,
    CICLOS_MEDICINA_UPC,
    CICLOS_REGULARES_UPC,
    CREDITOS_EXTRAACADEMICOS_REQUERIDOS,
    INTERESES_UPC,
    MAX_INTERESES_USUARIO,
    VIERNES_CULTURAL_FIN,
    VIERNES_CULTURAL_INICIO,
    CampusUPC,
    CarreraUPC,
    CategoriaInteresUPC,
    EspacioUPC,
    EstiloEstudio,
    FacultadUPC,
    MetaCursoUPC,
    ModalidadUPC,
    ObjetivoSocialite,
    ParticipacionUPC,
    PerfilUPC,
    RolActividadUPC,
    RolCursoUPC,
    TipoActividadUPC,
    ciclos_para_carrera,
    duracion_ciclos_carrera,
)


def _opciones(tipo_enum: type) -> list[dict[str, str]]:
    return [
        {"valor": miembro.value, "etiqueta": miembro.etiqueta}
        for miembro in tipo_enum
    ]


def curso_contexto(curso: Any) -> dict[str, Any] | None:
    if curso is None:
        return None
    return {"id": curso.id, "codigo": curso.codigo, "nombre": curso.nombre}


def horario_contexto(horario: Any) -> dict[str, Any]:
    return {
        "id": horario.id,
        "dia": horario.dia,
        "hora_inicio": horario.hora_inicio,
        "hora_fin": horario.hora_fin,
    }


def espacio_upc_contexto(espacio: EspacioUPC | None) -> dict[str, Any] | None:
    if espacio is None:
        return None
    return {
        "id": espacio.id,
        "clave": espacio.clave,
        "campus": espacio.campus.value,
        "campus_etiqueta": espacio.campus.etiqueta,
        "nombre": espacio.nombre,
        "tipo": espacio.tipo.value,
        "tipo_etiqueta": espacio.tipo.etiqueta,
        "pabellon": espacio.pabellon,
        "piso": espacio.piso,
        "aforo_minimo": espacio.aforo_minimo,
        "aforo_maximo": espacio.aforo_maximo,
        "requiere_reserva": espacio.requiere_reserva,
        "max_minutos_diarios": espacio.max_minutos_diarios,
        "fuente_url": espacio.fuente_url,
        "verificado_en": espacio.verificado_en.isoformat(),
    }


def carrera_upc_contexto(carrera: CarreraUPC | None) -> dict[str, Any] | None:
    if carrera is None:
        return None
    ciclos = ciclos_para_carrera(carrera.clave)
    return {
        "id": carrera.id,
        "clave": carrera.clave,
        "nombre": carrera.nombre,
        "facultad": carrera.facultad.value,
        "facultad_etiqueta": carrera.facultad.etiqueta,
        "duracion_ciclos": len(ciclos),
        "ciclos": [{"valor": ciclo, "etiqueta": f"Ciclo {ciclo}"} for ciclo in ciclos],
        "fuente_url": carrera.fuente_url,
        "verificado_en": carrera.verificado_en.isoformat(),
    }


def perfil_upc_contexto(perfil: PerfilUPC | None) -> dict[str, Any] | None:
    if perfil is None:
        return None
    return {
        "campus": perfil.campus.value,
        "campus_etiqueta": perfil.campus.etiqueta,
        "facultad": perfil.facultad.value if perfil.facultad else None,
        "facultad_etiqueta": perfil.facultad.etiqueta if perfil.facultad else None,
        "carrera": carrera_upc_contexto(perfil.carrera_upc),
        "modalidad": perfil.modalidad.value if perfil.modalidad else None,
        "modalidad_etiqueta": perfil.modalidad.etiqueta if perfil.modalidad else None,
        "objetivo": perfil.objetivo.value if perfil.objetivo else None,
        "objetivo_etiqueta": perfil.objetivo.etiqueta if perfil.objetivo else None,
        "estilo_estudio": perfil.estilo_estudio.value if perfil.estilo_estudio else None,
        "estilo_estudio_etiqueta": (
            perfil.estilo_estudio.etiqueta if perfil.estilo_estudio else None
        ),
        "viernes_cultural_disponible": perfil.viernes_cultural_disponible,
        "acepta_intercampus": perfil.acepta_intercampus,
        "espacio_preferido": espacio_upc_contexto(perfil.espacio_preferido),
    }


def participacion_upc_contexto(
    participacion: ParticipacionUPC, incluir_creditos: bool = False
) -> dict[str, Any]:
    datos = {
        "id": participacion.id,
        "tipo": participacion.tipo.value,
        "tipo_etiqueta": participacion.tipo.etiqueta,
        "nombre": participacion.nombre,
        "rol": participacion.rol.value,
        "rol_etiqueta": participacion.rol.etiqueta,
        "campus": participacion.campus.value if participacion.campus else None,
        "campus_etiqueta": participacion.campus.etiqueta if participacion.campus else None,
        "periodo": participacion.periodo,
        "activa": participacion.activa,
    }
    if incluir_creditos:
        datos["creditos_confirmados"] = participacion.creditos_confirmados
    return datos


def meta_curso_contexto(meta: MetaCursoUPC) -> dict[str, Any]:
    return {
        "id": meta.id,
        "curso": curso_contexto(meta.curso),
        "rol": meta.rol.value,
        "rol_etiqueta": meta.rol.etiqueta,
        "prioridad": meta.prioridad,
        "intento": meta.intento,
        "busca_equipo": meta.busca_equipo,
    }


def usuario_contexto(
    usuario: Any, incluir_email: bool = False, incluir_privado: bool = False
) -> dict[str, Any]:
    participaciones = [
        participacion_upc_contexto(item, incluir_creditos=incluir_privado)
        for item in usuario.participaciones_upc
        if item.activa
    ]
    datos: dict[str, Any] = {
        "id": usuario.id,
        "nombre": usuario.nombre,
        "iniciales": usuario.iniciales,
        "foto_url": usuario.foto_url,
        "biografia": usuario.biografia,
        "carrera": usuario.carrera,
        "ciclo": usuario.ciclo,
        "intereses": usuario.lista_intereses,
        "intereses_detalle": [
            {
                "clave": interes.clave,
                "etiqueta": interes.etiqueta,
                "categoria": interes.categoria.value,
                "categoria_etiqueta": interes.categoria.etiqueta,
            }
            for interes in usuario.intereses_catalogados
        ],
        "cursos": [curso_contexto(curso) for curso in usuario.cursos],
        "horarios": [horario_contexto(horario) for horario in usuario.horarios],
        "perfil_completo": usuario.perfil_completo,
        "perfil_upc": perfil_upc_contexto(usuario.perfil_upc),
        "participaciones_upc": participaciones,
    }
    if incluir_email:
        datos["correo_institucional"] = usuario.correo_institucional
    if incluir_privado:
        datos["creditos_extraacademicos"] = {
            "confirmados": usuario.creditos_extraacademicos_confirmados,
            "requeridos": CREDITOS_EXTRAACADEMICOS_REQUERIDOS,
            "pendientes": usuario.creditos_extraacademicos_pendientes,
        }
        datos["metas_curso"] = [meta_curso_contexto(meta) for meta in usuario.metas_curso]
    return datos


def match_contexto(resultado: dict[str, Any]) -> dict[str, Any]:
    return {
        "usuario": usuario_contexto(resultado["usuario"]),
        "score": resultado["score"],
        "porcentaje": resultado["porcentaje"],
        "confianza": resultado["confianza"],
        "probabilidad_emparejamiento": resultado[
            "probabilidad_emparejamiento"
        ],
        "modelo_probabilidad": resultado["modelo_probabilidad"],
        "cursos": [curso_contexto(curso) for curso in resultado["cursos"]],
        "horas": resultado["horas"],
        "minutos": resultado["minutos"],
        "intereses": resultado["intereses"],
        "intereses_detalle": resultado["intereses_detalle"],
        "razones": resultado["razones"],
        "componentes": resultado["componentes"],
        "contexto_upc": resultado.get("contexto_upc", {}),
    }


def grupo_contexto(grupo: Any, afinidad: dict[str, Any] | None = None) -> dict[str, Any]:
    datos = {
        "id": grupo.id,
        "tipo": grupo.tipo,
        "curso": curso_contexto(grupo.curso),
        "creador": usuario_contexto(grupo.creador),
        "lugar": grupo.lugar,
        "dia": grupo.dia,
        "hora_inicio": grupo.hora_inicio,
        "hora_fin": grupo.hora_fin,
        "max_miembros": grupo.max_miembros,
        "cantidad_miembros": len(grupo.miembros),
        "cupos_disponibles": grupo.cupos_disponibles,
        "esta_lleno": grupo.esta_lleno,
        "miembros": [usuario_contexto(usuario) for usuario in grupo.miembros],
        "creado_en": grupo.creado_en.isoformat() if grupo.creado_en else None,
    }
    if afinidad is not None:
        datos["afinidad"] = afinidad
    return datos


def conexion_contexto(conexion: Any, usuario_actual: Any) -> dict[str, Any]:
    otra = conexion.otra_persona(usuario_actual)
    return {
        "id": conexion.id,
        "estado": conexion.estado,
        "direccion": "enviada" if conexion.remitente_id == usuario_actual.id else "recibida",
        "persona": usuario_contexto(otra, incluir_email=conexion.estado == "aceptada"),
        "creada_en": conexion.creada_en.isoformat() if conexion.creada_en else None,
        "actualizada_en": (
            conexion.actualizada_en.isoformat() if conexion.actualizada_en else None
        ),
    }


def catalogo_upc_contexto(
    espacios: Iterable[EspacioUPC], carreras: Iterable[CarreraUPC]
) -> dict[str, Any]:
    carreras_contexto = [
        carrera_upc_contexto(carrera) for carrera in carreras
    ]
    intereses_contexto = [
        {
            "clave": interes.clave,
            "etiqueta": interes.etiqueta,
            "categoria": interes.categoria.value,
            "categoria_etiqueta": interes.categoria.etiqueta,
        }
        for interes in INTERESES_UPC
    ]
    return {
        "campus": [
            {
                "valor": campus.value,
                "etiqueta": campus.etiqueta,
                "nombre": CAMPUS_UPC[campus].nombre,
                "distrito": CAMPUS_UPC[campus].distrito,
                "direccion": CAMPUS_UPC[campus].direccion,
            }
            for campus in CampusUPC
        ],
        "facultades": _opciones(FacultadUPC),
        "carreras": carreras_contexto,
        "carreras_por_facultad": [
            {
                "facultad": facultad.value,
                "facultad_etiqueta": facultad.etiqueta,
                "carreras": [
                    carrera
                    for carrera in carreras_contexto
                    if carrera and carrera["facultad"] == facultad.value
                ],
            }
            for facultad in FacultadUPC
        ],
        "ciclos": [
            {"valor": ciclo, "etiqueta": f"Ciclo {ciclo}"}
            for ciclo in range(1, CICLOS_MEDICINA_UPC + 1)
        ],
        "duracion_ciclos": {
            "regular": CICLOS_REGULARES_UPC,
            "medicina": duracion_ciclos_carrera("medicina"),
        },
        "intereses": intereses_contexto,
        "intereses_por_categoria": [
            {
                "categoria": categoria.value,
                "categoria_etiqueta": categoria.etiqueta,
                "intereses": [
                    interes
                    for interes in intereses_contexto
                    if interes["categoria"] == categoria.value
                ],
            }
            for categoria in CategoriaInteresUPC
        ],
        "limites": {"max_intereses": MAX_INTERESES_USUARIO},
        "modalidades": _opciones(ModalidadUPC),
        "objetivos": _opciones(ObjetivoSocialite),
        "estilos_estudio": _opciones(EstiloEstudio),
        "tipos_actividad": _opciones(TipoActividadUPC),
        "roles_actividad": _opciones(RolActividadUPC),
        "roles_curso": _opciones(RolCursoUPC),
        "viernes_cultural": {
            "dia": "Viernes",
            "hora_inicio": VIERNES_CULTURAL_INICIO,
            "hora_fin": VIERNES_CULTURAL_FIN,
        },
        "creditos_extraacademicos_requeridos": CREDITOS_EXTRAACADEMICOS_REQUERIDOS,
        "espacios": [espacio_upc_contexto(espacio) for espacio in espacios],
    }


def paginacion_contexto(
    items: list[Any], pagina: int, por_pagina: int
) -> dict[str, Any]:
    total = len(items)
    paginas = max((total + por_pagina - 1) // por_pagina, 1)
    pagina = max(1, min(pagina, paginas))
    inicio = (pagina - 1) * por_pagina
    return {
        "items": items[inicio : inicio + por_pagina],
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total": total,
        "paginas": paginas,
        "tiene_anterior": pagina > 1,
        "tiene_siguiente": pagina < paginas,
    }
