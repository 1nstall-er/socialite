"""Consultas optimizadas y reutilizables para las rutas de Socialite."""

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload, selectinload

from models import Conexion, Curso, Grupo, PerfilUPC, Usuario, db


def usuario_para_matching(usuario_id):
    """Carga todas las senales del usuario actual en una sola consulta.

    El join de colecciones se limita a un unico usuario; evita cinco lecturas
    perezosas sin producir el producto cartesiano de todos los candidatos.
    """
    sentencia = (
        select(Usuario)
        .where(Usuario.id == usuario_id)
        .options(
            joinedload(Usuario.cursos),
            joinedload(Usuario.horarios),
            joinedload(Usuario.perfil_upc).joinedload(PerfilUPC.espacio_preferido),
            joinedload(Usuario.participaciones_upc),
            joinedload(Usuario.metas_curso),
        )
        .execution_options(populate_existing=True)
    )
    return db.session.execute(sentencia).scalars().unique().one()


def candidatos_para(usuario_id, busqueda="", curso_id=None):
    """Carga candidatos, cursos y horarios en tres consultas acotadas.

    ``selectinload`` evita el problema N+1 al calcular afinidad para una lista.
    """
    sentencia = (
        select(Usuario)
        .where(Usuario.id != usuario_id)
        .options(
            selectinload(Usuario.cursos),
            selectinload(Usuario.horarios),
            joinedload(Usuario.perfil_upc).joinedload(PerfilUPC.espacio_preferido),
            selectinload(Usuario.participaciones_upc),
            selectinload(Usuario.metas_curso),
        )
    )
    if busqueda:
        patron = f"%{busqueda.strip()}%"
        sentencia = sentencia.where(
            or_(
                Usuario.nombre.ilike(patron),
                Usuario.carrera.ilike(patron),
                Usuario.intereses.ilike(patron),
            )
        )
    if curso_id:
        sentencia = sentencia.where(Usuario.cursos.any(Curso.id == curso_id))
    return db.session.execute(sentencia).scalars().unique().all()


def grupos_filtrados(tipo="", curso_id=None, dia="", busqueda=""):
    """Obtiene grupos con relaciones precargadas para tarjetas y detalle."""
    sentencia = select(Grupo).options(
        joinedload(Grupo.curso),
        joinedload(Grupo.creador).selectinload(Usuario.cursos),
        joinedload(Grupo.creador).selectinload(Usuario.horarios),
        joinedload(Grupo.creador)
        .joinedload(Usuario.perfil_upc)
        .joinedload(PerfilUPC.espacio_preferido),
        joinedload(Grupo.creador).selectinload(Usuario.participaciones_upc),
        selectinload(Grupo.miembros).selectinload(Usuario.cursos),
        selectinload(Grupo.miembros).selectinload(Usuario.horarios),
        selectinload(Grupo.miembros)
        .joinedload(Usuario.perfil_upc)
        .joinedload(PerfilUPC.espacio_preferido),
        selectinload(Grupo.miembros).selectinload(Usuario.participaciones_upc),
    )
    if tipo:
        sentencia = sentencia.where(Grupo.tipo == tipo)
    if curso_id:
        sentencia = sentencia.where(Grupo.curso_id == curso_id)
    if dia:
        sentencia = sentencia.where(Grupo.dia == dia)
    if busqueda:
        patron = f"%{busqueda.strip()}%"
        sentencia = sentencia.outerjoin(Curso).where(
            or_(
                Grupo.lugar.ilike(patron),
                Curso.codigo.ilike(patron),
                Curso.nombre.ilike(patron),
            )
        )
    sentencia = sentencia.order_by(Grupo.creado_en.desc(), Grupo.id.desc())
    return db.session.execute(sentencia).scalars().unique().all()


def obtener_grupo(grupo_id):
    sentencia = (
        select(Grupo)
        .where(Grupo.id == grupo_id)
        .options(
            joinedload(Grupo.curso),
            joinedload(Grupo.creador).selectinload(Usuario.cursos),
            joinedload(Grupo.creador).selectinload(Usuario.horarios),
            joinedload(Grupo.creador)
            .joinedload(Usuario.perfil_upc)
            .joinedload(PerfilUPC.espacio_preferido),
            joinedload(Grupo.creador).selectinload(Usuario.participaciones_upc),
            selectinload(Grupo.miembros).selectinload(Usuario.cursos),
            selectinload(Grupo.miembros).selectinload(Usuario.horarios),
            selectinload(Grupo.miembros)
            .joinedload(Usuario.perfil_upc)
            .joinedload(PerfilUPC.espacio_preferido),
            selectinload(Grupo.miembros).selectinload(Usuario.participaciones_upc),
        )
    )
    return db.session.execute(sentencia).scalars().unique().first()


def grupos_de_usuario(usuario_id):
    sentencia = (
        select(Grupo)
        .where(Grupo.miembros.any(Usuario.id == usuario_id))
        .options(
            joinedload(Grupo.curso),
            joinedload(Grupo.creador).selectinload(Usuario.cursos),
            joinedload(Grupo.creador).selectinload(Usuario.horarios),
            joinedload(Grupo.creador)
            .joinedload(Usuario.perfil_upc)
            .joinedload(PerfilUPC.espacio_preferido),
            joinedload(Grupo.creador).selectinload(Usuario.participaciones_upc),
            selectinload(Grupo.miembros).selectinload(Usuario.cursos),
            selectinload(Grupo.miembros).selectinload(Usuario.horarios),
            selectinload(Grupo.miembros)
            .joinedload(Usuario.perfil_upc)
            .joinedload(PerfilUPC.espacio_preferido),
            selectinload(Grupo.miembros).selectinload(Usuario.participaciones_upc),
        )
        .order_by(Grupo.creado_en.desc(), Grupo.id.desc())
    )
    return db.session.execute(sentencia).scalars().unique().all()


def conexion_entre(usuario_a_id, usuario_b_id):
    sentencia = (
        select(Conexion)
        .where(
            or_(
                (Conexion.remitente_id == usuario_a_id)
                & (Conexion.destinatario_id == usuario_b_id),
                (Conexion.remitente_id == usuario_b_id)
                & (Conexion.destinatario_id == usuario_a_id),
            )
        )
        .options(
            joinedload(Conexion.remitente).selectinload(Usuario.cursos),
            joinedload(Conexion.remitente).selectinload(Usuario.horarios),
            joinedload(Conexion.remitente)
            .joinedload(Usuario.perfil_upc)
            .joinedload(PerfilUPC.espacio_preferido),
            joinedload(Conexion.remitente).selectinload(Usuario.participaciones_upc),
            joinedload(Conexion.destinatario).selectinload(Usuario.cursos),
            joinedload(Conexion.destinatario).selectinload(Usuario.horarios),
            joinedload(Conexion.destinatario)
            .joinedload(Usuario.perfil_upc)
            .joinedload(PerfilUPC.espacio_preferido),
            joinedload(Conexion.destinatario).selectinload(Usuario.participaciones_upc),
        )
    )
    return db.session.execute(sentencia).scalars().first()


def conexiones_de(usuario_id, estado=None):
    sentencia = (
        select(Conexion)
        .where(
            or_(
                Conexion.remitente_id == usuario_id,
                Conexion.destinatario_id == usuario_id,
            )
        )
        .options(
            joinedload(Conexion.remitente).selectinload(Usuario.cursos),
            joinedload(Conexion.remitente).selectinload(Usuario.horarios),
            joinedload(Conexion.remitente)
            .joinedload(Usuario.perfil_upc)
            .joinedload(PerfilUPC.espacio_preferido),
            joinedload(Conexion.remitente).selectinload(Usuario.participaciones_upc),
            joinedload(Conexion.destinatario).selectinload(Usuario.cursos),
            joinedload(Conexion.destinatario).selectinload(Usuario.horarios),
            joinedload(Conexion.destinatario)
            .joinedload(Usuario.perfil_upc)
            .joinedload(PerfilUPC.espacio_preferido),
            joinedload(Conexion.destinatario).selectinload(Usuario.participaciones_upc),
        )
        .order_by(Conexion.actualizada_en.desc(), Conexion.id.desc())
    )
    if estado:
        sentencia = sentencia.where(Conexion.estado == estado)
    return db.session.execute(sentencia).scalars().all()


def conexiones_con_candidatos(usuario_id, candidatos_ids):
    """Devuelve un mapa candidato->conexion con una sola consulta."""
    ids = set(candidatos_ids)
    if not ids:
        return {}
    sentencia = (
        select(Conexion)
        .where(
            or_(
                (Conexion.remitente_id == usuario_id)
                & Conexion.destinatario_id.in_(ids),
                (Conexion.destinatario_id == usuario_id)
                & Conexion.remitente_id.in_(ids),
            )
        )
        .options(joinedload(Conexion.remitente), joinedload(Conexion.destinatario))
    )
    resultado = {}
    for conexion in db.session.execute(sentencia).scalars().all():
        otro_id = (
            conexion.destinatario_id
            if conexion.remitente_id == usuario_id
            else conexion.remitente_id
        )
        resultado[otro_id] = conexion
    return resultado
