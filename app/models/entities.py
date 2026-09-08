"""Modelos de dominio de Socialite con contexto verificable de la UPC."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Final, Self, TypeVar
from unicodedata import category, normalize
from urllib.parse import urlsplit

from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

CREDITOS_EXTRAACADEMICOS_REQUERIDOS: Final[int] = 4
VIERNES_CULTURAL_INICIO: Final[str] = "13:00"
VIERNES_CULTURAL_FIN: Final[str] = "15:00"
PATRON_PERIODO_UPC: Final[re.Pattern[str]] = re.compile(r"^\d{4}-[12]$")
CICLOS_REGULARES_UPC: Final[int] = 10
CICLOS_MEDICINA_UPC: Final[int] = 14
MAX_INTERESES_USUARIO: Final[int] = 12


class EnumEtiquetado(StrEnum):
    """Enum persistible como texto y con etiqueta estable para Jinja2."""

    etiqueta: str

    def __new__(cls, valor: str, etiqueta: str) -> Self:
        miembro = str.__new__(cls, valor)
        miembro._value_ = valor
        miembro.etiqueta = etiqueta
        return miembro


class CampusUPC(EnumEtiquetado):
    MONTERRICO = ("monterrico", "Monterrico")
    VILLA = ("villa", "Villa")
    SAN_ISIDRO = ("san_isidro", "San Isidro")
    SAN_MIGUEL = ("san_miguel", "San Miguel")


class FacultadUPC(EnumEtiquetado):
    ADMINISTRACION_HOTELERIA_TURISMO = (
        "administracion_hoteleria_turismo",
        "Administración en Hotelería y Turismo",
    )
    ARQUITECTURA = ("arquitectura", "Arquitectura")
    ARTES_CONTEMPORANEAS = ("artes_contemporaneas", "Artes Contemporáneas")
    CIENCIAS_SALUD = ("ciencias_salud", "Ciencias de la Salud")
    CIENCIAS_HUMANAS = ("ciencias_humanas", "Ciencias Humanas")
    COMUNICACIONES = ("comunicaciones", "Comunicaciones")
    DERECHO = ("derecho", "Derecho")
    DISENO = ("diseno", "Diseño")
    ECONOMIA = ("economia", "Economía")
    EDUCACION = ("educacion", "Educación")
    INGENIERIA = ("ingenieria", "Ingeniería")
    NEGOCIOS = ("negocios", "Negocios")
    PSICOLOGIA = ("psicologia", "Psicología")


class ModalidadUPC(EnumEtiquetado):
    PRESENCIAL = ("presencial", "Presencial")
    SEMIPRESENCIAL = ("semipresencial", "Semipresencial")
    A_DISTANCIA = ("a_distancia", "A distancia")


class ObjetivoSocialite(EnumEtiquetado):
    ESTUDIAR = ("estudiar", "Formar un grupo de estudio")
    PROYECTOS = ("proyectos", "Crear proyectos")
    NETWORKING = ("networking", "Ampliar mi red UPC")
    VIDA_UNIVERSITARIA = ("vida_universitaria", "Vivir actividades UPC")


class EstiloEstudio(EnumEtiquetado):
    ENFOCADO = ("enfocado", "Sesión enfocada")
    COLABORATIVO = ("colaborativo", "Discusión colaborativa")
    PRACTICO = ("practico", "Resolver ejercicios")
    EXPLICATIVO = ("explicativo", "Explicar y enseñar")


class TipoActividadUPC(EnumEtiquetado):
    TALLER = ("taller", "Taller UPC")
    VOLUNTARIADO = ("voluntariado", "Voluntariado")
    GRUPO_UPC = ("grupo_upc", "Grupo UPC")
    ELENCO = ("elenco", "Elenco UPC")
    CLUB = ("club", "Club UPC")
    SELECCION_DEPORTIVA = ("seleccion_deportiva", "Selección deportiva")
    PASAPORTE_CULTURAL = (
        "pasaporte_cultural",
        "Pasaporte de Actividades Culturales",
    )
    SEMANA_UNIVERSITARIA = ("semana_universitaria", "Semana Universitaria")


class RolActividadUPC(EnumEtiquetado):
    PARTICIPANTE = ("participante", "Participante")
    COORDINADOR = ("coordinador", "Coordinador")
    SUBCOORDINADOR = ("subcoordinador", "Subcoordinador")
    REPRESENTANTE = ("representante", "Representante UPC")


class RolCursoUPC(EnumEtiquetado):
    REFORZAR = ("reforzar", "Quiero reforzar")
    PRACTICAR = ("practicar", "Quiero practicar")
    ENSENAR = ("ensenar", "Puedo enseñar")
    PROYECTO = ("proyecto", "Busco equipo de proyecto")


class TipoEspacioUPC(EnumEtiquetado):
    BIBLIOTECA = ("biblioteca", "Biblioteca / sala de lectura")
    CUBICULO = ("cubiculo", "Cubículo de biblioteca")
    ROTONDA = ("rotonda", "Rotonda")
    INTERNATIONAL_LOUNGE = ("international_lounge", "International Lounge")


class CategoriaInteresUPC(EnumEtiquetado):
    TECNOLOGIA = ("tecnologia", "Tecnología e innovación")
    ACADEMICO = ("academico", "Académicos")
    CREATIVIDAD = ("creatividad", "Arte y creatividad")
    DEPORTES = ("deportes", "Deportes y movimiento")
    COMUNIDAD = ("comunidad", "Comunidad e impacto")
    PROFESIONAL = ("profesional", "Desarrollo profesional")
    BIENESTAR = ("bienestar", "Bienestar y estilo de vida")


class MotivoReporte(EnumEtiquetado):
    ACOSO = ("acoso", "Acoso o intimidación")
    SPAM = ("spam", "Spam o publicidad")
    IDENTIDAD_FALSA = ("identidad_falsa", "Identidad falsa")
    CONTENIDO_INAPROPIADO = ("contenido_inapropiado", "Contenido inapropiado")
    CONDUCTA_PELIGROSA = ("conducta_peligrosa", "Conducta peligrosa")
    OTRO = ("otro", "Otro motivo")


class EstadoReporte(EnumEtiquetado):
    PENDIENTE = ("pendiente", "Pendiente")
    EN_REVISION = ("en_revision", "En revisión")
    RESUELTO = ("resuelto", "Resuelto")
    DESCARTADO = ("descartado", "Descartado")


class TipoNotificacion(EnumEtiquetado):
    MENSAJE = ("mensaje", "Mensaje nuevo")
    INVITACION = ("invitacion", "Invitación recibida")
    CONEXION = ("conexion", "Conexión aceptada")


@dataclass(frozen=True, slots=True)
class CampusInfo:
    codigo: CampusUPC
    nombre: str
    distrito: str
    direccion: str


CAMPUS_UPC: Final[dict[CampusUPC, CampusInfo]] = {
    CampusUPC.MONTERRICO: CampusInfo(
        CampusUPC.MONTERRICO,
        "Campus Monterrico",
        "Santiago de Surco",
        "Av. Prolongación Primavera 2390",
    ),
    CampusUPC.VILLA: CampusInfo(
        CampusUPC.VILLA,
        "Campus Villa",
        "Chorrillos",
        "Av. Alameda San Marcos, cruce con calle Amauta s/n",
    ),
    CampusUPC.SAN_ISIDRO: CampusInfo(
        CampusUPC.SAN_ISIDRO,
        "Campus San Isidro",
        "San Isidro",
        "Av. Salaverry 2255",
    ),
    CampusUPC.SAN_MIGUEL: CampusInfo(
        CampusUPC.SAN_MIGUEL,
        "Campus San Miguel",
        "San Miguel",
        "Av. La Marina 2810, esquina con Av. Rafael Escardó",
    ),
}


@dataclass(frozen=True, slots=True)
class InteresUPCInfo:
    """Opción controlada de interés para perfiles y matching."""

    clave: str
    etiqueta: str
    categoria: CategoriaInteresUPC


# Taxonomía de producto basada en ámbitos académicos y de Vida Universitaria.
# No pretende ser una clasificación institucional oficial de la UPC.
INTERESES_UPC: Final[tuple[InteresUPCInfo, ...]] = (
    InteresUPCInfo("tecnologia", "Tecnología", CategoriaInteresUPC.TECNOLOGIA),
    InteresUPCInfo("programacion", "Programación", CategoriaInteresUPC.TECNOLOGIA),
    InteresUPCInfo(
        "inteligencia-artificial",
        "Inteligencia artificial",
        CategoriaInteresUPC.TECNOLOGIA,
    ),
    InteresUPCInfo("ciencia-de-datos", "Ciencia de datos", CategoriaInteresUPC.TECNOLOGIA),
    InteresUPCInfo("ciberseguridad", "Ciberseguridad", CategoriaInteresUPC.TECNOLOGIA),
    InteresUPCInfo("robotica", "Robótica", CategoriaInteresUPC.TECNOLOGIA),
    InteresUPCInfo("videojuegos", "Videojuegos", CategoriaInteresUPC.TECNOLOGIA),
    InteresUPCInfo("innovacion", "Innovación", CategoriaInteresUPC.TECNOLOGIA),
    InteresUPCInfo("matematicas", "Matemáticas", CategoriaInteresUPC.ACADEMICO),
    InteresUPCInfo("investigacion", "Investigación", CategoriaInteresUPC.ACADEMICO),
    InteresUPCInfo("lectura", "Lectura", CategoriaInteresUPC.ACADEMICO),
    InteresUPCInfo("escritura", "Escritura", CategoriaInteresUPC.ACADEMICO),
    InteresUPCInfo("idiomas", "Idiomas", CategoriaInteresUPC.ACADEMICO),
    InteresUPCInfo("debate", "Debate", CategoriaInteresUPC.ACADEMICO),
    InteresUPCInfo("ciencias", "Ciencias", CategoriaInteresUPC.ACADEMICO),
    InteresUPCInfo("historia", "Historia", CategoriaInteresUPC.ACADEMICO),
    InteresUPCInfo("musica", "Música", CategoriaInteresUPC.CREATIVIDAD),
    InteresUPCInfo("fotografia", "Fotografía", CategoriaInteresUPC.CREATIVIDAD),
    InteresUPCInfo("cine-y-series", "Cine y series", CategoriaInteresUPC.CREATIVIDAD),
    InteresUPCInfo("diseno", "Diseño", CategoriaInteresUPC.CREATIVIDAD),
    InteresUPCInfo(
        "dibujo-e-ilustracion",
        "Dibujo e ilustración",
        CategoriaInteresUPC.CREATIVIDAD,
    ),
    InteresUPCInfo("teatro", "Teatro", CategoriaInteresUPC.CREATIVIDAD),
    InteresUPCInfo("danza", "Danza", CategoriaInteresUPC.CREATIVIDAD),
    InteresUPCInfo(
        "creacion-de-contenido",
        "Creación de contenido",
        CategoriaInteresUPC.CREATIVIDAD,
    ),
    InteresUPCInfo("deporte", "Deporte", CategoriaInteresUPC.DEPORTES),
    InteresUPCInfo("futbol", "Fútbol", CategoriaInteresUPC.DEPORTES),
    InteresUPCInfo("voley", "Vóley", CategoriaInteresUPC.DEPORTES),
    InteresUPCInfo("basquet", "Básquet", CategoriaInteresUPC.DEPORTES),
    InteresUPCInfo("running", "Running", CategoriaInteresUPC.DEPORTES),
    InteresUPCInfo("gimnasio", "Gimnasio", CategoriaInteresUPC.DEPORTES),
    InteresUPCInfo("natacion", "Natación", CategoriaInteresUPC.DEPORTES),
    InteresUPCInfo("ciclismo", "Ciclismo", CategoriaInteresUPC.DEPORTES),
    InteresUPCInfo("voluntariado", "Voluntariado", CategoriaInteresUPC.COMUNIDAD),
    InteresUPCInfo("sostenibilidad", "Sostenibilidad", CategoriaInteresUPC.COMUNIDAD),
    InteresUPCInfo("impacto-social", "Impacto social", CategoriaInteresUPC.COMUNIDAD),
    InteresUPCInfo("clubes-upc", "Clubes UPC", CategoriaInteresUPC.COMUNIDAD),
    InteresUPCInfo("grupos-upc", "Grupos UPC", CategoriaInteresUPC.COMUNIDAD),
    InteresUPCInfo("ciudadania", "Ciudadanía", CategoriaInteresUPC.COMUNIDAD),
    InteresUPCInfo("networking", "Networking", CategoriaInteresUPC.PROFESIONAL),
    InteresUPCInfo("emprendimiento", "Emprendimiento", CategoriaInteresUPC.PROFESIONAL),
    InteresUPCInfo("liderazgo", "Liderazgo", CategoriaInteresUPC.PROFESIONAL),
    InteresUPCInfo("marketing", "Marketing", CategoriaInteresUPC.PROFESIONAL),
    InteresUPCInfo("finanzas", "Finanzas", CategoriaInteresUPC.PROFESIONAL),
    InteresUPCInfo("negocios", "Negocios", CategoriaInteresUPC.PROFESIONAL),
    InteresUPCInfo("empleabilidad", "Empleabilidad", CategoriaInteresUPC.PROFESIONAL),
    InteresUPCInfo("bienestar", "Bienestar", CategoriaInteresUPC.BIENESTAR),
    InteresUPCInfo("viajes", "Viajes", CategoriaInteresUPC.BIENESTAR),
    InteresUPCInfo("gastronomia", "Gastronomía", CategoriaInteresUPC.BIENESTAR),
    InteresUPCInfo("mascotas", "Mascotas", CategoriaInteresUPC.BIENESTAR),
    InteresUPCInfo("moda", "Moda", CategoriaInteresUPC.BIENESTAR),
)


FUENTE_MALLAS_UPC: Final[str] = (
    "https://upc.edu.pe/transparencia-upc/mallas-curriculares/"
)

# Programas de pregrado con admision vigente publicados en Transparencia UPC.
# Las menciones de Musica, Traduccion, Educacion y Psicologia se mantienen como
# parte de la carrera base para no duplicar identidades academicas.
CARRERAS_POR_FACULTAD: Final[dict[FacultadUPC, tuple[str, ...]]] = {
    FacultadUPC.ADMINISTRACION_HOTELERIA_TURISMO: (
        "Hotelería y Administración",
        "Turismo y Administración",
        "Gastronomía y Gestión Culinaria",
    ),
    FacultadUPC.ARQUITECTURA: ("Arquitectura",),
    FacultadUPC.ARTES_CONTEMPORANEAS: ("Música", "Artes Escénicas"),
    FacultadUPC.CIENCIAS_SALUD: (
        "Ciencias de la Actividad Física y el Deporte",
        "Biología",
        "Enfermería",
        "Farmacia y Bioquímica",
        "Medicina",
        "Nutrición y Dietética",
        "Odontología",
        "Terapia Física",
        "Medicina Veterinaria",
    ),
    FacultadUPC.CIENCIAS_HUMANAS: ("Traducción e Interpretación",),
    FacultadUPC.COMUNICACIONES: (
        "Comunicación Audiovisual y Medios Interactivos",
        "Comunicación e Imagen Empresarial",
        "Comunicación y Marketing",
        "Comunicación y Periodismo",
        "Comunicación y Publicidad",
        "Comunicación y Fotografía",
    ),
    FacultadUPC.DERECHO: ("Derecho", "Relaciones Internacionales"),
    FacultadUPC.DISENO: (
        "Diseño Industrial",
        "Diseño Profesional de Interiores",
        "Diseño Profesional Gráfico",
        "Diseño y Gestión de Moda",
    ),
    FacultadUPC.ECONOMIA: (
        "Economía y Ciencia de Datos",
        "Economía y Finanzas",
        "Economía y Negocios Internacionales",
        "Economía Gerencial",
        "Ciencias Políticas",
    ),
    FacultadUPC.EDUCACION: ("Educación y Gestión del Aprendizaje",),
    FacultadUPC.INGENIERIA: (
        "Ciencias de la Computación",
        "Ingeniería Biomédica",
        "Ingeniería de Ciberseguridad",
        "Ingeniería Civil",
        "Ingeniería en Gestión Empresarial",
        "Ingeniería de Gestión Minera",
        "Ingeniería de Sistemas de Información",
        "Ingeniería de Software",
        "Ingeniería Electrónica",
        "Ingeniería Industrial",
        "Ingeniería Mecatrónica",
        "Ingeniería Ambiental",
    ),
    FacultadUPC.NEGOCIOS: (
        "Administración",
        "Administración y Ciencia de Datos para Negocios",
        "Administración y Agronegocios",
        "Administración y Finanzas",
        "Administración y Marketing",
        "Administración y Negocios del Deporte",
        "Administración y Negocios Digitales",
        "Administración y Negocios Internacionales",
        "Administración y Recursos Humanos",
        "Contabilidad y Administración",
        "Contabilidad y Finanzas",
        "Administración y Gerencia del Emprendimiento",
    ),
    FacultadUPC.PSICOLOGIA: ("Psicología",),
}


def slugificar(valor: str) -> str:
    texto = normalize("NFKD", valor.strip().casefold())
    sin_tildes = "".join(caracter for caracter in texto if category(caracter) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes).strip("-")


DURACION_CICLOS_POR_CARRERA: Final[dict[str, int]] = {
    "medicina": CICLOS_MEDICINA_UPC,
}

ALIAS_INTERESES_UPC: Final[dict[str, str]] = {
    "ia": "inteligencia-artificial",
    "inteligencia-artificial-ia": "inteligencia-artificial",
    "basket": "basquet",
    "basketball": "basquet",
    "voleibol": "voley",
    "programar": "programacion",
    "foto": "fotografia",
}

INTERESES_UPC_POR_CLAVE: Final[dict[str, InteresUPCInfo]] = {
    interes.clave: interes for interes in INTERESES_UPC
}


def duracion_ciclos_carrera(clave_carrera: str | None) -> int:
    """Devuelve la duración publicada; diez ciclos salvo excepciones verificadas."""
    return DURACION_CICLOS_POR_CARRERA.get(
        slugificar(clave_carrera or ""), CICLOS_REGULARES_UPC
    )


def ciclos_para_carrera(clave_carrera: str | None) -> tuple[int, ...]:
    return tuple(range(1, duracion_ciclos_carrera(clave_carrera) + 1))


def obtener_interes_upc(valor: str) -> InteresUPCInfo | None:
    clave = slugificar(valor)
    clave = ALIAS_INTERESES_UPC.get(clave, clave)
    return INTERESES_UPC_POR_CLAVE.get(clave)


def normalizar_intereses_upc(valores: Iterable[str]) -> list[str]:
    """Valida selecciones del formulario y devuelve etiquetas canónicas únicas."""
    encontrados: dict[str, InteresUPCInfo] = {}
    desconocidos: list[str] = []
    for valor in valores:
        for fragmento in str(valor).split(","):
            texto = fragmento.strip()
            if not texto:
                continue
            interes = obtener_interes_upc(texto)
            if interes is None:
                desconocidos.append(texto)
            else:
                encontrados[interes.clave] = interes
    if desconocidos:
        raise ValueError(
            "Selecciona intereses del catálogo: " + ", ".join(desconocidos[:3])
        )
    if len(encontrados) > MAX_INTERESES_USUARIO:
        raise ValueError(
            f"Puedes seleccionar hasta {MAX_INTERESES_USUARIO} intereses"
        )
    return [
        interes.etiqueta
        for interes in INTERESES_UPC
        if interes.clave in encontrados
    ]


@dataclass(frozen=True, slots=True)
class EspacioUPCSeed:
    clave: str
    campus: CampusUPC
    nombre: str
    tipo: TipoEspacioUPC
    pabellon: str | None
    piso: str | None
    aforo_minimo: int | None
    aforo_maximo: int | None
    requiere_reserva: bool
    max_minutos_diarios: int | None
    fuente_url: str
    verificado_en: date


FUENTE_BIBLIOTECAS: Final[str] = (
    "https://www.upc.edu.pe/servicios/contacto-para-alumnos-upc/horarios-de-atencion/"
)
FUENTE_CUBICULOS: Final[str] = (
    "https://explora.upc.edu.pe/es_ES/reserva-de-cub%C3%ADculos-y-computadoras"
)
FUENTE_SERVICIOS_BIBLIOTECA: Final[str] = (
    "https://explora.upc.edu.pe/es_ES/79939-biblioteca"
)
FUENTE_ROTONDA_MONTERRICO: Final[str] = (
    "https://noticias.upc.edu.pe/2026/04/13/noticias-feria-internacional-upc-2026/"
)


ESPACIOS_UPC_OFICIALES: Final[tuple[EspacioUPCSeed, ...]] = (
    EspacioUPCSeed(
        "biblioteca-monterrico", CampusUPC.MONTERRICO, "Biblioteca Monterrico",
        TipoEspacioUPC.BIBLIOTECA, "I y L", None, None, None, False, None,
        FUENTE_BIBLIOTECAS, date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "biblioteca-villa", CampusUPC.VILLA, "Biblioteca Villa",
        TipoEspacioUPC.BIBLIOTECA, "D e I", None, None, None, False, None,
        FUENTE_BIBLIOTECAS, date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "biblioteca-san-isidro", CampusUPC.SAN_ISIDRO, "Biblioteca San Isidro",
        TipoEspacioUPC.BIBLIOTECA, "A y B", None, None, None, False, None,
        FUENTE_BIBLIOTECAS, date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "biblioteca-san-miguel", CampusUPC.SAN_MIGUEL, "Biblioteca San Miguel",
        TipoEspacioUPC.BIBLIOTECA, "A y D", None, None, None, False, None,
        FUENTE_BIBLIOTECAS, date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "cubiculos-monterrico-i", CampusUPC.MONTERRICO,
        "Cubículos - Biblioteca Pabellón I", TipoEspacioUPC.CUBICULO,
        "I", "3, 6 y 7", 2, 5, True, 120, FUENTE_CUBICULOS, date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "cubiculos-monterrico-l", CampusUPC.MONTERRICO,
        "Cubículos - Biblioteca Pabellón L", TipoEspacioUPC.CUBICULO,
        "L", "4", 2, 6, True, 120, FUENTE_CUBICULOS, date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "cubiculos-villa-d", CampusUPC.VILLA,
        "Cubículos - Biblioteca Pabellón D", TipoEspacioUPC.CUBICULO,
        "D", "3", 2, 5, True, 120, FUENTE_CUBICULOS, date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "cubiculos-san-miguel-a", CampusUPC.SAN_MIGUEL,
        "Cubículos - Biblioteca Pabellón A", TipoEspacioUPC.CUBICULO,
        "A", "2 y 3", 2, 6, True, 120, FUENTE_CUBICULOS, date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "cubiculos-san-miguel-d", CampusUPC.SAN_MIGUEL,
        "Cubículos - Biblioteca Pabellón D", TipoEspacioUPC.CUBICULO,
        "D", "2", 2, 6, True, 120, FUENTE_CUBICULOS, date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "cubiculos-san-isidro-a", CampusUPC.SAN_ISIDRO,
        "Cubículos - Biblioteca Pabellón A", TipoEspacioUPC.CUBICULO,
        "A", "3", 2, 4, True, 120, FUENTE_CUBICULOS, date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "cubiculos-san-isidro-b", CampusUPC.SAN_ISIDRO,
        "Cubículos - Biblioteca Pabellón B", TipoEspacioUPC.CUBICULO,
        "B", "1 y 2", 2, 7, True, 120, FUENTE_CUBICULOS, date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "international-lounge-monterrico", CampusUPC.MONTERRICO,
        "International Lounge", TipoEspacioUPC.INTERNATIONAL_LOUNGE,
        None, None, None, None, False, None, FUENTE_SERVICIOS_BIBLIOTECA,
        date(2026, 9, 2),
    ),
    EspacioUPCSeed(
        "rotonda-monterrico", CampusUPC.MONTERRICO,
        "Rotonda del Campus Monterrico", TipoEspacioUPC.ROTONDA,
        None, None, None, None, False, None, FUENTE_ROTONDA_MONTERRICO,
        date(2026, 9, 2),
    ),
)


EnumT = TypeVar("EnumT", bound=EnumEtiquetado)


def convertir_enum(tipo: type[EnumT], valor: object | None) -> EnumT | None:
    """Convierte valores de formularios/JSON a enums de dominio validados."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, tipo):
        return valor
    try:
        return tipo(str(valor))
    except ValueError as error:
        permitidos = ", ".join(miembro.value for miembro in tipo)
        raise ValueError(f"Valor invalido. Opciones: {permitidos}") from error


def _tipo_enum(tipo: type[EnumT], nombre: str):
    return db.Enum(
        tipo,
        name=nombre,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda miembros: [miembro.value for miembro in miembros],
    )


inscripciones = db.Table(
    "inscripciones",
    db.Column("usuario_id", db.Integer, db.ForeignKey("usuarios.id"), primary_key=True),
    db.Column("curso_id", db.Integer, db.ForeignKey("cursos.id"), primary_key=True),
)


miembros_grupo = db.Table(
    "miembros_grupo",
    db.Column("usuario_id", db.Integer, db.ForeignKey("usuarios.id"), primary_key=True),
    db.Column("grupo_id", db.Integer, db.ForeignKey("grupos.id"), primary_key=True),
)


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False)
    correo_institucional = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    foto_archivo = db.Column(db.String(500))
    biografia = db.Column(db.String(220))
    carrera = db.Column(db.String(80))
    ciclo = db.Column(db.Integer)
    intereses = db.Column(db.String(300))
    correo_verificado_en = db.Column(db.DateTime, index=True)
    verificacion_codigo_hash = db.Column(db.String(64))
    verificacion_expira_en = db.Column(db.DateTime)
    verificacion_enviada_en = db.Column(db.DateTime)
    verificacion_intentos = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    cursos = db.relationship("Curso", secondary=inscripciones, back_populates="usuarios")
    solicitudes_enviadas = db.relationship(
        "Conexion", foreign_keys="Conexion.remitente_id", back_populates="remitente",
        cascade="all, delete-orphan",
    )
    solicitudes_recibidas = db.relationship(
        "Conexion", foreign_keys="Conexion.destinatario_id", back_populates="destinatario",
        cascade="all, delete-orphan",
    )
    bloqueos_emitidos = db.relationship(
        "Bloqueo",
        foreign_keys="Bloqueo.bloqueador_id",
        back_populates="bloqueador",
        cascade="all, delete-orphan",
    )
    bloqueos_recibidos = db.relationship(
        "Bloqueo",
        foreign_keys="Bloqueo.bloqueado_id",
        back_populates="bloqueado",
        cascade="all, delete-orphan",
    )
    reportes_emitidos = db.relationship(
        "Reporte",
        foreign_keys="Reporte.denunciante_id",
        back_populates="denunciante",
        cascade="all, delete-orphan",
    )
    reportes_recibidos = db.relationship(
        "Reporte",
        foreign_keys="Reporte.reportado_id",
        back_populates="reportado",
    )
    mensajes_enviados = db.relationship(
        "Mensaje",
        foreign_keys="Mensaje.emisor_id",
        back_populates="emisor",
        cascade="all, delete-orphan",
    )
    mensajes_recibidos = db.relationship(
        "Mensaje",
        foreign_keys="Mensaje.receptor_id",
        back_populates="receptor",
        cascade="all, delete-orphan",
    )
    notificaciones = db.relationship(
        "Notificacion",
        foreign_keys="Notificacion.usuario_id",
        back_populates="usuario",
        cascade="all, delete-orphan",
    )
    notificaciones_originadas = db.relationship(
        "Notificacion",
        foreign_keys="Notificacion.actor_id",
        back_populates="actor",
    )
    perfil_upc = db.relationship(
        "PerfilUPC", back_populates="usuario", uselist=False,
        cascade="all, delete-orphan", single_parent=True,
    )
    participaciones_upc = db.relationship(
        "ParticipacionUPC", back_populates="usuario", cascade="all, delete-orphan",
        order_by="ParticipacionUPC.periodo.desc(), ParticipacionUPC.id.desc()",
    )
    metas_curso = db.relationship(
        "MetaCursoUPC", back_populates="usuario", cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def correo_verificado(self) -> bool:
        return self.correo_verificado_en is not None

    @validates("biografia")
    def validar_biografia(self, _clave: str, valor: str | None) -> str | None:
        if valor is None:
            return None
        limpio = valor.strip()
        if len(limpio) > 220:
            raise ValueError("La presentación puede tener hasta 220 caracteres")
        return limpio or None

    @validates("foto_archivo")
    def validar_foto_archivo(self, _clave: str, valor: str | None) -> str | None:
        if valor is None:
            return None
        limpio = valor.strip()
        legado = re.fullmatch(r"[A-Za-z0-9_-]{24,80}\.jpg", limpio)
        parsed = urlsplit(limpio)
        remoto = (
            len(limpio) <= 500
            and parsed.scheme == "https"
            and bool(parsed.netloc)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path.endswith(".jpg")
            and not any(caracter.isspace() for caracter in limpio)
        )
        if not legado and not remoto:
            raise ValueError("La referencia del avatar no es válida")
        return limpio

    @property
    def lista_intereses(self) -> list[str]:
        return [item.strip() for item in (self.intereses or "").split(",") if item.strip()]

    @property
    def intereses_catalogados(self) -> list[InteresUPCInfo]:
        """Resuelve intereses legados y nuevos contra la taxonomía vigente."""
        resultado: list[InteresUPCInfo] = []
        vistos: set[str] = set()
        for valor in self.lista_intereses:
            interes = obtener_interes_upc(valor)
            if interes is not None and interes.clave not in vistos:
                vistos.add(interes.clave)
                resultado.append(interes)
        return resultado

    @property
    def iniciales(self) -> str:
        partes = self.nombre.strip().split()
        return "".join(parte[0] for parte in partes[:2]).upper()

    @property
    def foto_url(self) -> str | None:
        if not self.foto_archivo:
            return None
        if urlsplit(self.foto_archivo).scheme == "https":
            return self.foto_archivo
        return f"/media/avatares/{self.foto_archivo}"

    @property
    def creditos_extraacademicos_confirmados(self) -> int:
        return sum(item.creditos_confirmados for item in self.participaciones_upc)

    @property
    def creditos_extraacademicos_pendientes(self) -> int:
        return max(
            CREDITOS_EXTRAACADEMICOS_REQUERIDOS - self.creditos_extraacademicos_confirmados,
            0,
        )

    @property
    def perfil_completo(self) -> int:
        secciones = (
            bool(self.foto_archivo), bool(self.biografia),
            bool(self.carrera and self.ciclo), bool(self.lista_intereses),
            bool(self.cursos), bool(self.horarios),
            bool(self.perfil_upc and self.perfil_upc.campus),
        )
        return round(sum(secciones) / len(secciones) * 100)


class Curso(db.Model):
    __tablename__ = "cursos"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    usuarios = db.relationship("Usuario", secondary=inscripciones, back_populates="cursos")
    metas_estudiantes = db.relationship(
        "MetaCursoUPC", back_populates="curso", cascade="all, delete-orphan"
    )


class Horario(db.Model):
    __tablename__ = "horarios"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    dia = db.Column(db.String(20), nullable=False)
    hora_inicio = db.Column(db.String(5), nullable=False)
    hora_fin = db.Column(db.String(5), nullable=False)
    usuario = db.relationship(
        "Usuario", backref=db.backref("horarios", cascade="all, delete-orphan")
    )


class EspacioUPC(db.Model):
    __tablename__ = "espacios_upc"
    __table_args__ = (
        db.CheckConstraint(
            "aforo_minimo IS NULL OR aforo_minimo >= 1", name="ck_espacio_aforo_minimo"
        ),
        db.CheckConstraint(
            "aforo_maximo IS NULL OR aforo_maximo >= aforo_minimo",
            name="ck_espacio_aforo_coherente",
        ),
        db.CheckConstraint(
            "max_minutos_diarios IS NULL OR max_minutos_diarios > 0",
            name="ck_espacio_tiempo_positivo",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(80), unique=True, nullable=False, index=True)
    campus = db.Column(_tipo_enum(CampusUPC, "campus_espacio_upc"), nullable=False, index=True)
    nombre = db.Column(db.String(140), nullable=False)
    tipo = db.Column(_tipo_enum(TipoEspacioUPC, "tipo_espacio_upc"), nullable=False)
    pabellon = db.Column(db.String(30))
    piso = db.Column(db.String(30))
    aforo_minimo = db.Column(db.Integer)
    aforo_maximo = db.Column(db.Integer)
    requiere_reserva = db.Column(db.Boolean, nullable=False, default=False)
    max_minutos_diarios = db.Column(db.Integer)
    fuente_url = db.Column(db.String(500), nullable=False)
    verificado_en = db.Column(db.Date, nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True, index=True)

    perfiles_preferentes = db.relationship("PerfilUPC", back_populates="espacio_preferido")


class CarreraUPC(db.Model):
    __tablename__ = "carreras_upc"

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(100), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(140), unique=True, nullable=False)
    facultad = db.Column(
        _tipo_enum(FacultadUPC, "facultad_carrera_upc"), nullable=False, index=True
    )
    fuente_url = db.Column(db.String(500), nullable=False)
    verificado_en = db.Column(db.Date, nullable=False)
    activa = db.Column(db.Boolean, nullable=False, default=True, index=True)

    perfiles = db.relationship("PerfilUPC", back_populates="carrera_upc")


class PerfilUPC(db.Model):
    __tablename__ = "perfiles_upc"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), unique=True, nullable=False, index=True
    )
    campus = db.Column(_tipo_enum(CampusUPC, "campus_perfil_upc"), nullable=False, index=True)
    facultad = db.Column(_tipo_enum(FacultadUPC, "facultad_perfil_upc"), index=True)
    carrera_upc_id = db.Column(db.Integer, db.ForeignKey("carreras_upc.id"), index=True)
    modalidad = db.Column(_tipo_enum(ModalidadUPC, "modalidad_perfil_upc"))
    objetivo = db.Column(_tipo_enum(ObjetivoSocialite, "objetivo_socialite"))
    estilo_estudio = db.Column(_tipo_enum(EstiloEstudio, "estilo_estudio_upc"))
    viernes_cultural_disponible = db.Column(db.Boolean)
    acepta_intercampus = db.Column(db.Boolean, nullable=False, default=False)
    espacio_preferido_id = db.Column(db.Integer, db.ForeignKey("espacios_upc.id"))
    actualizado_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    usuario = db.relationship("Usuario", back_populates="perfil_upc")
    carrera_upc = db.relationship(
        "CarreraUPC", back_populates="perfiles", lazy="joined"
    )
    espacio_preferido = db.relationship("EspacioUPC", back_populates="perfiles_preferentes")

    def validar_coherencia(self) -> None:
        if self.carrera_upc and self.facultad and self.carrera_upc.facultad != self.facultad:
            raise ValueError("La carrera seleccionada no pertenece a la facultad indicada")
        if self.espacio_preferido and self.espacio_preferido.campus != self.campus:
            raise ValueError("El espacio preferido debe pertenecer al campus seleccionado")


class ParticipacionUPC(db.Model):
    __tablename__ = "participaciones_upc"
    __table_args__ = (
        db.CheckConstraint(
            "creditos_confirmados BETWEEN 0 AND 4", name="ck_participacion_creditos"
        ),
        db.UniqueConstraint(
            "usuario_id", "tipo", "nombre", "periodo",
            name="uq_participacion_usuario_periodo",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo = db.Column(_tipo_enum(TipoActividadUPC, "tipo_actividad_upc"), nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    rol = db.Column(
        _tipo_enum(RolActividadUPC, "rol_actividad_upc"), nullable=False,
        default=RolActividadUPC.PARTICIPANTE,
    )
    campus = db.Column(_tipo_enum(CampusUPC, "campus_actividad_upc"), index=True)
    periodo = db.Column(db.String(6), nullable=False, index=True)
    creditos_confirmados = db.Column(db.Integer, nullable=False, default=0)
    activa = db.Column(db.Boolean, nullable=False, default=True, index=True)
    creada_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    usuario = db.relationship("Usuario", back_populates="participaciones_upc")

    @validates("nombre")
    def validar_nombre(self, _clave: str, valor: str) -> str:
        nombre = (valor or "").strip()
        if not 2 <= len(nombre) <= 120:
            raise ValueError("El nombre de la actividad debe tener entre 2 y 120 caracteres")
        return nombre

    @validates("periodo")
    def validar_periodo(self, _clave: str, valor: str) -> str:
        periodo = (valor or "").strip()
        if not PATRON_PERIODO_UPC.fullmatch(periodo):
            raise ValueError("El periodo UPC debe usar el formato AAAA-1 o AAAA-2")
        return periodo

    @validates("creditos_confirmados")
    def validar_creditos(self, _clave: str, valor: int) -> int:
        creditos = int(valor)
        if not 0 <= creditos <= 4:
            raise ValueError("Los creditos confirmados deben estar entre 0 y 4")
        return creditos


class MetaCursoUPC(db.Model):
    """Necesidad declarada por un alumno; evita inventar cursos 'filtro'."""

    __tablename__ = "metas_curso_upc"
    __table_args__ = (
        db.CheckConstraint("prioridad BETWEEN 1 AND 5", name="ck_meta_curso_prioridad"),
        db.CheckConstraint("intento BETWEEN 1 AND 3", name="ck_meta_curso_intento"),
        db.UniqueConstraint("usuario_id", "curso_id", name="uq_meta_curso_usuario"),
    )

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    curso_id = db.Column(db.Integer, db.ForeignKey("cursos.id"), nullable=False, index=True)
    rol = db.Column(_tipo_enum(RolCursoUPC, "rol_curso_upc"), nullable=False)
    prioridad = db.Column(db.Integer, nullable=False, default=3)
    intento = db.Column(db.Integer, nullable=False, default=1)
    busca_equipo = db.Column(db.Boolean, nullable=False, default=True)
    actualizado_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    usuario = db.relationship("Usuario", back_populates="metas_curso")
    curso = db.relationship("Curso", back_populates="metas_estudiantes")

    @validates("prioridad")
    def validar_prioridad(self, _clave: str, valor: int) -> int:
        prioridad = int(valor)
        if not 1 <= prioridad <= 5:
            raise ValueError("La prioridad debe estar entre 1 y 5")
        return prioridad

    @validates("intento")
    def validar_intento(self, _clave: str, valor: int) -> int:
        intento = int(valor)
        if not 1 <= intento <= 3:
            raise ValueError("El intento debe estar entre 1 y 3")
        return intento


class Grupo(db.Model):
    __tablename__ = "grupos"

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)
    curso_id = db.Column(db.Integer, db.ForeignKey("cursos.id"), nullable=True)
    creador_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    lugar = db.Column(db.String(120), nullable=False)
    dia = db.Column(db.String(20), nullable=False)
    hora_inicio = db.Column(db.String(5), nullable=False)
    hora_fin = db.Column(db.String(5), nullable=False)
    max_miembros = db.Column(db.Integer, nullable=False, default=6)
    creado_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    curso = db.relationship("Curso", backref="grupos")
    creador = db.relationship("Usuario", foreign_keys=[creador_id], backref="grupos_creados")
    miembros = db.relationship(
        "Usuario", secondary=miembros_grupo, backref="grupos", lazy="selectin"
    )

    @property
    def esta_lleno(self) -> bool:
        return len(self.miembros) >= self.max_miembros

    @property
    def cupos_disponibles(self) -> int:
        return max(self.max_miembros - len(self.miembros), 0)


class Conexion(db.Model):
    __tablename__ = "conexiones"
    __table_args__ = (
        db.UniqueConstraint("remitente_id", "destinatario_id", name="uq_conexion_directa"),
        db.CheckConstraint("remitente_id != destinatario_id", name="ck_conexion_usuarios_distintos"),
        db.CheckConstraint(
            "(plan_tipo IS NULL AND plan_tema IS NULL) OR "
            "(plan_tipo IS NOT NULL AND plan_tipo IN ('estudio', 'proyecto', 'social') "
            "AND plan_tema IS NOT NULL AND length(trim(plan_tema)) BETWEEN 1 AND 120)",
            name="ck_conexion_plan",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    remitente_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    destinatario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    estado = db.Column(db.String(20), nullable=False, default="pendiente", index=True)
    plan_tipo = db.Column(db.String(16), nullable=True)
    plan_tema = db.Column(db.String(120), nullable=True)
    creada_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    actualizada_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    remitente = db.relationship(
        "Usuario", foreign_keys=[remitente_id], back_populates="solicitudes_enviadas"
    )
    destinatario = db.relationship(
        "Usuario", foreign_keys=[destinatario_id], back_populates="solicitudes_recibidas"
    )

    def involucra(self, usuario: Usuario) -> bool:
        return usuario.id in (self.remitente_id, self.destinatario_id)

    def otra_persona(self, usuario: Usuario) -> Usuario:
        return self.destinatario if self.remitente_id == usuario.id else self.remitente


class Bloqueo(db.Model):
    """Corta de inmediato toda interacción entre dos cuentas."""

    __tablename__ = "bloqueos"
    __table_args__ = (
        db.UniqueConstraint("bloqueador_id", "bloqueado_id", name="uq_bloqueo_directo"),
        db.CheckConstraint(
            "bloqueador_id != bloqueado_id", name="ck_bloqueo_usuarios_distintos"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    bloqueador_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    bloqueado_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    creado_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    bloqueador = db.relationship(
        "Usuario", foreign_keys=[bloqueador_id], back_populates="bloqueos_emitidos"
    )
    bloqueado = db.relationship(
        "Usuario", foreign_keys=[bloqueado_id], back_populates="bloqueos_recibidos"
    )


class Mensaje(db.Model):
    """Mensaje privado e inmutable entre dos conexiones aceptadas."""

    __tablename__ = "mensajes"
    __table_args__ = (
        db.CheckConstraint("emisor_id != receptor_id", name="ck_mensaje_usuarios_distintos"),
        db.CheckConstraint(
            "length(texto) BETWEEN 1 AND 2000", name="ck_mensaje_texto_longitud"
        ),
        db.Index(
            "ix_mensajes_emisor_receptor_fecha",
            "emisor_id",
            "receptor_id",
            "enviado_en",
        ),
        db.Index(
            "ix_mensajes_receptor_leido_fecha",
            "receptor_id",
            "leido",
            "enviado_en",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    emisor_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    receptor_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    texto = db.Column(db.Text, nullable=False)
    enviado_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    leido = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    leido_en = db.Column(db.DateTime(timezone=True))

    emisor = db.relationship(
        "Usuario", foreign_keys=[emisor_id], back_populates="mensajes_enviados"
    )
    receptor = db.relationship(
        "Usuario", foreign_keys=[receptor_id], back_populates="mensajes_recibidos"
    )
    notificacion = db.relationship(
        "Notificacion",
        back_populates="mensaje",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )

    @validates("texto")
    def validar_texto(self, _clave: str, valor: str) -> str:
        limpio = (valor or "").strip()
        if not 1 <= len(limpio) <= 2000:
            raise ValueError("El mensaje debe tener entre 1 y 2000 caracteres")
        return limpio

    def involucra(self, usuario_id: int) -> bool:
        return usuario_id in (self.emisor_id, self.receptor_id)


class Notificacion(db.Model):
    """Alerta persistente para una bandeja in-app auditable."""

    __tablename__ = "notificaciones"
    __table_args__ = (
        db.CheckConstraint(
            "actor_id IS NULL OR actor_id != usuario_id",
            name="ck_notificacion_actor_distinto",
        ),
        db.Index(
            "ix_notificaciones_usuario_leida_fecha",
            "usuario_id",
            "leida",
            "creada_en",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    actor_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=True, index=True
    )
    mensaje_id = db.Column(
        db.Integer, db.ForeignKey("mensajes.id"), unique=True, nullable=True
    )
    tipo = db.Column(
        _tipo_enum(TipoNotificacion, "tipo_notificacion"),
        nullable=False,
        index=True,
    )
    titulo = db.Column(db.String(120), nullable=False)
    contenido = db.Column(db.String(200))
    destino_url = db.Column(db.String(300), nullable=False)
    leida = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    creada_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    leida_en = db.Column(db.DateTime(timezone=True))

    usuario = db.relationship(
        "Usuario", foreign_keys=[usuario_id], back_populates="notificaciones"
    )
    actor = db.relationship(
        "Usuario", foreign_keys=[actor_id], back_populates="notificaciones_originadas"
    )
    mensaje = db.relationship("Mensaje", back_populates="notificacion")

    def marcar_leida(self) -> bool:
        if self.leida:
            return False
        self.leida = True
        self.leida_en = datetime.now(UTC)
        return True


class Reporte(db.Model):
    """Denuncia privada para revisión; nunca se expone al usuario reportado."""

    __tablename__ = "reportes"
    __table_args__ = (
        db.CheckConstraint(
            "denunciante_id != reportado_id", name="ck_reporte_usuarios_distintos"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    denunciante_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    reportado_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    motivo = db.Column(
        _tipo_enum(MotivoReporte, "motivo_reporte"), nullable=False, index=True
    )
    detalle = db.Column(db.String(500))
    estado = db.Column(
        _tipo_enum(EstadoReporte, "estado_reporte"),
        nullable=False,
        default=EstadoReporte.PENDIENTE,
        index=True,
    )
    creado_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    denunciante = db.relationship(
        "Usuario", foreign_keys=[denunciante_id], back_populates="reportes_emitidos"
    )
    reportado = db.relationship(
        "Usuario", foreign_keys=[reportado_id], back_populates="reportes_recibidos"
    )

    @validates("detalle")
    def validar_detalle(self, _clave: str, valor: str | None) -> str | None:
        if valor is None:
            return None
        limpio = valor.strip()
        if len(limpio) > 500:
            raise ValueError("El detalle del reporte puede tener hasta 500 caracteres")
        return limpio or None


def sincronizar_catalogo_upc() -> int:
    """Crea o refresca el catálogo oficial y conserva obsoletos como inactivos."""
    creados = 0
    claves_espacios = {dato.clave for dato in ESPACIOS_UPC_OFICIALES}
    EspacioUPC.query.filter(EspacioUPC.clave.notin_(claves_espacios)).update(
        {EspacioUPC.activo: False}, synchronize_session=False
    )
    for dato in ESPACIOS_UPC_OFICIALES:
        espacio = EspacioUPC.query.filter_by(clave=dato.clave).one_or_none()
        if espacio is None:
            espacio = EspacioUPC(clave=dato.clave)
            db.session.add(espacio)
            creados += 1
        espacio.campus = dato.campus
        espacio.nombre = dato.nombre
        espacio.tipo = dato.tipo
        espacio.pabellon = dato.pabellon
        espacio.piso = dato.piso
        espacio.aforo_minimo = dato.aforo_minimo
        espacio.aforo_maximo = dato.aforo_maximo
        espacio.requiere_reserva = dato.requiere_reserva
        espacio.max_minutos_diarios = dato.max_minutos_diarios
        espacio.fuente_url = dato.fuente_url
        espacio.verificado_en = dato.verificado_en
        espacio.activo = True
    claves_carreras = {
        slugificar(nombre)
        for nombres in CARRERAS_POR_FACULTAD.values()
        for nombre in nombres
    }
    CarreraUPC.query.filter(CarreraUPC.clave.notin_(claves_carreras)).update(
        {CarreraUPC.activa: False}, synchronize_session=False
    )
    for facultad, nombres in CARRERAS_POR_FACULTAD.items():
        for nombre in nombres:
            clave = slugificar(nombre)
            carrera = CarreraUPC.query.filter_by(clave=clave).one_or_none()
            if carrera is None:
                carrera = CarreraUPC(clave=clave)
                db.session.add(carrera)
                creados += 1
            carrera.nombre = nombre
            carrera.facultad = facultad
            carrera.fuente_url = FUENTE_MALLAS_UPC
            carrera.verificado_en = date(2026, 9, 2)
            carrera.activa = True
    db.session.commit()
    return creados
