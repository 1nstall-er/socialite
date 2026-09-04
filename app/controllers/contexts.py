from __future__ import annotations

from flask import (
    g,
    request,
)

from app.controllers.common import (
    DIAS,
    MAXIMO_POR_PAGINA,
    TIPOS_GRUPO,
    _entero_acotado,
)
from app.controllers.presenters import (
    catalogo_upc_contexto,
    conversacion_contexto,
    grupo_contexto,
    match_contexto,
    paginacion_contexto,
)
from app.models.entities import (
    CarreraUPC,
    EspacioUPC,
)
from app.models.queries import (
    candidatos_para,
    conexiones_con_candidatos,
    contactos_aceptados_de,
    grupos_filtrados,
    mensajes_no_leidos_por_contacto,
    ultimos_mensajes_por_contacto,
    usuario_para_matching,
)
from app.services.matching import (
    GrafoAfinidadUPC,
    calcular_afinidad_grupo,
    preparar_perfil,
    rankear_candidatos_paginado,
    rankear_top_candidatos,
)


def contexto_catalogo_upc():
    espacios = (
        EspacioUPC.query.filter_by(activo=True)
        .order_by(EspacioUPC.campus, EspacioUPC.tipo, EspacioUPC.nombre)
        .all()
    )
    carreras = (
        CarreraUPC.query.filter_by(activa=True)
        .order_by(CarreraUPC.facultad, CarreraUPC.nombre)
        .all()
    )
    return catalogo_upc_contexto(espacios, carreras)


def contexto_companeros():
    busqueda = request.args.get("q", "").strip()
    curso_id = request.args.get("curso", type=int)
    afinidad = _entero_acotado(request.args.get("afinidad"), 0, 0, 100)
    pagina = _entero_acotado(request.args.get("pagina"), 1, 1, 100000)
    por_pagina = _entero_acotado(request.args.get("por_pagina"), 18, 1, MAXIMO_POR_PAGINA)
    usuario_actual = usuario_para_matching(g.usuario.id)
    candidatos = candidatos_para(usuario_actual.id, busqueda, curso_id)
    grafo = GrafoAfinidadUPC([usuario_actual, *candidatos])
    paginacion = rankear_candidatos_paginado(
        usuario_actual,
        candidatos,
        afinidad_minima=afinidad,
        pagina=pagina,
        por_pagina=por_pagina,
        grafo=grafo,
    )
    conexiones = conexiones_con_candidatos(
        usuario_actual.id, [resultado["usuario"].id for resultado in paginacion["items"]]
    )
    contrato = {
        "resultados": [match_contexto(item) for item in paginacion["items"]],
        "paginacion": {clave: valor for clave, valor in paginacion.items() if clave != "items"},
        "filtros": {"q": busqueda, "curso": curso_id, "afinidad": afinidad},
    }
    return {
        "contrato": contrato,
        "sugerencias": paginacion["items"],
        "conexiones": conexiones,
        "paginacion": contrato["paginacion"],
        "filtros": contrato["filtros"],
    }


def contexto_top_companeros():
    usuario_actual = usuario_para_matching(g.usuario.id)
    candidatos = candidatos_para(usuario_actual.id)
    grafo = GrafoAfinidadUPC([usuario_actual, *candidatos])
    resultados = rankear_top_candidatos(usuario_actual, candidatos, limite=10, grafo=grafo)
    return {
        "resultados": [match_contexto(item) for item in resultados],
        "algoritmo": {
            "estructura": "max_heap",
            "limite": 10,
            "complejidad": "O(n + k log n)",
            "grafo_max_grado": 2,
        },
    }


def contexto_bandeja_mensajes():
    contactos = contactos_aceptados_de(g.usuario.id)
    ultimos = ultimos_mensajes_por_contacto(g.usuario.id)
    no_leidos = mensajes_no_leidos_por_contacto(g.usuario.id)
    conversaciones = []
    for conexion in contactos:
        contacto = conexion.otra_persona(g.usuario)
        conversaciones.append(
            conversacion_contexto(
                conexion, g.usuario, ultimos.get(contacto.id), no_leidos.get(contacto.id, 0)
            )
        )
    conversaciones.sort(key=lambda conversacion: conversacion["actualizada_en"], reverse=True)
    return {"conversaciones": conversaciones, "total_no_leidos": sum(no_leidos.values())}


def contexto_grupos():
    tipo = request.args.get("tipo", "").strip()
    curso_id = request.args.get("curso", type=int)
    dia = request.args.get("dia", "").strip()
    busqueda = request.args.get("q", "").strip()
    solo_disponibles = request.args.get("disponibles") == "1"
    pagina = _entero_acotado(request.args.get("pagina"), 1, 1, 100000)
    por_pagina = _entero_acotado(request.args.get("por_pagina"), 18, 1, MAXIMO_POR_PAGINA)
    tipo_consulta = tipo if tipo in TIPOS_GRUPO else ""
    dia_consulta = dia if dia in DIAS else ""
    grupos = grupos_filtrados(tipo_consulta, curso_id, dia_consulta, busqueda)
    if solo_disponibles:
        grupos = [grupo for grupo in grupos if not grupo.esta_lleno]
    paginacion = paginacion_contexto(grupos, pagina, por_pagina)
    perfil_preparado = preparar_perfil(g.usuario) if g.usuario else None
    afinidades = {
        grupo.id: calcular_afinidad_grupo(g.usuario, grupo, perfil_usuario=perfil_preparado)
        for grupo in paginacion["items"]
        if g.usuario
    }
    contrato = {
        "resultados": [
            grupo_contexto(grupo, afinidades.get(grupo.id)) for grupo in paginacion["items"]
        ],
        "paginacion": {clave: valor for clave, valor in paginacion.items() if clave != "items"},
        "filtros": {
            "q": busqueda,
            "tipo": tipo_consulta,
            "curso": curso_id,
            "dia": dia_consulta,
            "disponibles": solo_disponibles,
        },
    }
    return {
        "contrato": contrato,
        "grupos": paginacion["items"],
        "afinidades": afinidades,
        "paginacion": contrato["paginacion"],
        "filtros": contrato["filtros"],
    }
