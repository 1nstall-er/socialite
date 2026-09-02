import unittest

from sqlalchemy import event

from app import create_app
from matching import calcular_afinidad, minutos_compartidos
from models import Conexion, Curso, Grupo, Horario, Usuario, db


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

    def registrar(self, nombre="Ana", correo="ana@upc.edu.pe", password="segura1234"):
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
            self.assertNotEqual(usuario.password_hash, "segura1234")
            self.assertTrue(usuario.check_password("segura1234"))

    def test_formularios_rechazan_envios_sin_token_csrf(self):
        self.app.config["CSRF_ENABLED"] = True
        respuesta = self.client.post(
            "/registro",
            data={
                "nombre": "Ana",
                "correo": "ana@upc.edu.pe",
                "password": "segura1234",
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
            data={"correo": "ana@upc.edu.pe", "password": "segura1234"},
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
            ana.set_password("segura1234")
            bruno.set_password("segura1234")
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

    def test_matching_fusiona_bloques_y_no_duplica_minutos(self):
        propios = [
            Horario(dia="Lunes", hora_inicio="10:00", hora_fin="12:00"),
            Horario(dia="Lunes", hora_inicio="11:00", hora_fin="13:00"),
        ]
        ajenos = [Horario(dia="Lunes", hora_inicio="11:00", hora_fin="12:00")]
        self.assertEqual(minutos_compartidos(propios, ajenos), 60)

    def test_matching_entrega_desglose_explicable(self):
        with self.app.app_context():
            curso = Curso(codigo="SW201", nombre="Programacion Web")
            ana = Usuario(
                nombre="Ana",
                correo_institucional="ana@upc.edu.pe",
                intereses="fotografia, musica",
            )
            bruno = Usuario(
                nombre="Bruno",
                correo_institucional="bruno@upc.edu.pe",
                intereses="Fotografía, futbol",
            )
            ana.set_password("segura1234")
            bruno.set_password("segura1234")
            ana.cursos.append(curso)
            bruno.cursos.append(curso)
            ana.horarios.append(
                Horario(dia="Martes", hora_inicio="10:00", hora_fin="12:00")
            )
            bruno.horarios.append(
                Horario(dia="Martes", hora_inicio="10:30", hora_fin="12:30")
            )
            db.session.add_all([ana, bruno])
            db.session.commit()

            resultado = calcular_afinidad(ana, bruno)
            self.assertEqual(resultado["porcentaje"], 69)
            self.assertEqual(resultado["horas"], 1.5)
            self.assertEqual(resultado["intereses"], ["fotografia"])
            self.assertEqual(set(resultado["componentes"]), {"cursos", "horarios", "intereses"})

    def test_api_companeros_expone_contrato_paginado(self):
        self.registrar()
        self.client.post("/salir")
        self.registrar(nombre="Bruno", correo="bruno@upc.edu.pe")
        self.client.post("/salir")
        self.client.post(
            "/ingresar",
            data={"correo": "ana@upc.edu.pe", "password": "segura1234"},
        )

        respuesta = self.client.get("/api/v1/companeros?por_pagina=1")
        datos = respuesta.get_json()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(datos["paginacion"]["por_pagina"], 1)
        self.assertEqual(datos["paginacion"]["total"], 1)
        self.assertIn("componentes", datos["resultados"][0])
        self.assertNotIn("correo_institucional", datos["resultados"][0]["usuario"])

    def test_flujo_de_conexion_revela_email_solo_al_aceptar(self):
        self.registrar()
        with self.app.app_context():
            ana_id = Usuario.query.filter_by(correo_institucional="ana@upc.edu.pe").one().id
        self.client.post("/salir")
        self.registrar(nombre="Bruno", correo="bruno@upc.edu.pe")
        with self.app.app_context():
            bruno_id = Usuario.query.filter_by(correo_institucional="bruno@upc.edu.pe").one().id

        respuesta = self.client.get(f"/personas/{ana_id}")
        self.assertNotIn("correo_institucional", respuesta.get_json()["persona"])
        self.client.post(f"/companeros/{ana_id}/conectar")
        with self.app.app_context():
            conexion_id = Conexion.query.one().id

        self.client.post("/salir")
        self.client.post(
            "/ingresar",
            data={"correo": "ana@upc.edu.pe", "password": "segura1234"},
        )
        self.client.post(f"/conexiones/{conexion_id}/aceptar")
        respuesta = self.client.get(f"/personas/{bruno_id}")
        self.assertEqual(
            respuesta.get_json()["persona"]["correo_institucional"],
            "bruno@upc.edu.pe",
        )

    def test_respuestas_incluyen_cabeceras_de_seguridad(self):
        respuesta = self.client.get("/")
        self.assertEqual(respuesta.headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", respuesta.headers["Content-Security-Policy"])

    def test_matching_evitar_n_mas_uno_al_crecer_candidatos(self):
        with self.app.app_context():
            principal = Usuario(
                nombre="Principal",
                correo_institucional="principal@upc.edu.pe",
                intereses="tecnologia",
            )
            principal.set_password("segura1234")
            db.session.add(principal)
            for indice in range(12):
                candidato = Usuario(
                    nombre=f"Candidato {indice}",
                    correo_institucional=f"candidato{indice}@upc.edu.pe",
                    intereses="tecnologia",
                )
                candidato.set_password("segura1234")
                candidato.horarios.append(
                    Horario(
                        dia="Lunes", hora_inicio="10:00", hora_fin="11:00"
                    )
                )
                db.session.add(candidato)
            db.session.commit()
            principal_id = principal.id
            motor = db.engine

        with self.client.session_transaction() as sesion:
            sesion["usuario_id"] = principal_id
        consultas = []

        def registrar_consulta(conn, cursor, sentencia, parametros, contexto, muchos):
            if sentencia.lstrip().upper().startswith("SELECT"):
                consultas.append(sentencia)

        event.listen(motor, "before_cursor_execute", registrar_consulta)
        try:
            respuesta = self.client.get("/api/v1/companeros?por_pagina=12")
        finally:
            event.remove(motor, "before_cursor_execute", registrar_consulta)

        self.assertEqual(respuesta.status_code, 200)
        self.assertLessEqual(len(consultas), 8)

    def test_rutas_sin_template_entregan_contrato_json(self):
        self.registrar()
        respuesta = self.client.get("/panel")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()["template_pendiente"], "panel.html")
        self.assertIn("metricas", respuesta.get_json())

        respuesta = self.client.get("/grupos/nuevo")
        self.assertEqual(respuesta.get_json()["limites"]["max_miembros"], 12)


if __name__ == "__main__":
    unittest.main()
