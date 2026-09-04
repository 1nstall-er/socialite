"""Consultas optimizadas y reutilizables para las rutas de Socialite."""

from datetime import UTC, datetime

from sqlalchemy import case, exists, func, or_, select, update
from sqlalchemy.orm import joinedload, selectinload

from app.models.entities import (
    Bloqueo,
    Conexion,
    Curso,
    Grupo,
    Mensaje,
    Notificacion,
    PerfilUPC,
    Usuario,
    db,
)


def _opciones_matching_usuario():
    """Relaciones necesarias por el motor, sin productos cartesianos."""
    return (
        selectinload(Usuario.cursos),
        selectinload(Usuario.horarios),
        joinedload(Usuario.perfil_upc).joinedload(PerfilUPC.espacio_preferido),
        selectinload(Usuario.participaciones_upc),
        selectinload(Usuario.metas_curso),
    )


def _opciones_grupo():
    """Plan único de carga para listados y detalles de grupos."""
    return (
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


def _opciones_conexion():
    """Perfiles públicos requeridos por la pantalla de conexiones."""
    return (
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


def _opciones_contacto_resumido():
    campos = (
        Usuario.id,
        Usuario.nombre,
        Usuario.foto_archivo,
        Usuario.carrera,
        Usuario.ciclo,
    )
    return (
        joinedload(Conexion.remitente).load_only(*campos),
        joinedload(Conexion.destinatario).load_only(*campos),
    )


def usuario_para_matching(usuario_id):
    """Carga todas las señales del usuario actual en consultas acotadas.

    ``selectinload`` evita multiplicar cursos × horarios × participaciones ×
    metas en una sola respuesta SQL cuando el perfil crece.
    """
    sentencia = (
        select(Usuario)
        .where(Usuario.id == usuario_id)
        .options(*_opciones_matching_usuario())
        .execution_options(populate_existing=True)
    )
    return db.session.execute(sentencia).scalar_one()


def candidatos_para(usuario_id, busqueda="", curso_id=None):
    """Carga candidatos y señales en un número fijo de consultas acotadas.

    ``selectinload`` evita el problema N+1 al calcular afinidad para una lista.
    """
    sentencia = (
        select(Usuario)
        .where(
            Usuario.id != usuario_id,
            Usuario.correo_verificado_en.is_not(None),
            ~exists().where(
                or_(
                    (Bloqueo.bloqueador_id == usuario_id)
                    & (Bloqueo.bloqueado_id == Usuario.id),
                    (Bloqueo.bloqueado_id == usuario_id)
                    & (Bloqueo.bloqueador_id == Usuario.id),
                )
            ),
        )
        .options(*_opciones_matching_usuario())
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
    sentencia = select(Grupo).options(*_opciones_grupo())
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
        .options(*_opciones_grupo())
    )
    return db.session.execute(sentencia).scalars().unique().first()


def grupos_de_usuario(usuario_id):
    sentencia = (
        select(Grupo)
        .where(Grupo.miembros.any(Usuario.id == usuario_id))
        .options(*_opciones_grupo())
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
        .options(*_opciones_conexion())
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
        .options(*_opciones_conexion())
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


def hay_bloqueo_entre(usuario_a_id, usuario_b_id):
    sentencia = select(Bloqueo.id).where(
        or_(
            (Bloqueo.bloqueador_id == usuario_a_id)
            & (Bloqueo.bloqueado_id == usuario_b_id),
            (Bloqueo.bloqueador_id == usuario_b_id)
            & (Bloqueo.bloqueado_id == usuario_a_id),
        )
    )
    return db.session.execute(sentencia).scalar_one_or_none() is not None


def bloqueos_emitidos_de(usuario_id):
    sentencia = (
        select(Bloqueo)
        .where(Bloqueo.bloqueador_id == usuario_id)
        .options(joinedload(Bloqueo.bloqueado))
        .order_by(Bloqueo.creado_en.desc(), Bloqueo.id.desc())
    )
    return db.session.execute(sentencia).scalars().all()


def contacto_aceptado(usuario_id, contacto_id):
    sentencia = (
        select(Conexion)
        .where(
            Conexion.estado == "aceptada",
            ~exists().where(
                or_(
                    (Bloqueo.bloqueador_id == usuario_id)
                    & (Bloqueo.bloqueado_id == contacto_id),
                    (Bloqueo.bloqueador_id == contacto_id)
                    & (Bloqueo.bloqueado_id == usuario_id),
                )
            ),
            or_(
                (Conexion.remitente_id == usuario_id)
                & (Conexion.destinatario_id == contacto_id),
                (Conexion.remitente_id == contacto_id)
                & (Conexion.destinatario_id == usuario_id),
            ),
        )
        .options(*_opciones_contacto_resumido())
    )
    return db.session.execute(sentencia).scalars().first()


def contactos_aceptados_de(usuario_id):
    sentencia = (
        select(Conexion)
        .where(
            Conexion.estado == "aceptada",
            ~exists().where(
                or_(
                    (Bloqueo.bloqueador_id == usuario_id)
                    & (Bloqueo.bloqueado_id == case(
                        (Conexion.remitente_id == usuario_id, Conexion.destinatario_id),
                        else_=Conexion.remitente_id,
                    )),
                    (Bloqueo.bloqueado_id == usuario_id)
                    & (Bloqueo.bloqueador_id == case(
                        (Conexion.remitente_id == usuario_id, Conexion.destinatario_id),
                        else_=Conexion.remitente_id,
                    )),
                )
            ),
            or_(
                Conexion.remitente_id == usuario_id,
                Conexion.destinatario_id == usuario_id,
            ),
        )
        .options(*_opciones_contacto_resumido())
        .order_by(Conexion.actualizada_en.desc(), Conexion.id.desc())
    )
    return db.session.execute(sentencia).scalars().all()


def mensajes_entre(usuario_id, contacto_id, limite=50, antes_de_id=None):
    sentencia = (
        select(Mensaje)
        .where(
            or_(
                (Mensaje.emisor_id == usuario_id)
                & (Mensaje.receptor_id == contacto_id),
                (Mensaje.emisor_id == contacto_id)
                & (Mensaje.receptor_id == usuario_id),
            )
        )
        .order_by(Mensaje.enviado_en.desc(), Mensaje.id.desc())
        .limit(min(max(int(limite), 1), 100))
    )
    if antes_de_id:
        sentencia = sentencia.where(Mensaje.id < int(antes_de_id))
    mensajes = db.session.execute(sentencia).scalars().all()
    mensajes.reverse()
    return mensajes


def ultimos_mensajes_por_contacto(usuario_id):
    otro_id = case(
        (Mensaje.emisor_id == usuario_id, Mensaje.receptor_id),
        else_=Mensaje.emisor_id,
    )
    orden = func.row_number().over(
        partition_by=otro_id,
        order_by=(Mensaje.enviado_en.desc(), Mensaje.id.desc()),
    )
    clasificados = (
        select(
            Mensaje.id.label("mensaje_id"),
            otro_id.label("contacto_id"),
            orden.label("posicion"),
        )
        .where(
            or_(
                Mensaje.emisor_id == usuario_id,
                Mensaje.receptor_id == usuario_id,
            )
        )
        .subquery()
    )
    sentencia = (
        select(Mensaje, clasificados.c.contacto_id)
        .join(clasificados, clasificados.c.mensaje_id == Mensaje.id)
        .where(clasificados.c.posicion == 1)
    )
    return {
        int(contacto_id): mensaje
        for mensaje, contacto_id in db.session.execute(sentencia).all()
    }


def mensajes_no_leidos_por_contacto(usuario_id):
    sentencia = (
        select(Mensaje.emisor_id, func.count(Mensaje.id))
        .where(Mensaje.receptor_id == usuario_id, Mensaje.leido.is_(False))
        .group_by(Mensaje.emisor_id)
    )
    return {
        int(emisor_id): int(cantidad)
        for emisor_id, cantidad in db.session.execute(sentencia).all()
    }


def marcar_mensajes_leidos(usuario_id, contacto_id):
    sentencia = (
        update(Mensaje)
        .where(
            Mensaje.emisor_id == contacto_id,
            Mensaje.receptor_id == usuario_id,
            Mensaje.leido.is_(False),
        )
        .values(leido=True, leido_en=datetime.now(UTC))
        .execution_options(synchronize_session="fetch")
    )
    resultado = db.session.execute(sentencia)
    return int(resultado.rowcount or 0)


def notificaciones_de(usuario_id, limite=30, solo_no_leidas=False):
    sentencia = (
        select(Notificacion)
        .where(Notificacion.usuario_id == usuario_id)
        .options(joinedload(Notificacion.actor))
        .order_by(Notificacion.creada_en.desc(), Notificacion.id.desc())
        .limit(min(max(int(limite), 1), 100))
    )
    if solo_no_leidas:
        sentencia = sentencia.where(Notificacion.leida.is_(False))
    return db.session.execute(sentencia).scalars().all()


def notificaciones_no_leidas_total(usuario_id):
    sentencia = select(func.count(Notificacion.id)).where(
        Notificacion.usuario_id == usuario_id,
        Notificacion.leida.is_(False),
    )
    return int(db.session.execute(sentencia).scalar_one())


def marcar_notificaciones_leidas(usuario_id):
    sentencia = (
        update(Notificacion)
        .where(
            Notificacion.usuario_id == usuario_id,
            Notificacion.leida.is_(False),
        )
        .values(leida=True, leida_en=datetime.now(UTC))
        .execution_options(synchronize_session="fetch")
    )
    resultado = db.session.execute(sentencia)
    return int(resultado.rowcount or 0)


def marcar_conversacion_leida(usuario_id, contacto_id):
    mensajes_marcados = marcar_mensajes_leidos(usuario_id, contacto_id)
    sentencia = (
        update(Notificacion)
        .where(
            Notificacion.usuario_id == usuario_id,
            Notificacion.leida.is_(False),
            Notificacion.mensaje.has(Mensaje.emisor_id == contacto_id),
        )
        .values(leida=True, leida_en=datetime.now(UTC))
        .execution_options(synchronize_session="fetch")
    )
    resultado = db.session.execute(sentencia)
    return mensajes_marcados, int(resultado.rowcount or 0)
