from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


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
    carrera = db.Column(db.String(80))
    ciclo = db.Column(db.Integer)
    intereses = db.Column(db.String(300))
    cursos = db.relationship("Curso", secondary=inscripciones, back_populates="usuarios")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def lista_intereses(self):
        return [item.strip() for item in (self.intereses or "").split(",") if item.strip()]


class Curso(db.Model):
    __tablename__ = "cursos"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    usuarios = db.relationship("Usuario", secondary=inscripciones, back_populates="cursos")


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
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    curso = db.relationship("Curso", backref="grupos")
    creador = db.relationship("Usuario", foreign_keys=[creador_id], backref="grupos_creados")
    miembros = db.relationship(
        "Usuario", secondary=miembros_grupo, backref="grupos", lazy="selectin"
    )

    @property
    def esta_lleno(self):
        return len(self.miembros) >= self.max_miembros
