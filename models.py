from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

inscripciones = db.Table(
    "inscripciones",
    db.Column("usuario_id", db.Integer, db.ForeignKey("usuarios.id"), primary_key=True),
    db.Column("curso_id", db.Integer, db.ForeignKey("cursos.id"), primary_key=True),
)


class Usuario(db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False)
    correo_institucional = db.Column(db.String(120), unique=True, nullable=False)
    carrera = db.Column(db.String(80))
    ciclo = db.Column(db.Integer)
    cursos = db.relationship("Curso", secondary=inscripciones, backref="usuarios")


class Curso(db.Model):
    __tablename__ = "cursos"
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)
    nombre = db.Column(db.String(120), nullable=False)


class Horario(db.Model):
    __tablename__ = "horarios"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    dia = db.Column(db.String(20))
    hora_inicio = db.Column(db.String(5))
    hora_fin = db.Column(db.String(5))
    usuario = db.relationship("Usuario", backref="horarios")


class Grupo(db.Model):
    __tablename__ = "grupos"
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20))
    curso_id = db.Column(db.Integer, db.ForeignKey("cursos.id"), nullable=True)
    lugar = db.Column(db.String(120))
