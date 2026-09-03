"""Motor de afinidad puro, explicable y consciente del ecosistema UPC.

No importa Flask ni ejecuta consultas. Recibe objetos compatibles con los
protocolos declarados aqui, precalcula sus senales una vez y produce contratos
serializables para Jinja2 o JSON.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from heapq import heapify, heappop, nsmallest
from math import isfinite
from statistics import fmean
from typing import Protocol, TypedDict, cast
from unicodedata import category, normalize

PESO_CURSOS = 0.50
PESO_HORARIOS = 0.30
PESO_INTERESES = 0.20
PESO_CAMPUS = 0.12
PESO_CONTEXTO_ACADEMICO = 0.08
PESO_ESTILO_OBJETIVO = 0.08
PESO_VIDA_UNIVERSITARIA = 0.06
PESO_METAS_CURSO = 0.10
PESO_GRAFO = 0.08
MINUTOS_HORARIO_COMPLETO = 120
PESO_TOTAL_POSIBLE = sum(
    (
        PESO_CURSOS,
        PESO_HORARIOS,
        PESO_INTERESES,
        PESO_CAMPUS,
        PESO_CONTEXTO_ACADEMICO,
        PESO_ESTILO_OBJETIVO,
        PESO_VIDA_UNIVERSITARIA,
        PESO_METAS_CURSO,
        PESO_GRAFO,
    )
)
PROBABILIDAD_NEUTRAL = 0.50


class CursoCompatible(Protocol):
    id: int | None
    codigo: str
    nombre: str


class HorarioCompatible(Protocol):
    dia: str
    hora_inicio: str
    hora_fin: str


class UsuarioCompatible(Protocol):
    id: int | None
    nombre: str
    carrera: str | None
    cursos: Sequence[CursoCompatible]
    horarios: Sequence[HorarioCompatible]
    lista_intereses: Sequence[str]


class MetaCursoPreparada(TypedDict):
    rol: str
    prioridad: int
    busca_equipo: bool


class ContextoUPCPreparado(TypedDict):
    campus: str | None
    campus_etiqueta: str | None
    facultad: str | None
    facultad_etiqueta: str | None
    carrera: str | None
    carrera_etiqueta: str | None
    modalidad: str | None
    objetivo: str | None
    estilo_estudio: str | None
    viernes_cultural_disponible: bool | None
    acepta_intercampus: bool
    espacio_clave: str | None
    espacio_nombre: str | None


class PerfilPreparado(TypedDict):
    cursos: dict[str, CursoCompatible]
    intereses: dict[str, str]
    intereses_categorias: dict[str, str]
    intervalos: dict[str, list[tuple[int, int]]]
    carrera: str
    contexto_upc: ContextoUPCPreparado
    actividades_tipos: dict[str, str]
    actividades_nombres: dict[str, str]
    metas_curso: dict[str, MetaCursoPreparada]
    tiene_cursos: bool
    tiene_horarios: bool
    tiene_intereses: bool


class RankingPaginado(TypedDict):
    items: list[dict[str, object]]
    pagina: int
    por_pagina: int
    total: int
    paginas: int
    tiene_anterior: bool
    tiene_siguiente: bool


class ContextoConexionGrafo(TypedDict):
    grado: int | None
    tipo: str
    via: list[str]
    intermediario_id: int | None
    evaluable: bool


@dataclass(frozen=True, slots=True)
class ComponenteAfinidad:
    clave: str
    valor: float
    peso: float
    disponible: bool = True


class GrafoAfinidadUPC:
    """Grafo implícito por campus/facultad, sin materializar cliques O(n²).

    Los índices invertidos conectan estudiantes que comparten campus o
    facultad. Un BFS acotado expande cada bucket una sola vez y admite además
    aristas sociales explícitas, como conexiones aceptadas.
    """

    def __init__(
        self,
        usuarios: Iterable[UsuarioCompatible],
        conexiones_aceptadas: Iterable[tuple[int, int]] = (),
    ) -> None:
        self._usuarios: dict[int, UsuarioCompatible] = {}
        self._campus: defaultdict[str, set[int]] = defaultdict(set)
        self._facultades: defaultdict[str, set[int]] = defaultdict(set)
        self._conexiones: defaultdict[int, set[int]] = defaultdict(set)
        self._tiene_senales: dict[int, bool] = {}
        for usuario in usuarios:
            usuario_id = usuario.id
            if usuario_id is None:
                continue
            self._usuarios[usuario_id] = usuario
            contexto = _contexto_upc(usuario)
            self._tiene_senales[usuario_id] = bool(
                contexto["campus"] or contexto["facultad"]
            )
            if contexto["campus"]:
                self._campus[contexto["campus"]].add(usuario_id)
            if contexto["facultad"]:
                self._facultades[contexto["facultad"]].add(usuario_id)
        for origen, destino in conexiones_aceptadas:
            if origen == destino or origen not in self._usuarios or destino not in self._usuarios:
                continue
            self._conexiones[origen].add(destino)
            self._conexiones[destino].add(origen)
            self._tiene_senales[origen] = True
            self._tiene_senales[destino] = True

    def contextos_desde(
        self, origen_id: int, max_grado: int = 2
    ) -> dict[int, ContextoConexionGrafo]:
        """Devuelve distancias mínimas con BFS en O(V + E + buckets)."""
        if origen_id not in self._usuarios or max_grado < 1:
            return {}
        distancias = {origen_id: 0}
        vias: dict[int, list[str]] = {origen_id: []}
        intermediarios: dict[int, int | None] = {origen_id: None}
        cola = deque([origen_id])
        buckets_expandidos: set[tuple[str, str]] = set()

        def descubrir(
            actual_id: int, vecino_id: int, razones: list[str]
        ) -> None:
            nueva_distancia = distancias[actual_id] + 1
            if vecino_id == actual_id or vecino_id in distancias:
                return
            distancias[vecino_id] = nueva_distancia
            vias[vecino_id] = list(dict.fromkeys([*vias[actual_id], *razones]))
            intermediarios[vecino_id] = actual_id if nueva_distancia == 2 else None
            cola.append(vecino_id)

        while cola:
            actual_id = cola.popleft()
            if distancias[actual_id] >= max_grado:
                continue
            for vecino_id in self._conexiones.get(actual_id, ()):
                descubrir(actual_id, vecino_id, ["conexion_aceptada"])

            contexto = _contexto_upc(self._usuarios[actual_id])
            for dimension, clave, indice in (
                ("campus", contexto["campus"], self._campus),
                ("facultad", contexto["facultad"], self._facultades),
            ):
                if not clave or (dimension, clave) in buckets_expandidos:
                    continue
                buckets_expandidos.add((dimension, clave))
                for vecino_id in indice[clave]:
                    descubrir(actual_id, vecino_id, [f"{dimension}:{clave}"])

        resultado: dict[int, ContextoConexionGrafo] = {}
        for usuario_id in self._usuarios:
            if usuario_id == origen_id:
                continue
            grado = distancias.get(usuario_id)
            resultado[usuario_id] = {
                "grado": grado,
                "tipo": (
                    "primer_grado"
                    if grado == 1
                    else "segundo_grado"
                    if grado == 2
                    else "fuera_de_red"
                ),
                "via": vias.get(usuario_id, []),
                "intermediario_id": intermediarios.get(usuario_id),
                "evaluable": bool(
                    self._tiene_senales.get(origen_id)
                    and self._tiene_senales.get(usuario_id)
                ),
            }
        return resultado


class MaxHeapAfinidad:
    """Cola de prioridad que extrae primero la mayor afinidad."""

    def __init__(self, resultados: Iterable[dict[str, object]]) -> None:
        self._items = [self._entrada(resultado, indice) for indice, resultado in enumerate(resultados)]
        heapify(self._items)

    @staticmethod
    def _entrada(
        resultado: dict[str, object], indice: int
    ) -> tuple[float, str, int, int, dict[str, object]]:
        usuario = resultado["usuario"]
        return (
            -cast(float, resultado["score"]),
            normalizar_texto(getattr(usuario, "nombre", "")),
            int(getattr(usuario, "id", 0) or 0),
            indice,
            resultado,
        )

    def extraer_maximo(self) -> dict[str, object]:
        if not self._items:
            raise IndexError("El max-heap está vacío")
        return heappop(self._items)[-1]

    def __bool__(self) -> bool:
        return bool(self._items)

    def __len__(self) -> int:
        return len(self._items)


def normalizar_texto(valor: object | None) -> str:
    """Normaliza texto para comparar sin depender de tildes o mayusculas."""
    texto = normalize("NFKD", str(valor or "").strip().casefold())
    return "".join(caracter for caracter in texto if category(caracter) != "Mn")


def _valor_enum(valor: object | None) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, Enum):
        return str(valor.value)
    return str(valor)


def _etiqueta_enum(valor: object | None) -> str | None:
    if valor is None:
        return None
    return str(getattr(valor, "etiqueta", _valor_enum(valor)))


def _clave_curso(curso: CursoCompatible) -> str:
    return f"id:{curso.id}" if curso.id is not None else f"codigo:{normalizar_texto(curso.codigo)}"


def _a_minutos(valor: str) -> int:
    partes = (valor or "").split(":")
    if len(partes) != 2:
        raise ValueError("La hora debe usar el formato HH:MM")
    horas, minutos = map(int, partes)
    if not 0 <= horas <= 23 or not 0 <= minutos <= 59:
        raise ValueError("Hora fuera del rango permitido")
    return horas * 60 + minutos


def _intervalos_por_dia(
    horarios: Iterable[HorarioCompatible],
) -> dict[str, list[tuple[int, int]]]:
    """Agrupa y fusiona bloques solapados en O(n log n)."""
    por_dia: defaultdict[str, list[tuple[int, int]]] = defaultdict(list)
    for horario in horarios:
        try:
            inicio = _a_minutos(horario.hora_inicio)
            fin = _a_minutos(horario.hora_fin)
        except (AttributeError, TypeError, ValueError):
            continue
        if inicio < fin and horario.dia:
            por_dia[normalizar_texto(horario.dia)].append((inicio, fin))

    fusionados: dict[str, list[tuple[int, int]]] = {}
    for dia, intervalos in por_dia.items():
        resultado: list[tuple[int, int]] = []
        for inicio, fin in sorted(intervalos):
            if resultado and inicio <= resultado[-1][1]:
                resultado[-1] = (resultado[-1][0], max(resultado[-1][1], fin))
            else:
                resultado.append((inicio, fin))
        fusionados[dia] = resultado
    return fusionados


def minutos_compartidos(
    horarios_a: Iterable[HorarioCompatible], horarios_b: Iterable[HorarioCompatible]
) -> int:
    """Calcula interseccion real con fusion y dos punteros O(n + m)."""
    return _minutos_entre_intervalos(
        _intervalos_por_dia(horarios_a), _intervalos_por_dia(horarios_b)
    )


def _minutos_entre_intervalos(
    dias_a: Mapping[str, Sequence[tuple[int, int]]],
    dias_b: Mapping[str, Sequence[tuple[int, int]]],
) -> int:
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


def _contexto_upc(usuario: UsuarioCompatible) -> ContextoUPCPreparado:
    perfil = getattr(usuario, "perfil_upc", None)
    if perfil is None:
        return {
            "campus": None,
            "campus_etiqueta": None,
            "facultad": None,
            "facultad_etiqueta": None,
            "carrera": None,
            "carrera_etiqueta": None,
            "modalidad": None,
            "objetivo": None,
            "estilo_estudio": None,
            "viernes_cultural_disponible": None,
            "acepta_intercampus": False,
            "espacio_clave": None,
            "espacio_nombre": None,
        }
    espacio = getattr(perfil, "espacio_preferido", None)
    carrera = getattr(perfil, "carrera_upc", None)
    return {
        "campus": _valor_enum(getattr(perfil, "campus", None)),
        "campus_etiqueta": _etiqueta_enum(getattr(perfil, "campus", None)),
        "facultad": _valor_enum(getattr(perfil, "facultad", None)),
        "facultad_etiqueta": _etiqueta_enum(getattr(perfil, "facultad", None)),
        "carrera": getattr(carrera, "clave", None),
        "carrera_etiqueta": getattr(carrera, "nombre", None),
        "modalidad": _valor_enum(getattr(perfil, "modalidad", None)),
        "objetivo": _valor_enum(getattr(perfil, "objetivo", None)),
        "estilo_estudio": _valor_enum(getattr(perfil, "estilo_estudio", None)),
        "viernes_cultural_disponible": getattr(
            perfil, "viernes_cultural_disponible", None
        ),
        "acepta_intercampus": bool(getattr(perfil, "acepta_intercampus", False)),
        "espacio_clave": getattr(espacio, "clave", None),
        "espacio_nombre": getattr(espacio, "nombre", None),
    }


def preparar_perfil(usuario: UsuarioCompatible) -> PerfilPreparado:
    """Precalcula todas las senales reutilizables de un candidato."""
    actividades_tipos: dict[str, str] = {}
    actividades_nombres: dict[str, str] = {}
    for participacion in getattr(usuario, "participaciones_upc", ()):
        if not bool(getattr(participacion, "activa", True)):
            continue
        tipo = getattr(participacion, "tipo", None)
        valor_tipo = _valor_enum(tipo)
        if valor_tipo:
            actividades_tipos[valor_tipo] = _etiqueta_enum(tipo) or valor_tipo
        nombre = str(getattr(participacion, "nombre", "")).strip()
        if nombre:
            actividades_nombres[normalizar_texto(nombre)] = nombre

    metas: dict[str, MetaCursoPreparada] = {}
    for meta in getattr(usuario, "metas_curso", ()):
        curso_id = getattr(meta, "curso_id", None)
        clave = (
            f"id:{curso_id}"
            if curso_id is not None
            else _clave_curso(curso)
            if (curso := getattr(meta, "curso", None)) is not None
            else ""
        )
        if clave:
            metas[clave] = {
                "rol": _valor_enum(getattr(meta, "rol", None)) or "practicar",
                "prioridad": int(getattr(meta, "prioridad", 3)),
                "busca_equipo": bool(getattr(meta, "busca_equipo", True)),
            }

    cursos = {_clave_curso(curso): curso for curso in usuario.cursos}
    intereses = {
        normalizar_texto(valor): valor for valor in usuario.lista_intereses
    }
    intereses_categorias: dict[str, str] = {}
    for interes in getattr(usuario, "intereses_catalogados", ()):
        clave = normalizar_texto(getattr(interes, "etiqueta", ""))
        clave_catalogo = normalizar_texto(getattr(interes, "clave", ""))
        if clave and clave_catalogo in intereses and clave_catalogo != clave:
            valor = intereses.pop(clave_catalogo)
            intereses.setdefault(clave, valor)
        categoria = _valor_enum(getattr(interes, "categoria", None))
        if clave in intereses and categoria:
            intereses_categorias[clave] = categoria
    contexto_upc = _contexto_upc(usuario)
    return {
        "cursos": cursos,
        "intereses": intereses,
        "intereses_categorias": intereses_categorias,
        "intervalos": _intervalos_por_dia(usuario.horarios),
        "carrera": normalizar_texto(
            contexto_upc["carrera_etiqueta"] or usuario.carrera
        ),
        "contexto_upc": contexto_upc,
        "actividades_tipos": actividades_tipos,
        "actividades_nombres": actividades_nombres,
        "metas_curso": metas,
        "tiene_cursos": bool(cursos),
        "tiene_horarios": bool(usuario.horarios),
        "tiene_intereses": bool(intereses),
    }


def _cursos_comunes(
    perfil_usuario: PerfilPreparado, perfil_candidato: PerfilPreparado
) -> list[CursoCompatible]:
    return [
        curso
        for clave, curso in perfil_candidato["cursos"].items()
        if clave in perfil_usuario["cursos"]
    ]


def _intereses_comunes(
    perfil_usuario: PerfilPreparado, perfil_candidato: PerfilPreparado
) -> list[str]:
    propios = perfil_usuario["intereses"]
    ajenos = perfil_candidato["intereses"]
    return [propios[clave] for clave in sorted(propios.keys() & ajenos.keys())]


def _compatibilidad_intereses(
    usuario: PerfilPreparado, candidato: PerfilPreparado
) -> tuple[float, dict[str, object]] | None:
    """Combina Jaccard exacto (80 %) y proximidad de categorías (20 %)."""
    propios = usuario["intereses"]
    ajenos = candidato["intereses"]
    if not propios or not ajenos:
        return None

    claves_propias = set(propios)
    claves_ajenas = set(ajenos)
    comunes = claves_propias & claves_ajenas
    union = claves_propias | claves_ajenas
    jaccard_exacto = len(comunes) / len(union) if union else 0.0

    categorias_propias = set(usuario["intereses_categorias"].values())
    categorias_ajenas = set(candidato["intereses_categorias"].values())
    categorias_union = categorias_propias | categorias_ajenas
    jaccard_categorias = (
        len(categorias_propias & categorias_ajenas) / len(categorias_union)
        if categorias_union
        else 0.0
    )
    valor = _limitar(jaccard_exacto * 0.80 + jaccard_categorias * 0.20)

    comparaciones: list[dict[str, object]] = []
    for clave in sorted(claves_propias):
        categoria = usuario["intereses_categorias"].get(clave)
        coincide_con: str | None
        if clave in claves_ajenas:
            similitud = 100
            coincide_con = ajenos[clave]
        else:
            candidatos_categoria = [
                ajenos[clave_ajena]
                for clave_ajena, categoria_ajena in candidato[
                    "intereses_categorias"
                ].items()
                if categoria and categoria == categoria_ajena
            ]
            similitud = 25 if candidatos_categoria else 0
            coincide_con = candidatos_categoria[0] if candidatos_categoria else None
        comparaciones.append(
            {
                "interes": propios[clave],
                "categoria": categoria,
                "porcentaje_similitud": similitud,
                "coincide_con": coincide_con,
            }
        )

    return valor, {
        "porcentaje_similitud": round(valor * 100, 1),
        "jaccard_exacto": round(jaccard_exacto, 4),
        "porcentaje_jaccard_exacto": round(jaccard_exacto * 100, 1),
        "jaccard_categorias": round(jaccard_categorias, 4),
        "porcentaje_jaccard_categorias": round(jaccard_categorias * 100, 1),
        "formula": "0.80 × Jaccard exacto + 0.20 × Jaccard de categorías",
        "comparaciones": comparaciones,
    }


def _componente_cursos(cantidad: int) -> float:
    if cantidad <= 0:
        return 0.0
    if cantidad == 1:
        return 0.80
    return 1.0


def _limitar(valor: float, minimo: float = 0.0, maximo: float = 1.0) -> float:
    if not isfinite(valor):
        return minimo
    return min(max(valor, minimo), maximo)


def _compatibilidad_campus(
    propio: ContextoUPCPreparado, ajeno: ContextoUPCPreparado
) -> tuple[float, dict[str, object]] | None:
    if not propio["campus"] or not ajeno["campus"]:
        return None
    mismo_campus = propio["campus"] == ajeno["campus"]
    mismo_espacio = bool(
        propio["espacio_clave"]
        and propio["espacio_clave"] == ajeno["espacio_clave"]
    )
    if mismo_campus:
        valor = 1.0 if mismo_espacio else 0.90
    elif propio["acepta_intercampus"] and ajeno["acepta_intercampus"]:
        valor = 0.70
    elif propio["acepta_intercampus"] or ajeno["acepta_intercampus"]:
        valor = 0.40
    else:
        valor = 0.05
    return valor, {
        "mismo_campus": mismo_campus,
        "mismo_espacio": mismo_espacio,
        "campus": propio["campus_etiqueta"] if mismo_campus else None,
        "espacio": propio["espacio_nombre"] if mismo_espacio else None,
    }


def _compatibilidad_academica(
    usuario: PerfilPreparado, candidato: PerfilPreparado
) -> tuple[float, str] | None:
    propio = usuario["contexto_upc"]
    ajeno = candidato["contexto_upc"]
    misma_carrera = bool(
        usuario["carrera"] and usuario["carrera"] == candidato["carrera"]
    )
    misma_facultad = bool(
        propio["facultad"] and propio["facultad"] == ajeno["facultad"]
    )
    if not (usuario["carrera"] and candidato["carrera"]) and not (
        propio["facultad"] and ajeno["facultad"]
    ):
        return None
    if misma_carrera:
        return 1.0, "misma_carrera"
    if misma_facultad:
        return 0.80, "misma_facultad"
    objetivos_creativos = {"proyectos", "networking"}
    if propio["objetivo"] in objetivos_creativos or ajeno["objetivo"] in objetivos_creativos:
        return 0.60, "interdisciplinaria"
    return 0.25, "facultades_distintas"


def _compatibilidad_estilo_objetivo(
    propio: ContextoUPCPreparado, ajeno: ContextoUPCPreparado
) -> tuple[float, dict[str, bool]] | None:
    valores: list[float] = []
    objetivo_propio = propio["objetivo"]
    objetivo_ajeno = ajeno["objetivo"]
    if objetivo_propio is not None and objetivo_ajeno is not None:
        objetivos = frozenset((objetivo_propio, objetivo_ajeno))
        if len(objetivos) == 1:
            valores.append(1.0)
        else:
            valores.append(
                {
                    frozenset(("estudiar", "proyectos")): 0.85,
                    frozenset(("networking", "vida_universitaria")): 0.90,
                    frozenset(("proyectos", "networking")): 0.80,
                    frozenset(("estudiar", "vida_universitaria")): 0.55,
                }.get(objetivos, 0.60)
            )

    estilos = {propio["estilo_estudio"], ajeno["estilo_estudio"]}
    if None not in estilos:
        if len(estilos) == 1:
            valores.append(0.90)
        elif estilos in (
            {"practico", "explicativo"},
            {"enfocado", "practico"},
        ):
            valores.append(1.0)
        else:
            valores.append(0.65)

    viernes_compartido = (
        propio["viernes_cultural_disponible"] is True
        and ajeno["viernes_cultural_disponible"] is True
    )
    if (
        propio["viernes_cultural_disponible"] is not None
        and ajeno["viernes_cultural_disponible"] is not None
    ):
        valores.append(1.0 if viernes_compartido else 0.35)
    if not valores:
        return None
    return fmean(valores), {
        "mismo_objetivo": bool(
            propio["objetivo"] and propio["objetivo"] == ajeno["objetivo"]
        ),
        "viernes_cultural": viernes_compartido,
    }


def _compatibilidad_actividades(
    usuario: PerfilPreparado, candidato: PerfilPreparado
) -> tuple[float, list[str], list[str]] | None:
    tipos_a = usuario["actividades_tipos"]
    tipos_b = candidato["actividades_tipos"]
    nombres_a = usuario["actividades_nombres"]
    nombres_b = candidato["actividades_nombres"]
    if not tipos_a or not tipos_b:
        return None
    tipos_comunes = sorted(tipos_a.keys() & tipos_b.keys())
    nombres_comunes = sorted(nombres_a.keys() & nombres_b.keys())
    union_tipos = tipos_a.keys() | tipos_b.keys()
    union_nombres = nombres_a.keys() | nombres_b.keys()
    valor_tipos = len(tipos_comunes) / len(union_tipos) if union_tipos else 0.0
    valor_nombres = len(nombres_comunes) / len(union_nombres) if union_nombres else 0.0
    valor = valor_tipos * 0.70 + valor_nombres * 0.30
    return (
        valor,
        [tipos_a[clave] for clave in tipos_comunes],
        [nombres_a[clave] for clave in nombres_comunes],
    )


def _compatibilidad_metas_curso(
    usuario: PerfilPreparado,
    candidato: PerfilPreparado,
    cursos: Sequence[CursoCompatible],
) -> tuple[float, list[str]] | None:
    roles_complementarios = {
        frozenset(("ensenar", "reforzar")): 1.0,
        frozenset(("ensenar", "practicar")): 0.90,
        frozenset(("practicar",)): 0.90,
        frozenset(("proyecto",)): 1.0,
        frozenset(("reforzar",)): 0.80,
        frozenset(("practicar", "reforzar")): 0.85,
    }
    valores: list[float] = []
    codigos: list[str] = []
    for curso in cursos:
        clave = _clave_curso(curso)
        propia = usuario["metas_curso"].get(clave)
        ajena = candidato["metas_curso"].get(clave)
        if not propia or not ajena:
            continue
        compatibilidad_rol = roles_complementarios.get(
            frozenset((propia["rol"], ajena["rol"])), 0.55
        )
        cercania_prioridad = 1 - abs(propia["prioridad"] - ajena["prioridad"]) / 4
        disposicion_equipo = 1.0 if propia["busca_equipo"] and ajena["busca_equipo"] else 0.40
        valores.append(fmean((compatibilidad_rol, cercania_prioridad, disposicion_equipo)))
        codigos.append(curso.codigo)
    if not valores:
        return None
    return fmean(valores), codigos


def _serializar_componentes(
    componentes: Sequence[ComponenteAfinidad],
) -> tuple[float, dict[str, dict[str, float]]]:
    activos = [componente for componente in componentes if componente.disponible]
    peso_total = sum(componente.peso for componente in activos)
    if not activos or peso_total <= 0:
        return 0.0, {}
    total = sum(componente.valor * componente.peso for componente in activos) / peso_total
    serializados = {
        componente.clave: {
            "valor": round(componente.valor, 4),
            "puntos": round(componente.valor * componente.peso / peso_total * 100),
            "peso": round(componente.peso / peso_total * 100),
            "porcentaje_similitud": round(componente.valor * 100, 1),
            "contribucion_porcentual": round(
                componente.valor * componente.peso / peso_total * 100, 1
            ),
            "peso_porcentual": round(componente.peso / peso_total * 100, 1),
        }
        for componente in activos
    }
    return round(_limitar(total), 4), serializados


def estimar_probabilidad_emparejamiento(
    afinidad: float, cobertura: float
) -> float | None:
    """Contrae la afinidad hacia 50 % cuando la evidencia está incompleta.

    Es una estimación heurística y explicable, no una probabilidad calibrada
    con resultados históricos. Sin ninguna señal compartida devuelve ``None``.
    """
    cobertura = _limitar(cobertura)
    if cobertura == 0:
        return None
    estimacion = PROBABILIDAD_NEUTRAL + (
        _limitar(afinidad) - PROBABILIDAD_NEUTRAL
    ) * cobertura
    return round(_limitar(estimacion), 4)


def calcular_afinidad(
    usuario: UsuarioCompatible,
    candidato: UsuarioCompatible,
    perfil_usuario: PerfilPreparado | None = None,
    perfil_candidato: PerfilPreparado | None = None,
    contexto_grafo: ContextoConexionGrafo | None = None,
) -> dict[str, object]:
    """Calcula afinidad base y activa contexto UPC solo cuando esta disponible."""
    perfil_usuario = perfil_usuario or preparar_perfil(usuario)
    perfil_candidato = perfil_candidato or preparar_perfil(candidato)
    cursos = _cursos_comunes(perfil_usuario, perfil_candidato)
    intereses = _intereses_comunes(perfil_usuario, perfil_candidato)
    compatibilidad_intereses = _compatibilidad_intereses(
        perfil_usuario, perfil_candidato
    )
    minutos = _minutos_entre_intervalos(
        perfil_usuario["intervalos"], perfil_candidato["intervalos"]
    )

    componentes: list[ComponenteAfinidad] = [
        ComponenteAfinidad(
            "cursos",
            _componente_cursos(len(cursos)),
            PESO_CURSOS,
            perfil_usuario["tiene_cursos"] and perfil_candidato["tiene_cursos"],
        ),
        ComponenteAfinidad(
            "horarios",
            _limitar(minutos / MINUTOS_HORARIO_COMPLETO),
            PESO_HORARIOS,
            perfil_usuario["tiene_horarios"]
            and perfil_candidato["tiene_horarios"],
        ),
        ComponenteAfinidad(
            "intereses",
            compatibilidad_intereses[0] if compatibilidad_intereses else 0.0,
            PESO_INTERESES,
            compatibilidad_intereses is not None,
        ),
    ]
    razones: list[dict[str, object]] = []
    contexto_resultado: dict[str, object] = {}

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
                "titulo": (
                    f"{len(intereses)} "
                    f"{'interés' if len(intereses) == 1 else 'intereses'} "
                    f"compartido{'s' if len(intereses) != 1 else ''}"
                ),
                "detalle": ", ".join(intereses),
            }
        )

    upc_usuario = perfil_usuario["contexto_upc"]
    upc_candidato = perfil_candidato["contexto_upc"]
    campus = _compatibilidad_campus(upc_usuario, upc_candidato)
    if campus:
        valor_campus, detalle_campus = campus
        componentes.append(
            ComponenteAfinidad("campus", valor_campus, PESO_CAMPUS)
        )
        contexto_resultado["campus"] = detalle_campus
        if detalle_campus["mismo_campus"]:
            razones.append(
                {
                    "tipo": "campus",
                    "titulo": f"Coinciden en Campus {detalle_campus['campus']}",
                    "detalle": detalle_campus["espacio"]
                    or "Encuentro presencial mas simple",
                }
            )

    academica = _compatibilidad_academica(perfil_usuario, perfil_candidato)
    if academica:
        valor, tipo = academica
        componentes.append(
            ComponenteAfinidad("contexto_academico", valor, PESO_CONTEXTO_ACADEMICO)
        )
        contexto_resultado["contexto_academico"] = tipo
        if tipo in {"misma_carrera", "misma_facultad", "interdisciplinaria"}:
            etiqueta = {
                "misma_carrera": "Misma carrera",
                "misma_facultad": "Misma facultad",
                "interdisciplinaria": "Conexion interdisciplinaria",
            }[tipo]
            razones.append(
                {
                    "tipo": "contexto_academico",
                    "titulo": etiqueta,
                    "detalle": "Contexto académico compatible",
                }
            )

    estilo = _compatibilidad_estilo_objetivo(upc_usuario, upc_candidato)
    if estilo:
        valor_estilo, detalle_estilo = estilo
        componentes.append(
            ComponenteAfinidad(
                "estilo_objetivo", valor_estilo, PESO_ESTILO_OBJETIVO
            )
        )
        contexto_resultado["estilo_objetivo"] = detalle_estilo
        if detalle_estilo["viernes_cultural"]:
            razones.append(
                {
                    "tipo": "viernes_cultural",
                    "titulo": "Viernes Cultural disponible",
                    "detalle": "Ambos pueden coincidir de 1:00 p. m. a 3:00 p. m.",
                }
            )

    actividades = _compatibilidad_actividades(perfil_usuario, perfil_candidato)
    if actividades:
        valor, tipos, nombres = actividades
        componentes.append(
            ComponenteAfinidad("vida_universitaria", valor, PESO_VIDA_UNIVERSITARIA)
        )
        contexto_resultado["actividades_comunes"] = {"tipos": tipos, "nombres": nombres}
        if tipos or nombres:
            razones.append(
                {
                    "tipo": "vida_universitaria",
                    "titulo": "Vida universitaria en comun",
                    "detalle": ", ".join(nombres or tipos),
                }
            )

    metas = _compatibilidad_metas_curso(perfil_usuario, perfil_candidato, cursos)
    if metas:
        valor, codigos = metas
        componentes.append(ComponenteAfinidad("metas_curso", valor, PESO_METAS_CURSO))
        contexto_resultado["metas_curso"] = codigos
        razones.append(
            {
                "tipo": "metas_curso",
                "titulo": "Metas de estudio compatibles",
                "detalle": ", ".join(codigos),
            }
        )

    grafo_disponible = bool(contexto_grafo and contexto_grafo["evaluable"])
    if contexto_grafo is not None:
        contexto_resultado["grafo"] = contexto_grafo
    if contexto_grafo is not None and grafo_disponible:
        grado = contexto_grafo["grado"]
        valor_grafo = 1.0 if grado == 1 else 0.65 if grado == 2 else 0.0
        componentes.append(
            ComponenteAfinidad("proximidad_grafo", valor_grafo, PESO_GRAFO)
        )
        if grado in {1, 2}:
            razones.append(
                {
                    "tipo": "proximidad_grafo",
                    "titulo": (
                        "Conexión de primer grado"
                        if grado == 1
                        else "Conexión de segundo grado"
                    ),
                    "detalle": " · ".join(contexto_grafo["via"]),
                }
            )

    total, componentes_serializados = _serializar_componentes(componentes)
    peso_disponible = sum(
        componente.peso for componente in componentes if componente.disponible
    )
    peso_total_aplicable = PESO_TOTAL_POSIBLE - (
        PESO_GRAFO if not grafo_disponible else 0
    )
    cobertura = _limitar(peso_disponible / peso_total_aplicable)
    probabilidad = estimar_probabilidad_emparejamiento(total, cobertura)
    return {
        "score": total,
        "porcentaje": round(total * 100),
        "confianza": round(cobertura * 100),
        "probabilidad_emparejamiento": (
            round(probabilidad * 100, 1) if probabilidad is not None else None
        ),
        "modelo_probabilidad": {
            "nombre": "estimacion_heuristica_v1",
            "afinidad": total,
            "cobertura": round(cobertura, 4),
            "base_neutral": PROBABILIDAD_NEUTRAL,
            "formula": "0.50 + (afinidad - 0.50) × cobertura",
            "calibrada_con_datos_historicos": False,
        },
        "cursos": cursos,
        "horas": round(minutos / 60, 1),
        "minutos": minutos,
        "intereses": intereses,
        "intereses_detalle": (
            compatibilidad_intereses[1] if compatibilidad_intereses else None
        ),
        "razones": razones,
        "componentes": componentes_serializados,
        "contexto_upc": contexto_resultado,
    }


def calcular_afinidad_grupo(
    usuario: UsuarioCompatible, grupo: object, perfil_usuario: PerfilPreparado | None = None
) -> dict[str, object]:
    """Afinidad usuario-grupo, normalizada a partir de curso y horario."""
    perfil_usuario = perfil_usuario or preparar_perfil(usuario)
    curso = getattr(grupo, "curso", None)
    mismo_curso = bool(curso and _clave_curso(curso) in perfil_usuario["cursos"])

    class BloqueGrupo:
        dia = str(getattr(grupo, "dia", ""))
        hora_inicio = str(getattr(grupo, "hora_inicio", ""))
        hora_fin = str(getattr(grupo, "hora_fin", ""))

    minutos = _minutos_entre_intervalos(
        perfil_usuario["intervalos"], _intervalos_por_dia([BloqueGrupo()])
    )
    valor_curso = 1.0 if mismo_curso else 0.0
    valor_horario = _limitar(minutos / MINUTOS_HORARIO_COMPLETO)
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


def _clave_ranking(candidato: dict[str, object]) -> tuple[float, str, int]:
    usuario = candidato["usuario"]
    return (
        -cast(float, candidato["score"]),
        normalizar_texto(getattr(usuario, "nombre", "")),
        int(getattr(usuario, "id", 0) or 0),
    )


def rankear_candidatos_paginado(
    usuario: UsuarioCompatible,
    candidatos: Iterable[UsuarioCompatible],
    afinidad_minima: float = 0,
    pagina: int = 1,
    por_pagina: int = 18,
    grafo: GrafoAfinidadUPC | None = None,
) -> RankingPaginado:
    """Calcula únicamente el prefijo ordenado necesario para la página.

    Mantiene los resultados en ``O(pagina * por_pagina)`` y evita ordenar toda
    la colección cuando se consultan las primeras páginas. Cada afinidad sí se
    evalúa para conservar un total y un orden exactos.
    """
    minimo = _limitar(float(afinidad_minima) / 100)
    pagina_solicitada = max(int(pagina), 1)
    limite = max(int(por_pagina), 1)
    hasta = pagina_solicitada * limite
    perfil_usuario = preparar_perfil(usuario)
    contextos_grafo = (
        grafo.contextos_desde(usuario.id)
        if grafo is not None and usuario.id is not None
        else {}
    )
    total = 0

    def resultados_validos() -> Iterable[dict[str, object]]:
        nonlocal total
        for candidato in candidatos:
            resultado = calcular_afinidad(
                usuario,
                candidato,
                perfil_usuario=perfil_usuario,
                perfil_candidato=preparar_perfil(candidato),
                contexto_grafo=contextos_grafo.get(candidato.id)
                if candidato.id is not None
                else None,
            )
            if cast(float, resultado["score"]) < minimo:
                continue
            total += 1
            yield {"usuario": candidato, **resultado}

    mejores = nsmallest(hasta, resultados_validos(), key=_clave_ranking)
    paginas = max((total + limite - 1) // limite, 1)
    pagina_real = min(pagina_solicitada, paginas)
    inicio = (pagina_real - 1) * limite
    return {
        "items": mejores[inicio : inicio + limite],
        "pagina": pagina_real,
        "por_pagina": limite,
        "total": total,
        "paginas": paginas,
        "tiene_anterior": pagina_real > 1,
        "tiene_siguiente": pagina_real < paginas,
    }


def rankear_top_candidatos(
    usuario: UsuarioCompatible,
    candidatos: Iterable[UsuarioCompatible],
    limite: int = 10,
    afinidad_minima: float = 0,
    grafo: GrafoAfinidadUPC | None = None,
) -> list[dict[str, object]]:
    """Obtiene el Top-K exacto mediante max-heap en O(n + k log n).

    Todo ranking exacto debe evaluar al menos una vez los ``n`` candidatos. El
    heap evita ordenar los ``n`` resultados y solo extrae los ``k`` solicitados.
    """
    candidatos_lista = list(candidatos)
    limite_real = min(max(int(limite), 0), 100)
    if limite_real == 0:
        return []
    grafo = grafo or GrafoAfinidadUPC([usuario, *candidatos_lista])
    contextos_grafo = (
        grafo.contextos_desde(usuario.id) if usuario.id is not None else {}
    )
    perfil_usuario = preparar_perfil(usuario)
    minimo = _limitar(float(afinidad_minima) / 100)

    def resultados() -> Iterable[dict[str, object]]:
        for candidato in candidatos_lista:
            resultado = calcular_afinidad(
                usuario,
                candidato,
                perfil_usuario=perfil_usuario,
                perfil_candidato=preparar_perfil(candidato),
                contexto_grafo=(
                    contextos_grafo.get(candidato.id)
                    if candidato.id is not None
                    else None
                ),
            )
            if cast(float, resultado["score"]) >= minimo:
                yield {"usuario": candidato, **resultado}

    heap = MaxHeapAfinidad(resultados())
    return [heap.extraer_maximo() for _ in range(min(limite_real, len(heap)))]
