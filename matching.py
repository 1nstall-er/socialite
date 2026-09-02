"""Motor de afinidad explicable y determinista para Socialite.

La logica de este modulo es pura: no realiza consultas ni depende de Flask.
Eso permite probarla de forma aislada y reutilizarla desde rutas HTML, una API
o trabajos en segundo plano.
"""

from collections import defaultdict
from math import isfinite
from unicodedata import category, normalize


PESO_CURSOS = 0.50
PESO_HORARIOS = 0.30
PESO_INTERESES = 0.20
MINUTOS_HORARIO_COMPLETO = 120
INTERESES_PARA_PUNTAJE_COMPLETO = 3


def normalizar_texto(valor):
    """Normaliza texto para comparar sin depender de tildes o mayusculas."""
    texto = normalize("NFKD", (valor or "").strip().casefold())
    return "".join(caracter for caracter in texto if category(caracter) != "Mn")


def _a_minutos(valor):
    partes = (valor or "").split(":")
    if len(partes) != 2:
        raise ValueError("La hora debe usar el formato HH:MM")
    horas, minutos = map(int, partes)
    if not 0 <= horas <= 23 or not 0 <= minutos <= 59:
        raise ValueError("Hora fuera del rango permitido")
    return horas * 60 + minutos


def _intervalos_por_dia(horarios):
    """Agrupa y fusiona bloques solapados en O(n log n)."""
    por_dia = defaultdict(list)
    for horario in horarios:
        try:
            inicio = _a_minutos(horario.hora_inicio)
            fin = _a_minutos(horario.hora_fin)
        except (AttributeError, TypeError, ValueError):
            continue
        if inicio < fin and horario.dia:
            por_dia[normalizar_texto(horario.dia)].append((inicio, fin))

    fusionados = {}
    for dia, intervalos in por_dia.items():
        resultado = []
        for inicio, fin in sorted(intervalos):
            if resultado and inicio <= resultado[-1][1]:
                resultado[-1] = (resultado[-1][0], max(resultado[-1][1], fin))
            else:
                resultado.append((inicio, fin))
        fusionados[dia] = resultado
    return fusionados


def minutos_compartidos(horarios_a, horarios_b):
    """Calcula interseccion real con un recorrido lineal por cada dia.

    Los bloques se fusionan primero para impedir que disponibilidades duplicadas
    inflen el puntaje. Despues se usa un algoritmo de dos punteros O(n + m).
    """
    dias_a = _intervalos_por_dia(horarios_a)
    dias_b = _intervalos_por_dia(horarios_b)
    return _minutos_entre_intervalos(dias_a, dias_b)


def _minutos_entre_intervalos(dias_a, dias_b):
    total = 0

    for dia in dias_a.keys() & dias_b.keys():
        bloques_a = dias_a[dia]
        bloques_b = dias_b[dia]
        indice_a = indice_b = 0
        while indice_a < len(bloques_a) and indice_b < len(bloques_b):
            inicio_a, fin_a = bloques_a[indice_a]
            inicio_b, fin_b = bloques_b[indice_b]
            total += max(0, min(fin_a, fin_b) - max(inicio_a, inicio_b))
            if fin_a <= fin_b:
                indice_a += 1
            else:
                indice_b += 1
    return total


def preparar_perfil(usuario):
    """Precalcula señales reutilizables durante un lote de comparaciones."""
    return {
        "cursos": {curso.id: curso for curso in usuario.cursos},
        "intereses": {
            normalizar_texto(valor): valor for valor in usuario.lista_intereses
        },
        "intervalos": _intervalos_por_dia(usuario.horarios),
        "tiene_cursos": bool(usuario.cursos),
        "tiene_horarios": bool(usuario.horarios),
        "tiene_intereses": bool(usuario.lista_intereses),
    }


def _cursos_comunes(perfil_usuario, perfil_candidato):
    return [
        curso
        for identificador, curso in perfil_candidato["cursos"].items()
        if identificador in perfil_usuario["cursos"]
    ]


def _intereses_comunes(perfil_usuario, perfil_candidato):
    propios = perfil_usuario["intereses"]
    ajenos = perfil_candidato["intereses"]
    return [propios[clave] for clave in sorted(propios.keys() & ajenos.keys())]


def _componente_cursos(cantidad):
    if cantidad <= 0:
        return 0.0
    if cantidad == 1:
        return 0.80
    return 1.0


def _limitar(valor, minimo=0.0, maximo=1.0):
    if not isfinite(valor):
        return minimo
    return min(max(valor, minimo), maximo)


def calcular_afinidad(
    usuario, candidato, perfil_usuario=None, perfil_candidato=None
):
    """Devuelve puntaje, componentes y razones listas para Jinja2.

    Pesos del MVP:
    - cursos en comun: 50 %
    - disponibilidad compartida: 30 %
    - intereses en comun: 20 %
    """
    perfil_usuario = perfil_usuario or preparar_perfil(usuario)
    perfil_candidato = perfil_candidato or preparar_perfil(candidato)
    cursos = _cursos_comunes(perfil_usuario, perfil_candidato)
    intereses = _intereses_comunes(perfil_usuario, perfil_candidato)
    minutos = _minutos_entre_intervalos(
        perfil_usuario["intervalos"], perfil_candidato["intervalos"]
    )

    valor_cursos = _componente_cursos(len(cursos))
    valor_horarios = _limitar(minutos / MINUTOS_HORARIO_COMPLETO)
    valor_intereses = _limitar(
        len(intereses) / INTERESES_PARA_PUNTAJE_COMPLETO
    )
    total = (
        valor_cursos * PESO_CURSOS
        + valor_horarios * PESO_HORARIOS
        + valor_intereses * PESO_INTERESES
    )
    total = round(_limitar(total), 4)

    senales_disponibles = sum(
        (
            perfil_usuario["tiene_cursos"] and perfil_candidato["tiene_cursos"],
            perfil_usuario["tiene_horarios"] and perfil_candidato["tiene_horarios"],
            perfil_usuario["tiene_intereses"]
            and perfil_candidato["tiene_intereses"],
        )
    )
    razones = []
    if cursos:
        razones.append(
            {
                "tipo": "cursos",
                "titulo": f"{len(cursos)} curso{'s' if len(cursos) != 1 else ''} en comun",
                "detalle": ", ".join(curso.codigo for curso in cursos),
            }
        )
    if minutos:
        razones.append(
            {
                "tipo": "horarios",
                "titulo": f"{round(minutos / 60, 1)} h disponibles juntos",
                "detalle": "Coincidencia real entre bloques libres",
            }
        )
    if intereses:
        razones.append(
            {
                "tipo": "intereses",
                "titulo": f"{len(intereses)} interes{'es' if len(intereses) != 1 else ''} compartido{'s' if len(intereses) != 1 else ''}",
                "detalle": ", ".join(intereses),
            }
        )

    return {
        "score": total,
        "porcentaje": round(total * 100),
        "confianza": round(senales_disponibles / 3 * 100),
        "cursos": cursos,
        "horas": round(minutos / 60, 1),
        "minutos": minutos,
        "intereses": intereses,
        "razones": razones,
        "componentes": {
            "cursos": {
                "valor": round(valor_cursos, 4),
                "puntos": round(valor_cursos * PESO_CURSOS * 100),
                "peso": round(PESO_CURSOS * 100),
            },
            "horarios": {
                "valor": round(valor_horarios, 4),
                "puntos": round(valor_horarios * PESO_HORARIOS * 100),
                "peso": round(PESO_HORARIOS * 100),
            },
            "intereses": {
                "valor": round(valor_intereses, 4),
                "puntos": round(valor_intereses * PESO_INTERESES * 100),
                "peso": round(PESO_INTERESES * 100),
            },
        },
    }


def calcular_afinidad_grupo(usuario, grupo, perfil_usuario=None):
    """Afinidad usuario-grupo, normalizada a partir de curso y horario."""
    perfil_usuario = perfil_usuario or preparar_perfil(usuario)
    mismo_curso = bool(
        grupo.curso and grupo.curso.id in perfil_usuario["cursos"]
    )

    class BloqueGrupo:
        dia = grupo.dia
        hora_inicio = grupo.hora_inicio
        hora_fin = grupo.hora_fin

    minutos = _minutos_entre_intervalos(
        perfil_usuario["intervalos"], _intervalos_por_dia([BloqueGrupo()])
    )
    valor_curso = 1.0 if mismo_curso else 0.0
    valor_horario = _limitar(minutos / MINUTOS_HORARIO_COMPLETO)
    # Al no existir intereses de grupo, los pesos disponibles se renormalizan.
    total = (valor_curso * PESO_CURSOS + valor_horario * PESO_HORARIOS) / (
        PESO_CURSOS + PESO_HORARIOS
    )
    total = round(_limitar(total), 4)
    return {
        "score": total,
        "porcentaje": round(total * 100),
        "mismo_curso": mismo_curso,
        "horas": round(minutos / 60, 1),
        "minutos": minutos,
    }


def rankear_candidatos(usuario, candidatos, afinidad_minima=0):
    """Calcula una sola vez por candidato y ordena de forma estable."""
    minimo = _limitar(float(afinidad_minima) / 100)
    resultados = []
    perfil_usuario = preparar_perfil(usuario)
    for candidato in candidatos:
        resultado = calcular_afinidad(
            usuario,
            candidato,
            perfil_usuario=perfil_usuario,
            perfil_candidato=preparar_perfil(candidato),
        )
        if resultado["score"] < minimo:
            continue
        resultados.append({"usuario": candidato, **resultado})
    return ordenar_candidatos(resultados)


def score(mismo_curso, horas_compartidas, intereses_comunes):
    """Compatibilidad con la API inicial; devuelve un valor entre 0 y 1."""
    cursos = 1.0 if mismo_curso else 0.0
    horarios = _limitar(float(horas_compartidas) / 2)
    intereses = _limitar(float(intereses_comunes) / 3)
    return round(
        cursos * PESO_CURSOS
        + horarios * PESO_HORARIOS
        + intereses * PESO_INTERESES,
        4,
    )


def ordenar_candidatos(candidatos):
    """Orden descendente por score con desempate determinista por nombre e id."""
    return sorted(
        candidatos,
        key=lambda candidato: (
            -candidato["score"],
            normalizar_texto(candidato["usuario"].nombre),
            candidato["usuario"].id or 0,
        ),
    )
