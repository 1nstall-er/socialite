import unittest

from app import create_app
from models import Curso, Grupo, Horario, Usuario, db


class SocialiteTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "CSRF_ENABLED": False,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def registrar(self, nombre="Ana", correo="ana@upc.edu.pe", password="segura123"):
        return self.client.post(
            "/registro",
            data={
                "nombre": nombre,
                "correo": correo,
                "password": password,
                "carrera": "Ingenieria de Software",
                "ciclo": "5",
            },
            follow_redirects=True,
        )

    def test_registro_requiere_correo_upc_y_guarda_password_seguro(self):
        respuesta = self.registrar(correo="ana@gmail.com")
        self.assertIn("Usa tu correo institucional", respuesta.get_data(as_text=True))

        respuesta = self.registrar()
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Mi perfil", respuesta.get_data(as_text=True))
        with self.app.app_context():
            usuario = Usuario.query.one()
            self.assertNotEqual(usuario.password_hash, "segura123")
            self.assertTrue(usuario.check_password("segura123"))

    def test_formularios_rechazan_envios_sin_token_csrf(self):
        self.app.config["CSRF_ENABLED"] = True
        respuesta = self.client.post(
            "/registro",
            data={
                "nombre": "Ana",
                "correo": "ana@upc.edu.pe",
                "password": "segura123",
            },
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_usuario_puede_salir_y_volver_a_ingresar(self):
        self.registrar()
        self.client.post("/salir")
        respuesta = self.client.get("/perfil")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/ingresar", respuesta.headers["Location"])

        respuesta = self.client.post(
            "/ingresar",
            data={"correo": "ana@upc.edu.pe", "password": "segura123"},
            follow_redirects=True,
        )
        self.assertIn("Bienvenido de nuevo", respuesta.get_data(as_text=True))
        with self.client.session_transaction() as sesion:
            self.assertIn("usuario_id", sesion)

    def test_perfil_agrega_curso_y_horario(self):
        self.registrar()
        self.client.post(
            "/perfil/cursos",
            data={"codigo": "ma101", "nombre_curso": "Calculo I"},
        )
        self.client.post(
            "/perfil/horarios",
            data={"dia": "Martes", "hora_inicio": "10:00", "hora_fin": "12:00"},
        )
        self.client.post(
            "/perfil/horarios",
            data={"dia": "Martes", "hora_inicio": "25:00", "hora_fin": "26:00"},
        )

        with self.app.app_context():
            usuario = Usuario.query.one()
            self.assertEqual(usuario.cursos[0].codigo, "MA101")
            self.assertEqual(usuario.horarios[0].dia, "Martes")
            self.assertEqual(len(usuario.horarios), 1)

    def test_crear_unirse_y_respetar_capacidad_del_grupo(self):
        self.registrar()
        self.client.post(
            "/perfil/cursos",
            data={"codigo": "MA101", "nombre_curso": "Calculo I"},
        )
        with self.app.app_context():
            curso_id = Curso.query.one().id

        respuesta = self.client.post(
            "/grupos",
            data={
                "tipo": "estudio",
                "curso_id": str(curso_id),
                "lugar": "Biblioteca, piso 3",
                "dia": "Martes",
                "hora_inicio": "10:00",
                "hora_fin": "12:00",
                "max_miembros": "2",
            },
            follow_redirects=True,
        )
        self.assertIn("Grupo creado", respuesta.get_data(as_text=True))

        self.client.post("/salir")
        self.registrar(nombre="Bruno", correo="bruno@upc.edu.pe")
        respuesta = self.client.post("/grupos/1/unirse", follow_redirects=True)
        self.assertIn("Te uniste", respuesta.get_data(as_text=True))

        self.client.post("/salir")
        self.registrar(nombre="Carla", correo="carla@upc.edu.pe")
        respuesta = self.client.post("/grupos/1/unirse", follow_redirects=True)
        self.assertIn("capacidad maxima", respuesta.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(len(Grupo.query.one().miembros), 2)

    def test_matching_muestra_razones_de_afinidad(self):
        with self.app.app_context():
            curso = Curso(codigo="MA101", nombre="Calculo I")
            ana = Usuario(
                nombre="Ana",
                correo_institucional="ana@upc.edu.pe",
                carrera="Software",
                intereses="fotografia, futbol",
            )
            bruno = Usuario(
                nombre="Bruno",
                correo_institucional="bruno@upc.edu.pe",
                carrera="Sistemas",
                intereses="fotografia, musica",
            )
            ana.set_password("segura123")
            bruno.set_password("segura123")
            ana.cursos.append(curso)
            bruno.cursos.append(curso)
            ana.horarios.append(Horario(dia="Lunes", hora_inicio="10:00", hora_fin="12:00"))
            bruno.horarios.append(Horario(dia="Lunes", hora_inicio="11:00", hora_fin="13:00"))
            db.session.add_all([ana, bruno])
            db.session.commit()
            ana_id = ana.id

        with self.client.session_transaction() as sesion:
            sesion["usuario_id"] = ana_id
        respuesta = self.client.get("/companeros")
        pagina = respuesta.get_data(as_text=True)
        self.assertIn("Bruno", pagina)
        self.assertIn("1 curso en común", pagina)
        self.assertIn("1.0 h disponibles juntos", pagina)
        self.assertIn("fotografia", pagina)


if __name__ == "__main__":
    unittest.main()
