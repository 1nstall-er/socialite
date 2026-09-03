"""Crea cuentas locales de prueba; no ejecutar en producción."""

import random

from app import create_app
from models import INTERESES_UPC, CampusUPC, CarreraUPC, PerfilUPC, Usuario, db
from verification import completar_verificacion


def main() -> None:
    app = create_app()
    if app.config["APP_ENV"] == "production":
        raise RuntimeError("Las cuentas de prueba no deben crearse en producción.")

    with app.app_context():
        carreras = CarreraUPC.query.filter_by(activa=True).all()
        if not carreras:
            raise RuntimeError("Primero debes cargar el catálogo de carreras UPC.")

        sedes = list(CampusUPC)
        intereses = [interes.clave for interes in INTERESES_UPC]

        for numero in range(1, 11):
            correo = f"test{numero}@upc.edu.pe"
            if Usuario.query.filter_by(correo_institucional=correo).first():
                continue

            carrera = random.choice(carreras)
            usuario = Usuario(
                nombre=f"Estudiante de prueba {numero}",
                correo_institucional=correo,
                carrera=carrera.nombre,
                ciclo=random.randint(1, 10),
                intereses=", ".join(random.sample(intereses, random.randint(3, 6))),
            )
            usuario.set_password("123456")
            completar_verificacion(usuario)
            usuario.perfil_upc = PerfilUPC(
                campus=random.choice(sedes),
                carrera_upc=carrera,
                facultad=carrera.facultad,
            )
            db.session.add(usuario)

        db.session.commit()


if __name__ == "__main__":
    main()
