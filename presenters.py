"""Transforma modelos de dominio en contratos estables para Jinja2 o JSON."""


def curso_contexto(curso):
    if curso is None:
        return None
    return {"id": curso.id, "codigo": curso.codigo, "nombre": curso.nombre}


def horario_contexto(horario):
    return {
        "id": horario.id,
        "dia": horario.dia,
        "hora_inicio": horario.hora_inicio,
        "hora_fin": horario.hora_fin,
    }


def usuario_contexto(usuario, incluir_email=False):
    datos = {
        "id": usuario.id,
        "nombre": usuario.nombre,
        "iniciales": usuario.iniciales,
        "carrera": usuario.carrera,
        "ciclo": usuario.ciclo,
        "intereses": usuario.lista_intereses,
        "cursos": [curso_contexto(curso) for curso in usuario.cursos],
        "horarios": [horario_contexto(horario) for horario in usuario.horarios],
        "perfil_completo": usuario.perfil_completo,
    }
    if incluir_email:
        datos["correo_institucional"] = usuario.correo_institucional
    return datos


def match_contexto(resultado):
    return {
        "usuario": usuario_contexto(resultado["usuario"]),
        "score": resultado["score"],
        "porcentaje": resultado["porcentaje"],
        "confianza": resultado["confianza"],
        "cursos": [curso_contexto(curso) for curso in resultado["cursos"]],
        "horas": resultado["horas"],
        "minutos": resultado["minutos"],
        "intereses": resultado["intereses"],
        "razones": resultado["razones"],
        "componentes": resultado["componentes"],
    }


def grupo_contexto(grupo, afinidad=None):
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


def conexion_contexto(conexion, usuario_actual):
    otra = conexion.otra_persona(usuario_actual)
    return {
        "id": conexion.id,
        "estado": conexion.estado,
        "direccion": "enviada" if conexion.remitente_id == usuario_actual.id else "recibida",
        "persona": usuario_contexto(
            otra, incluir_email=conexion.estado == "aceptada"
        ),
        "creada_en": conexion.creada_en.isoformat() if conexion.creada_en else None,
        "actualizada_en": conexion.actualizada_en.isoformat()
        if conexion.actualizada_en
        else None,
    }


def paginacion_contexto(items, pagina, por_pagina):
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
