"""Entidades persistentes de cumplimiento de datos personales.

Viven en un modulo aparte de entities.py a proposito: el dominio social
(usuarios, grupos, mensajes) y la evidencia de cumplimiento cambian por
razones distintas y las edita gente distinta. Separarlos evita choques
al trabajar en paralelo.

Corresponden a la migracion b7d3e91a4c25.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.privacy_policy import (
    DIAS_GRACIA_ELIMINACION,
    VERSION_POLITICA_ACTUAL,
    fecha_purga,
    purga_vencida,
)
from app.models.entities import db


def _ahora() -> datetime:
    return datetime.now(UTC)


class Consentimiento(db.Model):
    """Prueba de que un usuario acepto una version de la politica.

    Se guarda una fila por version aceptada, nunca se sobrescribe: si la
    politica cambia y el usuario vuelve a aceptar, quedan las dos filas.
    Eso permite responder "que acepto exactamente y cuando".
    """

    __tablename__ = "consentimientos"
    __table_args__ = (
        db.UniqueConstraint(
            "usuario_id", "version_politica", name="uq_consentimiento_usuario_version"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_politica = db.Column(db.String(32), nullable=False)
    aceptado_en = db.Column(db.DateTime(timezone=True), nullable=False, default=_ahora)

    usuario = db.relationship("Usuario", backref="consentimientos")

    @classmethod
    def registrar(cls, usuario_id: int, version: str | None = None) -> Consentimiento:
        """Registra la aceptacion de la politica vigente (idempotente)."""
        version = version or VERSION_POLITICA_ACTUAL
        existente = cls.query.filter_by(
            usuario_id=usuario_id, version_politica=version
        ).one_or_none()
        if existente is not None:
            return existente
        consentimiento = cls(usuario_id=usuario_id, version_politica=version)
        db.session.add(consentimiento)
        return consentimiento

    @classmethod
    def version_vigente_de(cls, usuario_id: int) -> str | None:
        """Ultima version aceptada por el usuario, o None si nunca acepto."""
        fila = (
            cls.query.filter_by(usuario_id=usuario_id)
            .order_by(cls.aceptado_en.desc())
            .first()
        )
        return fila.version_politica if fila else None


class SolicitudEliminacion(db.Model):
    """Solicitud de supresion con periodo de gracia.

    No se borra al instante: se agenda. Asi un borrado accidental se
    puede revertir dentro del plazo, y queda evidencia de cuando se
    pidio y cuando se ejecuto.
    """

    __tablename__ = "solicitudes_eliminacion"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    solicitado_en = db.Column(
        db.DateTime(timezone=True), nullable=False, default=_ahora
    )
    purgar_desde = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    completado_en = db.Column(db.DateTime(timezone=True), nullable=True)
    cancelado_en = db.Column(db.DateTime(timezone=True), nullable=True)
    bitacora = db.Column(db.Text, nullable=True)

    usuario = db.relationship("Usuario", backref="solicitudes_eliminacion")

    @property
    def activa(self) -> bool:
        """True si sigue pendiente de ejecutarse."""
        return self.completado_en is None and self.cancelado_en is None

    @property
    def lista_para_purgar(self) -> bool:
        """True si esta activa y ya vencio el periodo de gracia."""
        return self.activa and purga_vencida(self.solicitado_en)

    @classmethod
    def abrir(cls, usuario_id: int) -> SolicitudEliminacion:
        """Crea la solicitud calculando la fecha de purga."""
        momento = _ahora()
        solicitud = cls(
            usuario_id=usuario_id,
            solicitado_en=momento,
            purgar_desde=fecha_purga(momento, DIAS_GRACIA_ELIMINACION),
        )
        db.session.add(solicitud)
        return solicitud

    @classmethod
    def activa_de(cls, usuario_id: int) -> SolicitudEliminacion | None:
        """Solicitud pendiente del usuario, si existe."""
        return cls.query.filter_by(
            usuario_id=usuario_id, completado_en=None, cancelado_en=None
        ).one_or_none()

    def cancelar(self) -> None:
        """El titular se arrepiente dentro del periodo de gracia."""
        self.cancelado_en = _ahora()

    def completar(self, bitacora: list[str]) -> None:
        """Marca la purga como ejecutada y guarda la evidencia."""
        self.completado_en = _ahora()
        self.bitacora = "\n".join(bitacora)


class AccesoDatos(db.Model):
    """Audit log de consultas a datos personales de terceros.

    Responde la pregunta de una auditoria institucional: quien miro los
    datos de quien y cuando. Las claves quedan en SET NULL para que el
    registro sobreviva a la eliminacion de las cuentas involucradas.
    """

    __tablename__ = "accesos_datos"
    __table_args__ = (
        db.Index("ix_accesos_datos_titular_momento", "titular_id", "momento"),
    )

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    titular_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    recurso = db.Column(db.String(64), nullable=False)
    momento = db.Column(db.DateTime(timezone=True), nullable=False, default=_ahora)

    @classmethod
    def anotar(cls, actor_id: int | None, titular_id: int | None, recurso: str) -> AccesoDatos:
        """Deja constancia de un acceso a datos personales."""
        registro = cls(actor_id=actor_id, titular_id=titular_id, recurso=recurso)
        db.session.add(registro)
        return registro
