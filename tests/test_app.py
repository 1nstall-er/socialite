import unittest

from sqlalchemy import event

from app import create_app
from matching import calcular_afinidad, minutos_compartidos
from models import (
    CampusUPC,
    CarreraUPC,
    Conexion,
    Curso,
    EspacioUPC,
    EstiloEstudio,
    FacultadUPC,
    Grupo,
    Horario,
    MetaCursoUPC,
    ObjetivoSocialite,
    ParticipacionUPC,
    PerfilUPC,
    RolActividadUPC,
    RolCursoUPC,
    TipoActividadUPC,
    Usuario,
    db,
    sincronizar_catalogo_upc,
)


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

    def test_catalogo_upc_verificado_es_idempotente(self):
        respuesta = self.client.get("/api/v1/catalogo-upc")
        catalogo = respuesta.get_json()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            {campus["valor"] for campus in catalogo["campus"]},
            {"monterrico", "villa", "san_isidro", "san_miguel"},
        )
        self.assertEqual(len(catalogo["facultades"]), 13)
        self.assertEqual(len(catalogo["carreras"]), 59)
        self.assertIn(
            "Ingeniería de Software",
            {carrera["nombre"] for carrera in catalogo["carreras"]},
        )
        self.assertEqual(catalogo["viernes_cultural"]["hora_inicio"], "13:00")
        self.assertEqual(catalogo["creditos_extraacademicos_requeridos"], 4)

        with self.app.app_context():
            total_inicial = EspacioUPC.query.count()
            self.assertEqual(total_inicial, 13)
            self.assertEqual(sincronizar_catalogo_upc(), 0)
            self.assertEqual(EspacioUPC.query.count(), total_inicial)
            cubiculo = EspacioUPC.query.filter_by(
                clave="cubiculos-san-isidro-b"
            ).one()
            self.assertEqual(cubiculo.aforo_maximo, 7)
            self.assertEqual(cubiculo.max_minutos_diarios, 120)

    def test_perfil_upc_y_vida_universitaria_exponen_contrato_privado(self):
        self.registrar()
        with self.app.app_context():
            espacio_id = EspacioUPC.query.filter_by(
                clave="cubiculos-san-miguel-a"
            ).one().id
            carrera_id = CarreraUPC.query.filter_by(
                clave="ingenieria-de-software"
            ).one().id

        respuesta = self.client.post(
            "/perfil/upc",
            data={
                "campus": "san_miguel",
                "facultad": "ingenieria",
                "carrera_upc_id": str(carrera_id),
                "modalidad": "presencial",
                "objetivo": "proyectos",
                "estilo_estudio": "practico",
                "viernes_cultural_disponible": "si",
                "acepta_intercampus": "1",
                "espacio_preferido_id": str(espacio_id),
            },
            follow_redirects=True,
        )
        self.assertIn("Contexto UPC actualizado", respuesta.get_data(as_text=True))

        respuesta = self.client.post(
            "/perfil/participaciones",
            data={
                "tipo": "grupo_upc",
                "nombre": "Comunidad de Programacion Competitiva",
                "rol": "coordinador",
                "campus": "san_miguel",
                "periodo": "2026-2",
                "creditos_confirmados": "1",
                "activa": "1",
            },
            follow_redirects=True,
        )
        self.assertIn("Actividad UPC agregada", respuesta.get_data(as_text=True))

        contrato = self.client.get("/api/v1/perfil").get_json()["perfil"]
        self.assertEqual(contrato["perfil_upc"]["campus"], "san_miguel")
        self.assertEqual(
            contrato["perfil_upc"]["carrera"]["nombre"],
            "Ingeniería de Software",
        )
        self.assertEqual(
            contrato["perfil_upc"]["espacio_preferido"]["aforo_maximo"], 6
        )
        self.assertEqual(contrato["creditos_extraacademicos"]["confirmados"], 1)
        self.assertEqual(contrato["creditos_extraacademicos"]["pendientes"], 3)
        self.assertEqual(contrato["participaciones_upc"][0]["tipo"], "grupo_upc")

    def test_validaciones_upc_rechazan_periodos_y_prioridades_invalidas(self):
        with self.app.app_context():
            usuario = Usuario(
                nombre="Ana",
                correo_institucional="ana@upc.edu.pe",
            )
            usuario.set_password("segura1234")
            curso = Curso(codigo="MA420", nombre="Matematica Basica")
            with self.assertRaisesRegex(ValueError, "formato AAAA-1"):
                ParticipacionUPC(
                    usuario=usuario,
                    tipo=TipoActividadUPC.TALLER,
                    nombre="Teatro",
                    rol=RolActividadUPC.PARTICIPANTE,
                    periodo="2026-3",
                )
            with self.assertRaisesRegex(ValueError, "prioridad"):
                MetaCursoUPC(
                    usuario=usuario,
                    curso=curso,
                    rol=RolCursoUPC.REFORZAR,
                    prioridad=6,
                )

    def test_matching_upc_activa_senales_contextuales_explicables(self):
        with self.app.app_context():
            espacio = EspacioUPC.query.filter_by(
                clave="cubiculos-san-isidro-b"
            ).one()
            curso = Curso(codigo="MA420", nombre="Matematica Basica")
            ana = Usuario(
                nombre="Ana",
                correo_institucional="ana@upc.edu.pe",
                carrera="Ingenieria de Software",
                intereses="programacion, musica",
            )
            bruno = Usuario(
                nombre="Bruno",
                correo_institucional="bruno@upc.edu.pe",
                carrera="Ingenieria de Sistemas de Informacion",
                intereses="programacion, deporte",
            )
            ana.set_password("segura1234")
            bruno.set_password("segura1234")
            for usuario in (ana, bruno):
                usuario.cursos.append(curso)
                usuario.horarios.append(
                    Horario(
                        dia="Viernes", hora_inicio="13:00", hora_fin="15:00"
                    )
                )
                usuario.perfil_upc = PerfilUPC(
                    campus=CampusUPC.SAN_ISIDRO,
                    facultad=FacultadUPC.INGENIERIA,
                    objetivo=ObjetivoSocialite.PROYECTOS,
                    estilo_estudio=EstiloEstudio.PRACTICO,
                    viernes_cultural_disponible=True,
                    espacio_preferido=espacio,
                )
                usuario.participaciones_upc.append(
                    ParticipacionUPC(
                        tipo=TipoActividadUPC.GRUPO_UPC,
                        nombre="Programacion Competitiva",
                        rol=RolActividadUPC.PARTICIPANTE,
                        campus=CampusUPC.SAN_ISIDRO,
                        periodo="2026-2",
                    )
                )
            ana.metas_curso.append(
                MetaCursoUPC(
                    curso=curso,
                    rol=RolCursoUPC.ENSENAR,
                    prioridad=5,
                    busca_equipo=True,
                )
            )
            bruno.metas_curso.append(
                MetaCursoUPC(
                    curso=curso,
                    rol=RolCursoUPC.REFORZAR,
                    prioridad=5,
                    busca_equipo=True,
                )
            )
            db.session.add_all([ana, bruno])
            db.session.commit()

            resultado = calcular_afinidad(ana, bruno)
            self.assertGreaterEqual(resultado["porcentaje"], 80)
            self.assertEqual(
                set(resultado["componentes"]),
                {
                    "cursos",
                    "horarios",
                    "intereses",
                    "campus",
                    "contexto_academico",
                    "estilo_objetivo",
                    "vida_universitaria",
                    "metas_curso",
                },
            )
            tipos_razon = {razon["tipo"] for razon in resultado["razones"]}
            self.assertIn("viernes_cultural", tipos_razon)
            self.assertIn("metas_curso", tipos_razon)
            self.assertEqual(
                resultado["contexto_upc"]["campus"]["espacio"],
                "Cubículos - Biblioteca Pabellón B",
            )


if __name__ == "__main__":
    unittest.main()
